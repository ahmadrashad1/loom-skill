---
name: setup
description: Configure the loom plugin for this user. Asks for their own Fish Audio voice model ID (and API key if missing), installs the browser, and checks FFmpeg. Use for /loom:setup, on first use, or when `loom status` says VOICE NOT CONFIGURED.
---

# Loom setup

Every user narrates with **their own** cloned voice, so each person
configures their own voice model ID. Run `loom status` first and only fix
what's missing.

1. **Voice model ID.** If `FISH_REFERENCE_ID` isn't set, ask the user:
   "What's your Fish Audio voice model ID?" Explain where to find it: on
   fish.audio, create a voice model from a few minutes of clean recordings of
   their own voice; the ID is the hex string in the model page URL. Never
   suggest or reuse anyone else's voice ID.
2. **API key.** If `FISH_API_KEY` isn't set, the best option is the plugin
   settings dialog, where the key is masked and kept in secure storage: tell the user to run
   `/plugin configure loom@loom-skill`, fill in the fields, then start a new session (settings sync at session start). The
   voice model ID can be entered there too. Don't ask them to paste the key
   into chat. If they paste it anyway, use it, and tell them it is now in the
   chat history.
3. Save what you received and install the browser:
   ```
   loom setup --reference-id <ID> [--model s2.1-pro-free] [--api-key <KEY>]
   ```
   (`setup` with no flags only installs Chromium and checks FFmpeg.)
4. Read the output. It prints the voice model's title and author: ask the
   user to confirm it's their own voice. If FFmpeg is missing, give them the
   printed install command. If uv is missing, give them
   `curl -LsSf https://astral.sh/uv/install.sh | sh`.
5. If the voice check passed, offer a quick test:
   `loom say "Hi, this is my Loom voice." -o ~/Videos/loom/voice-test.wav`
   and tell them where the file is.

Model choice: `s2.1-pro` needs Fish Audio *API* credit (separate from a
Fish subscription). `s2.1-pro-free` works on the free developer tier.
