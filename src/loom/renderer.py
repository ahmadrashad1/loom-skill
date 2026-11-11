"""Final video production with FFmpeg.

raw/recording.webm + narration/*.wav + raw/timeline.json →
final_video.mp4 (1080p30 H.264/AAC, loudness-normalised narration, captions).
The raw recording is left untouched.
"""

from __future__ import annotations

import json
from pathlib import Path

from .captions import build_cues, to_srt
from .config import Settings
import re
import subprocess

from .media import duration, ffmpeg
from .plan import Plan


class RenderError(RuntimeError):
    pass


def load_timeline(out_dir: Path) -> dict:
    f = out_dir / "raw" / "timeline.json"
    if not f.exists():
        raise RenderError("no raw/timeline.json; run `loom record` first")
    tl = json.loads(f.read_text())
    if tl.get("status") != "ok":
        raise RenderError(f"recording did not complete: {tl.get('error')}")
    return tl


def find_flash(video: Path, search_s: float = 6.0) -> float | None:
    """Timestamp of the first (near-)white frame: the calibration flash."""
    p = subprocess.run(
        ["ffmpeg", "-hide_banner", "-nostats", "-t", str(search_s), "-i", str(video),
         "-vf", "scale=64:-2,signalstats,metadata=print:key=lavfi.signalstats.YAVG",
         "-f", "null", "-"], capture_output=True, text=True)
    pts = None
    for line in p.stderr.splitlines():
        m = re.search(r"pts_time:([\d.]+)", line)
        if m:
            pts = float(m.group(1))
        m = re.search(r"YAVG=([\d.]+)", line)
        if m and pts is not None and float(m.group(1)) > 200:
            return pts
    return None


def video_offset(video: Path, tl: dict) -> float:
    """Seconds to add to wall-clock timeline values to get video timestamps."""
    if "flash" not in tl:
        return 0.0
    pts = find_flash(video)
    if pts is None:
        raise RenderError("calibration flash not found in the recording")
    return pts - tl["flash"]


def _sub_escape(p: Path) -> str:
    return str(p).replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'")


def render(plan: Plan, out_dir: Path, s: Settings, captions: str | None = None) -> Path:
    captions = captions or s.captions
    tl = load_timeline(out_dir)
    video = out_dir / tl["video"]
    offset = video_offset(video, tl)
    scenes = [dict(sc, start=sc["start"] + offset, actions_end=sc["actions_end"] + offset)
              for sc in tl["scenes"]]
    trim = max(0.0, scenes[0]["start"])
    dur = min(tl["end"] + offset, duration(video)) - trim
    W, H, fps, fade = s.width, s.height, s.fps, s.fade_s

    narr_dir = out_dir / "narration"
    clips = []
    for sc in scenes:
        wav = narr_dir / f"{sc['id']}.wav"
        if not wav.exists():
            raise RenderError(f"missing narration {wav}")
        clips.append((wav, sc["start"] - trim))

    # captions
    text_by_id = {sc.id: sc.narration for sc in plan.scenes}
    cues = build_cues([(sc["start"] - trim, sc["narration"], text_by_id[sc["id"]])
                       for sc in scenes])
    subs_dir = out_dir / "subtitles"
    subs_dir.mkdir(exist_ok=True)
    srt = subs_dir / "captions.srt"
    srt.write_text(to_srt(cues))

    args = ["-ss", f"{trim:.3f}", "-i", str(video)]
    for wav, _ in clips:
        args += ["-i", str(wav)]
    if captions == "soft":
        args += ["-i", str(srt)]

    vf = (f"[0:v]fps={fps},scale={W}:{H}:force_original_aspect_ratio=decrease:flags=lanczos,"
          f"pad={W}:{H}:(ow-iw)/2:(oh-ih)/2:color=black,setsar=1,format=yuv420p")
    if fade > 0:
        vf += f",fade=t=in:st=0:d={fade},fade=t=out:st={max(0, dur - fade):.3f}:d={fade}"
    if captions == "burn":
        vf += (f",subtitles='{_sub_escape(srt)}':force_style='FontName=Cantarell,FontSize=20,"
               "PrimaryColour=&H00FFFFFF,OutlineColour=&H80000000,BorderStyle=3,Outline=1,"
               "Shadow=0,MarginV=36'")
    parts = [vf + "[v]"]
    labels = []
    for i, (_, at) in enumerate(clips, start=1):
        ms = max(0, int(round(at * 1000)))
        parts.append(f"[{i}:a]aresample=48000,adelay={ms}:all=1[a{i}]")
        labels.append(f"[a{i}]")
    parts.append(
        f"{''.join(labels)}amix=inputs={len(labels)}:normalize=0:dropout_transition=0,"
        f"loudnorm=I={s.loudness_i}:TP={s.loudness_tp}:LRA=11,aresample=48000,"
        f"apad,atrim=0:{dur:.3f}[a]")
    args += ["-filter_complex", ";".join(parts), "-map", "[v]", "-map", "[a]"]

    if captions == "soft":
        sub_idx = len(clips) + 1
        args += ["-map", f"{sub_idx}:s", "-c:s", "mov_text", "-metadata:s:s:0", "language=eng"]

    final = out_dir / "final_video.mp4"
    args += ["-t", f"{dur:.3f}",
             "-c:v", "libx264", "-preset", s.preset, "-crf", str(s.crf), "-r", str(fps),
             "-profile:v", "high", "-pix_fmt", "yuv420p",
             "-c:a", "aac", "-b:a", s.audio_bitrate, "-ar", "48000",
             "-metadata", f"title={plan.title}", "-movflags", "+faststart", str(final)]
    ffmpeg(*args)

    # scene thumbnails at the end of each scene's actions, for visual review
    thumbs = out_dir / "scenes"
    thumbs.mkdir(exist_ok=True)
    for sc in scenes:
        t = min(max(sc["actions_end"], sc["start"] + 0.5) - trim, dur - 0.1)
        ffmpeg("-ss", f"{max(0, t):.3f}", "-i", str(final), "-frames:v", "1",
               "-vf", "scale=960:-2", "-q:v", "3", str(thumbs / f"{sc['id']}.jpg"))
    return final
