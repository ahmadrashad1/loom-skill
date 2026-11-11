---
name: video
description: Produce a finished, narrated Loom-style screen-recording video (MP4, 1080p, the user's own cloned voice via Fish Audio, captions, no webcam) that demonstrates a website or web app. Use when the user runs /loom:video or asks to record, demo, or make a walkthrough/tutorial video of an application.
argument-hint: <what to demonstrate>
---

# Narrated demo video

You plan and drive the demonstration. The `loom` command (on your PATH
while this plugin is enabled) handles narration, recording, rendering and
verification. Run it as plain `loom …` from any directory. Videos are saved
under the recordings folder shown by `loom status` (default `~/Videos/loom/<slug>/`).
Below, `<rec>` means that folder.

Request: **$ARGUMENTS**

If the request is the slug of an existing recording (`loom status` lists
them), resume it from its first unfinished step below. An unapproved plan
still needs approval.

## Non-negotiable rules

1. **Never record an unapproved plan.** Write the plan with `"approved": false`,
   show it to the user, and set it to `true` only after they approve (or they
   explicitly said to go ahead without review).
2. **Destructive or irreversible actions** (delete, purchase, deploy, send,
   payment, changing production settings) must be marked `"destructive": true`
   and need the user's explicit OK for *this* video before passing
   `--allow-destructive`.
3. **No secrets in plan.json or narration.** Typed passwords/tokens use
   `"secret_env": "VAR"`; on-screen keys, emails, tokens, account numbers go
   in `"redact"` (CSS selectors, blurred for the whole video). Never print
   the contents of `~/.config/loom/*.env`.
4. **No fabricated footage.** Every scene must be performed for real by the
   recorder. If a scene fails, fix the plan and re-record. Never fake a
   result, and never present a video whose `loom verify` failed as finished.
5. **No webcam, own voice only.** Narration uses the user's own Fish Audio
   voice model. Never use or suggest someone else's voice without their
   permission.

## Workflow

### 0. Voice setup (first run)
Run `loom status`. If it says **VOICE NOT CONFIGURED**, set up the voice
before anything else; follow the `/loom:setup` skill
(`${CLAUDE_PLUGIN_ROOT}/skills/setup/SKILL.md`). Ask the user for their own
Fish Audio voice model ID; never invent or reuse one. If they don't want to
set it up now, you may continue with `--provider espeak` as a robotic
*preview* voice, and say clearly that it is not their voice.

### A. Understand
Work out: which app/URL, the outcome the viewer should achieve, the audience,
and whether login is required. If one of these is genuinely unclear, ask one
concise question; otherwise proceed with sensible assumptions and state them.

### B. Inspect the real app
```
loom inspect <url> --out <rec>/<slug>/inspect
```
Read the screenshot (`<rec>/<slug>/inspect/page.png`) and use the printed
selectors. Inspect every page the demo will visit (follow the flow) so that
selectors are real, not guessed. Prefer `#id`, `[data-testid=…]`, then
`role=button[name="…"]`, then `text=…`. Local files work as `file:///…` URLs.

### C. Write the plan
Create `<rec>/<slug>/plan.json` following
`${CLAUDE_PLUGIN_ROOT}/skills/video/reference/plan-schema.md`. Guidelines:
- 4–10 scenes; open with a `title` scene, end with a short recap scene.
- Narration: first person, conversational, like a colleague recording a Loom.
  1–3 sentences per scene (≈ 6–20 s). Describe what the viewer sees *as* it
  happens; don't read out selectors or URLs character by character.
- Actions run while that scene's narration plays; keep them short enough to
  fit (≈ 2.6 words per second of speech). Split long flows into more scenes.
- Add `expect` to every scene that changes state, so failures are caught.
- `loom validate <slug>` until it passes.

Present the plan to the user as a table (scene · what happens on screen ·
narration) plus anything destructive, any secrets needed, and the estimated
length. Stop and wait for approval. On approval set `"approved": true`.

### D. Narrate
`loom voice <slug>`: one WAV per scene in the cloned voice (cached; only
changed scenes regenerate). Check the durations look sane.

### E. Record
`loom record <slug>` (add `--allow-destructive` only per rule 2).
If it fails, read the error and `<rec>/<slug>/raw/failure-<scene>.png`,
fix selectors/waits in the plan, and re-run. Re-inspect pages if needed.

### F. Produce
`loom render <slug>` (`--captions burn` if the user wants burned-in
captions; default is an embedded subtitle track plus `subtitles/captions.srt`).

### G. Verify (always)
`loom verify <slug>`, then **look at every thumbnail** in
`<rec>/<slug>/scenes/*.jpg` with the Read tool: is the expected screen state
visible, is anything sensitive left unredacted, are there error pages or cookie banners
covering content? If a warning says actions outran narration, consider
splitting that scene. Fix and redo the necessary steps until it passes.

### H. Report
Give the path to `<rec>/<slug>/final_video.mp4`, its length, the scene list,
and any caveats (e.g. preview voice used). Mention that VS Code's built-in
preview plays MP4s without sound; use a normal video player. Shortcut for
steps D–G once a plan is approved: `loom run <slug>`.

## Troubleshooting
- `loom: command not found` → the plugin's `bin/` isn't on PATH; run
  `${CLAUDE_PLUGIN_ROOT}/bin/loom` instead.
- `loom needs uv` → tell the user to install uv (command is printed).
- Element not found → re-run `loom inspect` on that page; add `wait_for`.
- Cookie/consent banner → add a first-scene `click` on its accept button.
- Login → `type` with `secret_env`; ask the user to export the variable.
- Fish Audio 401 → bad API key. 402 → no API credit for that model; suggest
  adding credit or switching the plugin's model setting to `s2.1-pro-free`.
- Desktop (non-browser) demos → `--recorder obs` (OBS must be running with
  WebSocket enabled and a screen-capture scene). This path is experimental.
