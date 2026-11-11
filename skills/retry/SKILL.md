---
name: retry
description: Diagnose and fix a failed or unsatisfactory demo recording, then regenerate it. Use for /loom:retry or when a loom run/verify failed.
argument-hint: <slug> [what to change]
---

Recording: **$ARGUMENTS**

1. Read `<rec>/<slug>/raw/timeline.json` (error), `report.json` (failed
   checks), any `raw/failure-*.png`, and the scene thumbnails.
2. Find the cause: wrong selector → `loom inspect <url>`; slow page →
   `wait_for`; narration/pacing → edit narration or split the scene.
3. Edit `plan.json`. If you changed what happens on screen or added
   destructive actions, show the user the diff and get approval again.
4. `loom voice <slug>` (only changed scenes regenerate) →
   `loom record <slug>` → `render` → `verify`, then review thumbnails.
   The whole video is re-recorded because scenes share one continuous take.
5. Report what was wrong, what changed, and the verify result.
