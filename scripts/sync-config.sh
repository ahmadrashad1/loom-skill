#!/bin/sh
# SessionStart hook: copy this plugin's settings (entered in Claude Code's
# plugin settings dialog) to ~/.config/loom/plugin.env, where the loom CLI
# reads them. Claude's Bash tool doesn't receive plugin options directly.
dir="${XDG_CONFIG_HOME:-$HOME/.config}/loom"
f="$dir/plugin.env"
umask 077
mkdir -p "$dir" || exit 0
{
  echo "# written by the loom plugin at session start; edit via /plugin, not here"
  [ -n "$CLAUDE_PLUGIN_OPTION_FISH_REFERENCE_ID" ] && printf 'FISH_REFERENCE_ID=%s\n' "$CLAUDE_PLUGIN_OPTION_FISH_REFERENCE_ID"
  [ -n "$CLAUDE_PLUGIN_OPTION_FISH_API_KEY" ] && printf 'FISH_API_KEY=%s\n' "$CLAUDE_PLUGIN_OPTION_FISH_API_KEY"
  [ -n "$CLAUDE_PLUGIN_OPTION_FISH_MODEL" ] && printf 'FISH_MODEL=%s\n' "$CLAUDE_PLUGIN_OPTION_FISH_MODEL"
} > "$f.tmp" && mv "$f.tmp" "$f"
exit 0
