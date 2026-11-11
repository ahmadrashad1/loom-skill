"""Automated quality gate for a finished video. A failing check means the
video must not be presented as finished."""

from __future__ import annotations

import json
import re
from pathlib import Path

from .captions import parse_srt
from .config import Settings
from .media import MediaError, probe, volume_stats
from .plan import Plan


def _words(t: str) -> list[str]:
    return re.findall(r"[a-z0-9']+", t.lower())


def verify(plan: Plan, out_dir: Path, s: Settings) -> dict:
    checks: list[dict] = []

    def check(name: str, ok: bool, detail: str = "", warn: bool = False):
        checks.append({"check": name, "ok": bool(ok), "warn_only": warn, "detail": detail})

    final = out_dir / "final_video.mp4"
    tl_path = out_dir / "raw" / "timeline.json"
    tl = json.loads(tl_path.read_text()) if tl_path.exists() else {}
    check("recording completed", tl.get("status") == "ok", tl.get("error", ""))
    check("raw recording preserved", bool(tl.get("video")) and (out_dir / tl.get("video", "x")).exists())
    if not final.exists():
        check("final video exists", False, str(final))
        return _report(out_dir, checks)
    try:
        info = probe(final)
    except MediaError as e:
        check("final video playable", False, str(e))
        return _report(out_dir, checks)
    check("final video playable", True)

    streams = info["streams"]
    v = [x for x in streams if x["codec_type"] == "video"]
    a = [x for x in streams if x["codec_type"] == "audio"]
    sub = [x for x in streams if x["codec_type"] == "subtitle"]
    dur = float(info["format"]["duration"])
    check("one video stream (H.264)", len(v) == 1 and v[0]["codec_name"] == "h264",
          v[0]["codec_name"] if v else "none")
    if v:
        w, h = v[0]["width"], v[0]["height"]
        check("resolution", (w, h) == (s.width, s.height), f"{w}x{h}")
        num, den = map(int, v[0]["avg_frame_rate"].split("/"))
        fps = num / den if den else 0
        check("frame rate", abs(fps - s.fps) < 0.5, f"{fps:.2f}")
    check("audio stream present (AAC)", len(a) == 1 and a[0]["codec_name"] == "aac",
          a[0]["codec_name"] if a else "none")
    if s.captions == "soft":
        check("embedded subtitles", len(sub) >= 1)

    scenes = tl.get("scenes", [])
    if scenes:
        trim = scenes[0]["start"]
        last = max(sc["start"] - trim + sc["narration"] for sc in scenes)
        check("narration not cut off", last <= dur + 0.05,
              f"last narration ends {last:.2f}s, video {dur:.2f}s")
        over = [sc["id"] for sc in scenes if sc.get("overran")]
        check("actions fit narration", not over,
              f"scenes where actions outlasted narration: {over}" if over else "", warn=True)
        check("all planned scenes recorded",
              [sc["id"] for sc in scenes] == [sc.id for sc in plan.scenes])

    vol = volume_stats(final)
    mx, mean = vol.get("max_volume", 0.0), vol.get("mean_volume", float("-inf"))
    check("no clipping", mx <= -0.1, f"peak {mx} dB")
    silent_ok = s.tts_provider == "silent"
    check("narration audible", silent_ok or mean > -40, f"mean {mean} dB", warn=silent_ok)

    srt = out_dir / "subtitles" / "captions.srt"
    if srt.exists():
        cues = parse_srt(srt.read_text())
        cap_words = _words(" ".join(c[2] for c in cues))
        narr_words = _words(" ".join(sc.narration for sc in plan.scenes))
        check("captions match narration", cap_words == narr_words,
              f"{len(cues)} cues, {len(cap_words)} words")
        check("captions within video", all(b <= dur + 0.05 for _, b, _ in cues))
    elif s.captions != "none":
        check("captions file", False, "missing subtitles/captions.srt")

    check("no webcam source", tl.get("recorder") in ("playwright", "obs"),
          "playwright records the browser viewport only; obs is checked for camera sources")
    return _report(out_dir, checks)


def _report(out_dir: Path, checks: list[dict]) -> dict:
    passed = all(c["ok"] or c["warn_only"] for c in checks)
    thumbs = sorted(str(p.relative_to(out_dir)) for p in (out_dir / "scenes").glob("*.jpg")) \
        if (out_dir / "scenes").exists() else []
    report = {"passed": passed, "checks": checks, "thumbnails": thumbs}
    (out_dir / "report.json").write_text(json.dumps(report, indent=2))
    return report
