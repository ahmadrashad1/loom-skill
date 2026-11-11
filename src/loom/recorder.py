"""Scene-synchronised demonstration recorder.

For each scene: note the start time, run the actions while the (already
generated) narration would be playing, check the scene's completion criteria,
then hold the screen until the narration has finished. The resulting timeline
lets the renderer place every narration clip exactly where its scene began.
"""

from __future__ import annotations

import json
import math
import os
import shutil
import time
from pathlib import Path

from playwright.sync_api import Page, sync_playwright

from . import overlay
from .config import Settings
from .plan import (Click, Goto, Highlight, Hover, Plan, Press, Scene, Scroll, Select,
                   Title, TypeText, Wait, WaitFor)


class RecordingError(RuntimeError):
    pass


def preflight(plan: Plan, durations: dict[str, float], allow_destructive: bool) -> None:
    if not plan.approved:
        raise RecordingError(
            "plan is not approved. Review it with the user, then set \"approved\": true.")
    missing = [s.id for s in plan.scenes if s.id not in durations]
    if missing:
        raise RecordingError(f"no narration audio for scenes {missing}; run `loom voice` first")
    bad = plan.destructive_actions()
    if bad and not allow_destructive:
        raise RecordingError(
            f"plan contains destructive actions {bad}; get explicit user approval and "
            "pass --allow-destructive")
    unset = [e for e in plan.secret_envs() if not os.environ.get(e)]
    if unset:
        raise RecordingError(f"secret env vars not set: {unset}")


class _Driver:
    def __init__(self, page: Page, plan: Plan):
        self.page = page
        self.plan = plan
        self.mouse = (plan.viewport.width / 2, plan.viewport.height / 2)

    # -- helpers -----------------------------------------------------------
    def _after_nav(self) -> None:
        try:
            self.page.wait_for_load_state("domcontentloaded", timeout=15000)
        except Exception:
            pass
        self.page.evaluate(overlay.CURSOR_JS)
        if self.plan.redact:
            self.page.evaluate(overlay.redact_js(self.plan.redact))
        self.page.mouse.move(*self.mouse)

    def glide(self, x: float, y: float) -> None:
        x0, y0 = self.mouse
        dist = math.hypot(x - x0, y - y0)
        if dist < 2:
            return
        total_ms = min(900, 250 + dist * 0.45)
        steps = max(8, int(total_ms / 16))
        for i in range(1, steps + 1):
            t = i / steps
            e = t * t * (3 - 2 * t)  # smoothstep
            self.page.mouse.move(x0 + (x - x0) * e, y0 + (y - y0) * e)
            self.page.wait_for_timeout(total_ms / steps)
        self.mouse = (x, y)

    def glide_to(self, selector: str) -> None:
        loc = self.page.locator(selector).first
        loc.wait_for(state="visible", timeout=15000)
        loc.scroll_into_view_if_needed(timeout=5000)
        box = loc.bounding_box()
        if box:
            self.glide(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)

    # -- actions -----------------------------------------------------------
    def run(self, a) -> None:
        p = self.page
        if isinstance(a, Goto):
            p.goto(a.url, wait_until="domcontentloaded", timeout=45000)
            self._after_nav()
        elif isinstance(a, Click):
            self.glide_to(a.selector)
            p.wait_for_timeout(120)
            p.locator(a.selector).first.click(timeout=10000)
            p.wait_for_timeout(250)
            self._after_nav()
        elif isinstance(a, TypeText):
            self.glide_to(a.selector)
            loc = p.locator(a.selector).first
            loc.click(timeout=10000)
            if a.clear:
                loc.fill("")
            text = os.environ[a.secret_env] if a.secret_env else a.text
            p.keyboard.type(text, delay=a.delay_ms)
        elif isinstance(a, Press):
            if a.selector:
                p.locator(a.selector).first.press(a.key)
            else:
                p.keyboard.press(a.key)
            p.wait_for_timeout(200)
            self._after_nav()
        elif isinstance(a, Hover):
            self.glide_to(a.selector)
            p.locator(a.selector).first.hover()
            p.wait_for_timeout(a.ms)
        elif isinstance(a, Scroll):
            if a.selector:
                p.locator(a.selector).first.evaluate(
                    "el => el.scrollIntoView({behavior:'smooth', block:'center'})")
            else:
                p.evaluate(f"window.scrollBy({{top:{a.y}, behavior:'smooth'}})")
            p.wait_for_timeout(a.ms)
        elif isinstance(a, Select):
            self.glide_to(a.selector)
            p.locator(a.selector).first.select_option(a.value)
        elif isinstance(a, Wait):
            p.wait_for_timeout(a.ms)
        elif isinstance(a, WaitFor):
            if a.selector:
                p.locator(a.selector).first.wait_for(state="visible", timeout=a.timeout_ms)
            if a.url_contains:
                p.wait_for_url(f"**{a.url_contains}**", timeout=a.timeout_ms)
        elif isinstance(a, Highlight):
            loc = p.locator(a.selector).first
            loc.wait_for(state="visible", timeout=15000)
            loc.scroll_into_view_if_needed()
            loc.evaluate(f"(el) => ({overlay.HIGHLIGHT_JS})([el, {a.ms}])")
            p.wait_for_timeout(a.ms + 300)
        elif isinstance(a, Title):
            p.set_content(overlay.title_html(a.heading, a.subheading))
            self._after_nav()
        else:  # pragma: no cover
            raise RecordingError(f"unsupported action {a!r}")

    def check(self, scene: Scene) -> None:
        e = scene.expect
        if not e:
            return
        p = self.page
        if e.url_contains and e.url_contains not in p.url:
            raise RecordingError(
                f"scene {scene.id}: expected URL to contain {e.url_contains!r}, got {p.url!r}")
        if e.selector_visible:
            try:
                p.locator(e.selector_visible).first.wait_for(state="visible", timeout=8000)
            except Exception as ex:
                raise RecordingError(
                    f"scene {scene.id}: {e.selector_visible!r} not visible") from ex
        if e.text_visible:
            try:
                p.get_by_text(e.text_visible).first.wait_for(state="visible", timeout=8000)
            except Exception as ex:
                raise RecordingError(
                    f"scene {scene.id}: text {e.text_visible!r} not visible") from ex


FLASH_DOC = "<html><body style='margin:0;background:%s'></body></html>"
PAINTED = "() => new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)))"


def _calibration_flash(page: Page, t0: float) -> float:
    """Show a white frame at a known wall-clock time. The renderer finds it in
    the video to measure the recorder's start offset, so narration lands on
    the exact frame its scene starts (trimmed out of the final video)."""
    page.set_content(FLASH_DOC % "#000")
    page.evaluate(PAINTED)
    page.wait_for_timeout(700)
    page.evaluate("() => { document.body.style.background = '#fff'; }")
    page.evaluate(PAINTED)
    flash = time.monotonic() - t0
    page.wait_for_timeout(400)
    page.set_content(FLASH_DOC % "#0b0f17")
    page.evaluate(PAINTED)
    page.wait_for_timeout(300)
    return round(flash, 3)


def _play_scenes(drv: _Driver, plan: Plan, durations: dict[str, float], t0: float,
                 raw: Path) -> list[dict]:
    timeline = []
    for scene in plan.scenes:
        start = time.monotonic() - t0
        drv.page.wait_for_timeout(scene.lead_in_s * 1000)
        try:
            for a in scene.actions:
                drv.run(a)
            drv.check(scene)
        except Exception as ex:
            try:
                drv.page.screenshot(path=str(raw / f"failure-{scene.id}.png"))
            except Exception:
                pass
            if isinstance(ex, RecordingError):
                raise
            raise RecordingError(f"scene {scene.id} failed: {ex}") from ex
        actions_end = time.monotonic() - t0
        target = start + max(durations[scene.id] + scene.pad_after_s, scene.min_duration_s)
        remaining = target - (time.monotonic() - t0)
        if remaining > 0:
            drv.page.wait_for_timeout(remaining * 1000)
        end = time.monotonic() - t0
        timeline.append({"id": scene.id, "start": round(start, 3), "end": round(end, 3),
                         "actions_end": round(actions_end, 3),
                         "narration": round(durations[scene.id], 3),
                         "overran": actions_end > start + durations[scene.id] + scene.pad_after_s})
        print(f"  scene {scene.id}: {start:6.2f}s → {end:6.2f}s"
              + ("  (actions overran narration)" if timeline[-1]["overran"] else ""))
    return timeline


def record(plan: Plan, durations: dict[str, float], out_dir: Path, s: Settings,
           allow_destructive: bool = False) -> dict:
    preflight(plan, durations, allow_destructive)
    raw = out_dir / "raw"
    if raw.exists():
        shutil.rmtree(raw)
    raw.mkdir(parents=True)
    if s.recorder == "obs":
        return _record_obs(plan, durations, raw, s)
    vw, vh = plan.viewport.width, plan.viewport.height
    result: dict = {"recorder": "playwright", "status": "failed"}
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=s.headless)
        ctx = browser.new_context(
            viewport={"width": vw, "height": vh},
            record_video_dir=str(raw / "tmp"),
            record_video_size={"width": vw, "height": vh},
            device_scale_factor=1,
            permissions=[],  # never grant camera/microphone
        )
        ctx.add_init_script(overlay.CURSOR_JS)
        if plan.redact:
            ctx.add_init_script(overlay.redact_js(plan.redact))
        page = ctx.new_page()
        t0 = time.monotonic()
        drv = _Driver(page, plan)
        error = None
        try:
            flash = _calibration_flash(page, t0)
            timeline = _play_scenes(drv, plan, durations, t0, raw)
            page.wait_for_timeout(800)
            result.update(status="ok", scenes=timeline, flash=flash,
                          end=round(time.monotonic() - t0, 3))
        except RecordingError as ex:
            error = ex
            result["error"] = str(ex)
        finally:
            video = page.video
            ctx.close()
            browser.close()
            src = Path(video.path()) if video else None
    if src and src.exists():
        dst = raw / "recording.webm"
        src.rename(dst)
        shutil.rmtree(raw / "tmp", ignore_errors=True)
        result["video"] = str(dst.relative_to(out_dir))
    (raw / "timeline.json").write_text(json.dumps(result, indent=2))
    if error:
        raise error
    return result


def _record_obs(plan: Plan, durations: dict[str, float], raw: Path, s: Settings) -> dict:
    """Headed browser captured by OBS (PipeWire screen capture on Wayland).
    OBS must be running with obs-websocket enabled and a scene that captures
    the screen (and NO camera source)."""
    from .obs_controller import OBS

    result: dict = {"recorder": "obs", "status": "failed"}
    obs = OBS(s.obs_host, s.obs_port, s.obs_password)
    obs.assert_no_camera()
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=False, args=["--start-fullscreen"])
        ctx = browser.new_context(no_viewport=True, permissions=[])
        ctx.add_init_script(overlay.CURSOR_JS)
        if plan.redact:
            ctx.add_init_script(overlay.redact_js(plan.redact))
        page = ctx.new_page()
        page.set_content("<html><body style='background:#0b0f17'></body></html>")
        page.wait_for_timeout(1500)
        obs.start()
        t0 = time.monotonic()
        error = None
        try:
            timeline = _play_scenes(_Driver(page, plan), plan, durations, t0, raw)
            page.wait_for_timeout(800)
            result.update(status="ok", scenes=timeline, end=round(time.monotonic() - t0, 3))
        except RecordingError as ex:
            error = ex
            result["error"] = str(ex)
        finally:
            path = obs.stop()
            ctx.close()
            browser.close()
    if path and Path(path).exists():
        dst = raw / ("recording" + Path(path).suffix)
        shutil.copy2(path, dst)
        result["video"] = str(dst.relative_to(raw.parent))
    (raw / "timeline.json").write_text(json.dumps(result, indent=2))
    if error:
        raise error
    return result
