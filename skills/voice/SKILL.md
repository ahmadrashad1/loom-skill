---
name: voice
description: Generate narration audio in the user's cloned Fish Audio voice from text, or (re)generate narration for a recording's scenes. Use for /loom:voice.
argument-hint: <text> | <slug> [scene ids]
---

Input: **$ARGUMENTS**

- If it names an existing recording (`<rec>/<slug>/plan.json`): run
  `loom voice <slug>` (add `--scene <id>` per scene and `--force` to
  regenerate specific scenes). Report each scene's duration.
- Otherwise treat it as text to speak:
  `loom say "<text>" -o ~/Videos/loom/_voice/<short-name>.wav` and report
  the file path and duration.

If `loom status` shows Fish Audio keys missing, say so; only use
`--provider espeak` if the user accepts a non-cloned preview voice. Never use a
voice model other than the user's own `FISH_REFERENCE_ID`.
