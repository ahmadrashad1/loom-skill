# Loom: narrated demo videos for Claude Code

**Install** (run inside Claude Code):

```
/plugin marketplace add ahmadrashad1/loom-skill
/plugin install loom@loom-skill
/plugin configure loom@loom-skill
```

The last command asks for your Fish Audio voice model ID and API key. Then
start a new session and run `/loom:setup`. Details are under
[Install](#install).

A Claude Code plugin that makes Loom-style walkthrough videos for you. Describe
the demo, approve the plan, and get back a captioned 1080p MP4: performed in
a real browser and narrated in **your own cloned voice** (Fish Audio). No
webcam, no microphone, no editing.

```
/loom:video Show how to add a task in Taskboard at https://app.example.com
```

## Install

In Claude Code:

```
/plugin marketplace add ahmadrashad1/loom-skill
/plugin install loom@loom-skill
```

Then enter your settings with `/plugin configure loom@loom-skill`:

| Setting | What to enter |
|---|---|
| **Fish Audio voice model ID** (required) | the ID of *your* cloned voice on [fish.audio](https://fish.audio): the hex string in the model page's URL |
| **Fish Audio API key** | fish.audio → Developers → API keys. Stored in your system's secure storage. Leave blank if `FISH_API_KEY` is already set in your environment |
| **Speech model** | `s2.1-pro` (needs Fish *API* credit) or `s2.1-pro-free` (free tier) |

Start a new session after configuring, then run `/loom:setup`. It installs
the headless browser (~150 MB, once), checks FFmpeg, and confirms your voice
model. Change settings any time with `/plugin configure loom@loom-skill`.
From a shell, `claude plugin install loom@loom-skill --config fish_reference_id=<ID>`
works too.

**Requirements:**
- [uv](https://docs.astral.sh/uv/) (`curl -LsSf https://astral.sh/uv/install.sh | sh`). The plugin's Python environment is created automatically on first use.
- FFmpeg with libx264: `sudo dnf install ffmpeg` (Fedora, RPM Fusion) · `sudo apt install ffmpeg` · `brew install ffmpeg`.
- Linux or macOS.

### Make your voice model
1. Record a few minutes of clean, natural speech in a quiet room, in the voice
   you'd use for a presentation.
2. On fish.audio, create a voice model from those recordings. Consider
   keeping it **private**, so nobody else can generate speech in your voice.
3. Copy its ID into the plugin settings.

Only use a voice you own or have explicit permission to use.

## Skills

| | |
|---|---|
| `/loom:video <task or slug>` | full workflow: plan → you approve → narrate → record → render → verify |
| `/loom:plan <task>` | write a plan for review without recording |
| `/loom:voice <text or slug>` | generate narration in your voice |
| `/loom:retry <slug>` | diagnose a failed or weak video and remake it |
| `/loom:status` | pipeline health and your recordings |
| `/loom:setup` | configure your voice, install the browser |

Videos are saved to `~/Videos/loom/<slug>/` (set `LOOM_RECORDINGS` to change):

```
plan.json            the approved demonstration plan
narration/01.wav     per-scene voice + metadata (duration, cache key)
raw/recording.webm   untouched original take + timeline.json
subtitles/captions.srt
scenes/01.jpg        one frame per scene, for review
final_video.mp4      1920×1080 · 30 fps · H.264/AAC · −16 LUFS · captions
report.json          verification results
```

> VS Code's built-in preview plays MP4 video without sound (it can't decode
> AAC). Open videos in a normal player or browser.

## How it works

```
plan.json ──► loom voice ──► loom record ──► loom render ──► loom verify
 (Claude)     Fish Audio     Playwright       FFmpeg          quality gate
```

- **Scene-based sync.** Narration is generated first, so each scene's exact
  length is known. The browser performs a scene's actions while its narration
  would play, then holds until the narration has finished. A calibration
  flash at the start of each take measures the recorder's offset, so the
  voice lands within about one frame.
- **Real footage only.** Each scene can declare an `expect` check (an element,
  text or URL). If it fails, the take aborts and nothing is rendered.
- **Safeguards in code:**
  - Unapproved plans aren't recorded.
  - Actions marked `destructive` need `--allow-destructive`.
  - Typed secrets come from environment variables.
  - `redact` selectors are blurred.
  - The browser gets no camera or mic access.
  - `verify` fails on missing audio, clipping, cut-off narration or mismatched captions.

### Where settings live
Claude Code stores the plugin settings. A session-start hook copies them to
`~/.config/loom/plugin.env` (mode 600) so the `loom` command can read them.
`loom setup --reference-id …` writes `~/.config/loom/config.env` instead.
Precedence, highest first: environment variables, then plugin settings, then
`loom setup`.

## CLI

The plugin puts a `loom` command on Claude's PATH:

| | |
|---|---|
| `loom setup [--reference-id ID] [--model M]` | save settings, install Chromium, check FFmpeg and voice |
| `loom status [--fish] [--obs]` | check tools and keys, list recordings |
| `loom inspect <url>` | screenshot + selectors for planning |
| `loom validate <slug>` | validate a plan |
| `loom voice <slug> [--scene ID] [--force]` | per-scene narration (cached) |
| `loom say "<text>" -o out.wav` | speak arbitrary text |
| `loom record <slug> [--headed] [--allow-destructive]` | perform and record |
| `loom render <slug> [--captions soft\|burn\|none]` | produce `final_video.mp4` |
| `loom verify <slug>` | quality checks |
| `loom run <slug>` | voice → record → render → verify |

`--provider espeak|silent` swaps in an offline robotic voice or silence for
previews and dry runs.

## Development

```bash
git clone https://github.com/ahmadrashad1/loom-skill && cd loom-skill
uv sync && uv run playwright install chromium
uv run pytest                          # -m "not slow" skips browser/video tests
claude --plugin-dir .                  # load the plugin from this checkout
claude plugin validate .
```

- **Layout:** `src/loom/` (engine), `skills/` (Claude Code skills),
  `.claude-plugin/` (manifest and marketplace), `bin/loom` (CLI wrapper),
  `hooks/` (settings sync).
- **Plan schema:** the source of truth is `src/loom/plan.py`, documented in
  `skills/video/reference/plan-schema.md`.
- **Recorder timing:** if you change it, keep the calibration flash intact
  (`recorder._calibration_flash` and `renderer.video_offset`). It's what keeps
  narration in sync.

## Limits

- Browser demos are tested end to end. OBS desktop recording
  (`--recorder obs`) is implemented but experimental, and native-app
  automation on Wayland isn't supported.
- A retry re-records the whole take. Narration for unchanged scenes is reused
  from cache.
- Captions come from the narration script, timed within each clip, not from
  speech recognition.

MIT licensed.
