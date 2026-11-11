"""SRT captions built from the narration script and the recording timeline.

Each scene's narration is split into caption-sized chunks, and the scene's
measured audio duration is shared between them in proportion to their length.
Since the narration text is the exact TTS input, captions always match.
"""

from __future__ import annotations

import re
import textwrap

MAX_CHARS = 84  # two lines of 42


def chunk_text(text: str, max_chars: int = MAX_CHARS) -> list[str]:
    sentences = re.split(r"(?<=[.!?])\s+", " ".join(text.split()))
    chunks: list[str] = []
    for sent in filter(None, sentences):
        if len(sent) <= max_chars:
            chunks.append(sent)
            continue
        # split long sentences at clause boundaries, then at words
        parts = re.split(r"(?<=[,;:])\s+", sent)
        cur = ""
        for part in parts:
            for piece in textwrap.wrap(part, max_chars) or [part]:
                if cur and len(cur) + 1 + len(piece) > max_chars:
                    chunks.append(cur)
                    cur = piece
                else:
                    cur = f"{cur} {piece}".strip()
        if cur:
            chunks.append(cur)
    return chunks


def _ts(t: float) -> str:
    t = max(0.0, t)
    ms = int(round(t * 1000))
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    sec, ms = divmod(ms, 1000)
    return f"{h:02}:{m:02}:{sec:02},{ms:03}"


def build_cues(items: list[tuple[float, float, str]]) -> list[tuple[float, float, str]]:
    """items: (start, narration_duration, text) per scene → (start, end, text) cues."""
    cues = []
    for start, dur, text in items:
        chunks = chunk_text(text)
        total = sum(len(c) for c in chunks) or 1
        t = start
        for c in chunks:
            d = dur * len(c) / total
            cues.append((t, t + d, c))
            t += d
    return cues


def to_srt(cues: list[tuple[float, float, str]]) -> str:
    out = []
    for i, (a, b, text) in enumerate(cues, 1):
        lines = "\n".join(textwrap.wrap(text, 42)) if len(text) > 42 else text
        out.append(f"{i}\n{_ts(a)} --> {_ts(b)}\n{lines}\n")
    return "\n".join(out)


def parse_srt(srt: str) -> list[tuple[float, float, str]]:
    cues = []
    for block in re.split(r"\n\s*\n", srt.strip()):
        lines = block.strip().splitlines()
        if len(lines) < 3:
            continue
        m = re.match(r"(\d+):(\d+):(\d+),(\d+) --> (\d+):(\d+):(\d+),(\d+)", lines[1])
        if not m:
            continue
        g = list(map(int, m.groups()))
        a = g[0] * 3600 + g[1] * 60 + g[2] + g[3] / 1000
        b = g[4] * 3600 + g[5] * 60 + g[6] + g[7] / 1000
        cues.append((a, b, " ".join(lines[2:])))
    return cues
