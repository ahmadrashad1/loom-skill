---
name: status
description: Check the loom video pipeline (FFmpeg, Playwright, Fish Audio keys, OBS) and list recordings with their state. Use for /loom:status.
---

Run `loom status --fish` (add `--obs` if the user uses OBS) and
summarise: what's ready, what's missing with the exact fix (voice not configured → follow
`${CLAUDE_PLUGIN_ROOT}/skills/setup/SKILL.md`), and each recording's state (planned → voiced →
recorded → rendered, verify passed/failed). Never print secret values.
