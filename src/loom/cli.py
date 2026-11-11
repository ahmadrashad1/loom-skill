"""`loom` command line: setup, status, inspect, validate, voice, say, record, render, verify, run."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

from pydantic import ValidationError

from .config import RECORDINGS, load_settings
from .plan import Plan, load_plan


def resolve(target: str) -> Path:
    """Accept a slug, a recordings/<slug> dir, or a path to plan.json."""
    p = Path(target)
    if p.is_file():
        return p.parent
    if p.is_dir():
        return p
    if (RECORDINGS / target).is_dir():
        return RECORDINGS / target
    sys.exit(f"error: no recording directory or plan for {target!r}")


def _plan(d: Path) -> Plan:
    try:
        return load_plan(d / "plan.json")
    except FileNotFoundError:
        sys.exit(f"error: {d/'plan.json'} not found")
    except ValidationError as e:
        sys.exit(f"error: plan.json is invalid:\n{e}")


def _settings(args) -> object:
    return load_settings({
        "tts_provider": getattr(args, "provider", None),
        "recorder": getattr(args, "recorder", None),
        "headless": False if getattr(args, "headed", False) else None,
        "captions": getattr(args, "captions", None),
    })


# -- commands ----------------------------------------------------------------

INSTALL_HINTS = {
    "ffmpeg": "Fedora: sudo dnf install ffmpeg (RPM Fusion) · Ubuntu: sudo apt install ffmpeg · "
              "macOS: brew install ffmpeg",
}


def _playwright_ready() -> bool:
    import os
    cands = [os.environ.get("PLAYWRIGHT_BROWSERS_PATH"),
             Path.home() / ".cache" / "ms-playwright",
             Path.home() / "Library" / "Caches" / "ms-playwright"]
    return any(c and Path(c).is_dir() and any(Path(c).glob("chromium*")) for c in cands)


def _fish_voice(s) -> tuple[bool, str]:
    """Look up the configured voice model on Fish Audio."""
    import httpx
    try:
        r = httpx.get(f"https://api.fish.audio/model/{s.fish_reference_id}",
                      headers={"Authorization": f"Bearer {s.fish_api_key}"}, timeout=15)
    except Exception as e:
        return False, f"network error: {e}"
    if r.status_code != 200:
        return False, f"HTTP {r.status_code} {r.text[:100]}"
    j = r.json()
    author = (j.get("author") or {}).get("nickname", "?")
    return True, f"{j.get('title', '')!r} by {author} ({j.get('visibility', '?')})"


def cmd_status(args) -> int:
    from .config import CONFIG_DIR
    s = _settings(args)
    rows = []
    def row(name, ok, detail=""):
        rows.append((name, ok, detail))
    for tool in ("ffmpeg", "ffprobe"):
        row(tool, bool(shutil.which(tool)), shutil.which(tool) or INSTALL_HINTS["ffmpeg"])
    row("espeak-ng (preview voice)", bool(shutil.which("espeak-ng")), "optional")
    row("playwright chromium", _playwright_ready(), "" if _playwright_ready() else "run: loom setup")
    row("FISH_REFERENCE_ID", bool(s.fish_reference_id),
        s.fish_reference_id or "not set: your Fish Audio voice model id")
    row("FISH_API_KEY", bool(s.fish_api_key), "set" if s.fish_api_key else "not set")
    row("fish model", True, s.fish_model)
    row("tts provider", True, s.tts_provider)
    row("recorder", True, s.recorder)
    if s.recorder == "obs" or args.obs:
        try:
            from .obs_controller import OBS
            row("OBS websocket", True, OBS(s.obs_host, s.obs_port, s.obs_password).version())
        except Exception as e:
            row("OBS websocket", False, str(e).splitlines()[0])
    if args.fish and s.fish_api_key and s.fish_reference_id:
        row("Fish voice model", *_fish_voice(s))
    for name, ok, detail in rows:
        print(f"  {'✓' if ok else '✗'} {name:28} {detail}")
    configured = bool(s.fish_reference_id and s.fish_api_key)
    print(f"\n  config: {CONFIG_DIR}  ({'voice configured' if configured else 'VOICE NOT CONFIGURED'})")
    recs = sorted(RECORDINGS.glob("*/plan.json")) if RECORDINGS.exists() else []
    print(f"  recordings: {len(recs)} in {RECORDINGS}")
    for p in recs:
        d = p.parent
        state = "rendered" if (d / "final_video.mp4").exists() else (
            "recorded" if (d / "raw" / "timeline.json").exists() else (
                "voiced" if any((d / "narration").glob("*.wav")) else "planned"))
        rep = d / "report.json"
        if rep.exists():
            state += ", verify " + ("PASSED" if json.loads(rep.read_text())["passed"] else "FAILED")
        print(f"    - {d.name}: {state}")
    return 0


def cmd_setup(args) -> int:
    """Save the user's voice settings and install the browser."""
    import os
    import subprocess
    from .config import write_user_env
    updates = {"FISH_REFERENCE_ID": args.reference_id, "FISH_API_KEY": args.api_key,
               "FISH_MODEL": args.model, "LOOM_RECORDINGS": args.recordings}
    if any(updates.values()):
        path = write_user_env(updates)
        for k, v in updates.items():
            if v:
                os.environ[k] = v
        print(f"saved {', '.join(k for k, v in updates.items() if v)} to {path}")
        from dotenv import dotenv_values
        from .config import PLUGIN_ENV
        plugin = dotenv_values(PLUGIN_ENV) if PLUGIN_ENV.exists() else {}
        shadowed = [k for k, v in updates.items() if v and plugin.get(k) not in (None, v)]
        if shadowed:
            print(f"note: the plugin settings set {shadowed} differently and take precedence; "
                  "change them via /plugin → loom → Configure")
    if not args.skip_browser and not _playwright_ready():
        print("installing Playwright Chromium (one-time, ~150 MB)…")
        subprocess.run([sys.executable, "-m", "playwright", "install", "chromium"], check=True)
    missing = [t for t in ("ffmpeg", "ffprobe") if not shutil.which(t)]
    if missing:
        print(f"missing {missing}: {INSTALL_HINTS['ffmpeg']}")
    s = _settings(args)
    if s.fish_reference_id and s.fish_api_key:
        ok, detail = _fish_voice(s)
        print(f"voice model: {detail}" if ok else f"voice model check FAILED: {detail}")
        if not ok:
            return 1
    else:
        need = [n for n, v in (("voice model id", s.fish_reference_id),
                               ("API key", s.fish_api_key)) if not v]
        print(f"still needed: {', '.join(need)}")
        return 1
    print("ready." if not missing else "ready except FFmpeg.")
    return 0 if not missing else 1


def cmd_inspect(args) -> int:
    from .inspect import inspect
    out = Path(args.out) if args.out else RECORDINGS / "_inspect"
    info = inspect(args.url, out, full_page=args.full_page)
    print(f"{info['title']!r} — {info['url']}\nscreenshot: {info['screenshot']}\n")
    for e in info["elements"][: args.limit]:
        vis = " " if e["inViewport"] else "↓"
        print(f"  {vis} {e['role']:10} {e['name'][:40]:40} {e['selector']}")
    if len(info["elements"]) > args.limit:
        print(f"  … {len(info['elements']) - args.limit} more in {out/'elements.json'}")
    return 0


def cmd_validate(args) -> int:
    d = resolve(args.target)
    plan = _plan(d)
    words = sum(len(s.narration.split()) for s in plan.scenes)
    print(f"ok: {plan.title!r} — {len(plan.scenes)} scenes, {words} narration words "
          f"(~{words / 2.6:.0f}s), approved={plan.approved}")
    if plan.destructive_actions():
        print(f"  destructive actions: {plan.destructive_actions()}")
    if plan.secret_envs():
        print(f"  secrets from env: {plan.secret_envs()}")
    return 0


def _voice(plan: Plan, d: Path, s, only: list[str] | None, force: bool) -> dict[str, float]:
    from .tts import synthesize
    out = {}
    for sc in plan.scenes:
        wav = d / "narration" / f"{sc.id}.wav"
        if only and sc.id not in only:
            if wav.exists():
                out[sc.id] = json.loads(wav.with_suffix(".json").read_text())["duration"]
            continue
        meta = synthesize(sc.narration, wav, s, force=force)
        out[sc.id] = meta["duration"]
        print(f"  {sc.id}: {meta['duration']:6.2f}s {'(cached)' if meta['cached'] else ''}")
    return out


def _durations(plan: Plan, d: Path, s) -> dict[str, float]:
    from .tts import voice_key
    out = {}
    for sc in plan.scenes:
        meta = d / "narration" / f"{sc.id}.json"
        if meta.exists():
            m = json.loads(meta.read_text())
            if m.get("key") != voice_key(sc.narration, s):
                sys.exit(f"error: narration for scene {sc.id} is stale; run `loom voice`")
            out[sc.id] = m["duration"]
    return out


def cmd_voice(args) -> int:
    d = resolve(args.target)
    plan, s = _plan(d), _settings(args)
    print(f"narration via {s.tts_provider}:")
    _voice(plan, d, s, args.scene, args.force)
    return 0


def cmd_say(args) -> int:
    from .tts import synthesize
    s = _settings(args)
    out = Path(args.output)
    meta = synthesize(args.text, out, s, force=True)
    print(f"wrote {out} ({meta['duration']:.2f}s via {s.tts_provider})")
    return 0


def cmd_record(args) -> int:
    from .recorder import record
    d = resolve(args.target)
    plan, s = _plan(d), _settings(args)
    print(f"recording with {s.recorder}:")
    record(plan, _durations(plan, d, s), d, s, allow_destructive=args.allow_destructive)
    print(f"  raw recording: {d/'raw'}")
    return 0


def cmd_render(args) -> int:
    from .renderer import render
    d = resolve(args.target)
    final = render(_plan(d), d, _settings(args))
    print(f"rendered {final}")
    return 0


def cmd_verify(args) -> int:
    from .verify import verify
    d = resolve(args.target)
    rep = verify(_plan(d), d, _settings(args))
    for c in rep["checks"]:
        mark = "✓" if c["ok"] else ("!" if c["warn_only"] else "✗")
        print(f"  {mark} {c['check']:30} {c['detail']}")
    print(f"\n{'PASSED' if rep['passed'] else 'FAILED'} — thumbnails: {', '.join(rep['thumbnails'])}")
    return 0 if rep["passed"] else 1


def cmd_run(args) -> int:
    from .recorder import record
    from .renderer import render
    d = resolve(args.target)
    plan, s = _plan(d), _settings(args)
    print(f"[1/4] narration via {s.tts_provider}")
    durations = _voice(plan, d, s, None, args.force_voice)
    print(f"[2/4] recording with {s.recorder}")
    record(plan, durations, d, s, allow_destructive=args.allow_destructive)
    print("[3/4] rendering")
    render(plan, d, s)
    print("[4/4] verifying")
    return cmd_verify(args)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="loom", description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)

    def add(name, fn, target=True, **kw):
        p = sub.add_parser(name, **kw)
        if target:
            p.add_argument("target", help="slug, recordings/<slug> or plan.json")
        p.set_defaults(fn=fn)
        return p

    p = add("status", cmd_status, target=False, help="check the pipeline")
    p.add_argument("--fish", action="store_true", help="also call the Fish Audio API")
    p.add_argument("--obs", action="store_true", help="also check the OBS websocket")
    p = add("setup", cmd_setup, target=False, help="save voice settings, install browser")
    p.add_argument("--reference-id", help="your Fish Audio voice model id")
    p.add_argument("--api-key", help="Fish Audio API key (prefer the plugin settings dialog)")
    p.add_argument("--model", help="Fish model, e.g. s2.1-pro or s2.1-pro-free")
    p.add_argument("--recordings", help="where videos are saved (default ~/Videos/loom)")
    p.add_argument("--skip-browser", action="store_true")
    p = add("inspect", cmd_inspect, target=False, help="screenshot a page and list selectors")
    p.add_argument("url")
    p.add_argument("--out", help="output dir (default recordings/_inspect)")
    p.add_argument("--full-page", action="store_true")
    p.add_argument("--limit", type=int, default=80)
    add("validate", cmd_validate, help="validate plan.json")
    for name, fn in (("voice", cmd_voice),):
        p = add(name, fn, help="generate scene narration")
        p.add_argument("--scene", action="append", help="only this scene id (repeatable)")
        p.add_argument("--force", action="store_true", help="regenerate even if cached")
        p.add_argument("--provider", choices=["fish", "espeak", "silent"])
    p = add("say", cmd_say, target=False, help="speak arbitrary text to a file")
    p.add_argument("text")
    p.add_argument("-o", "--output", default="say.wav")
    p.add_argument("--provider", choices=["fish", "espeak", "silent"])
    for name, fn in (("record", cmd_record), ("run", cmd_run)):
        p = add(name, fn, help="record the demonstration" if name == "record"
                else "voice → record → render → verify")
        p.add_argument("--allow-destructive", action="store_true")
        p.add_argument("--headed", action="store_true", help="show the browser window")
        p.add_argument("--recorder", choices=["playwright", "obs"])
        p.add_argument("--provider", choices=["fish", "espeak", "silent"])
        if name == "run":
            p.add_argument("--force-voice", action="store_true")
            p.add_argument("--captions", choices=["soft", "burn", "none"])
    p = add("render", cmd_render, help="produce final_video.mp4")
    p.add_argument("--captions", choices=["soft", "burn", "none"])
    p.add_argument("--provider", choices=["fish", "espeak", "silent"])
    p = add("verify", cmd_verify, help="quality-check final_video.mp4")
    p.add_argument("--captions", choices=["soft", "burn", "none"])
    p.add_argument("--provider", choices=["fish", "espeak", "silent"])

    args = ap.parse_args(argv)
    try:
        return args.fn(args)
    except KeyboardInterrupt:
        return 130
    except Exception as e:  # surface pipeline errors cleanly
        from .media import MediaError
        from .tts import TTSError
        known = (MediaError, TTSError)
        try:
            from .recorder import RecordingError
            from .renderer import RenderError
            known += (RecordingError, RenderError)
        except Exception:
            pass
        if isinstance(e, known):
            print(f"error: {e}", file=sys.stderr)
            return 2
        raise


if __name__ == "__main__":
    sys.exit(main())
