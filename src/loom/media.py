"""Thin FFmpeg/ffprobe helpers."""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path


class MediaError(RuntimeError):
    pass


def run(cmd: list[str]) -> subprocess.CompletedProcess:
    p = subprocess.run(cmd, capture_output=True, text=True)
    if p.returncode != 0:
        tail = "\n".join(p.stderr.strip().splitlines()[-15:])
        raise MediaError(f"{cmd[0]} failed ({p.returncode}):\n{tail}")
    return p


def ffmpeg(*args: str) -> subprocess.CompletedProcess:
    return run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", *args])


def probe(path: Path) -> dict:
    p = run(["ffprobe", "-v", "error", "-print_format", "json",
             "-show_format", "-show_streams", str(path)])
    return json.loads(p.stdout)


def duration(path: Path) -> float:
    info = probe(path)
    d = info.get("format", {}).get("duration")
    if d is None:
        raise MediaError(f"no duration for {path}")
    return float(d)


def volume_stats(path: Path) -> dict:
    p = subprocess.run(
        ["ffmpeg", "-hide_banner", "-nostats", "-i", str(path), "-vn",
         "-af", "volumedetect", "-f", "null", "-"],
        capture_output=True, text=True,
    )
    out = {}
    for key in ("mean_volume", "max_volume"):
        m = re.search(rf"{key}:\s*(-?[\d.]+|-inf) dB", p.stderr)
        if m:
            out[key] = float("-inf") if m.group(1) == "-inf" else float(m.group(1))
    return out
