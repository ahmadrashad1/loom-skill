---
name: plan
description: Prepare and review a narrated demo-video plan (plan.json) without recording anything. Use for /loom:plan or when the user wants to see a video plan first.
argument-hint: <what to demonstrate>
---

Follow steps **A–C** of the `/loom:video` skill (`${CLAUDE_PLUGIN_ROOT}/skills/video/SKILL.md`) for:
**$ARGUMENTS**

Write `<rec>/<slug>/plan.json` with `"approved": false`, run
`loom validate <slug>`, and present the scene table, destructive
actions, required secrets and estimated length. Do **not** run voice, record
or render. Tell the user they can approve it and run `/loom:video <slug>` (or
`loom run <slug>` after setting `"approved": true`).
