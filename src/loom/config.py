"""Settings: shipped defaults + per-user config + environment.

Per-user files live in ~/.config/loom/ (XDG_CONFIG_HOME), outside the plugin
directory, so they survive plugin updates:
  plugin.env    written each session from the Claude Code plugin settings
  config.env    written by `loom setup`
  settings.yaml optional overrides of config/settings.yaml
Precedence: process env > plugin.env > config.env > <repo>/.env (development).
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
CONFIG_DIR = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "loom"
PLUGIN_ENV = CONFIG_DIR / "plugin.env"
USER_ENV = CONFIG_DIR / "config.env"


def _load_env() -> None:
    for f in (PLUGIN_ENV, USER_ENV, ROOT / ".env"):
        if f.exists():
            load_dotenv(f, override=False)


_load_env()


def recordings_dir() -> Path:
    v = os.environ.get("LOOM_RECORDINGS")
    return Path(v).expanduser() if v else Path.home() / "Videos" / "loom"


RECORDINGS = recordings_dir()


@dataclass
class Settings:
    tts_provider: str = "fish"  # fish | espeak | silent
    fish_model: str = "s2.1-pro"
    fish_speed: float = 1.0
    fish_latency: str = "normal"
    fish_api_key: str | None = None
    fish_reference_id: str | None = None
    recorder: str = "playwright"  # playwright | obs
    headless: bool = True
    width: int = 1920
    height: int = 1080
    fps: int = 30
    crf: int = 18
    preset: str = "medium"
    audio_bitrate: str = "192k"
    loudness_i: float = -16.0
    loudness_tp: float = -1.5
    captions: str = "soft"  # soft | burn | none
    fade_s: float = 0.4
    obs_host: str = "localhost"
    obs_port: int = 4455
    obs_password: str | None = None
    extra: dict = field(default_factory=dict)


def _yaml(path: Path) -> dict:
    if not path.exists():
        return {}
    data = yaml.safe_load(path.read_text()) or {}
    flat: dict = {}
    for section in data.values() if isinstance(data, dict) else []:
        if isinstance(section, dict):
            flat.update(section)
    return flat


def load_settings(overrides: dict | None = None) -> Settings:
    s = Settings()
    for src in (ROOT / "config" / "settings.yaml", CONFIG_DIR / "settings.yaml"):
        for k, v in _yaml(src).items():
            if hasattr(s, k):
                setattr(s, k, v)
    env = os.environ
    s.fish_api_key = env.get("FISH_API_KEY") or s.fish_api_key
    s.fish_reference_id = env.get("FISH_REFERENCE_ID") or s.fish_reference_id
    s.fish_model = env.get("FISH_MODEL") or s.fish_model
    s.obs_password = env.get("OBS_WEBSOCKET_PASSWORD") or s.obs_password
    if env.get("LOOM_TTS_PROVIDER"):
        s.tts_provider = env["LOOM_TTS_PROVIDER"]
    for k, v in (overrides or {}).items():
        if v is not None:
            setattr(s, k, v)
    return s


def write_user_env(updates: dict[str, str]) -> Path:
    """Merge KEY=value pairs into ~/.config/loom/config.env (mode 600)."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    current: dict[str, str] = {}
    if USER_ENV.exists():
        for line in USER_ENV.read_text().splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                k, v = line.split("=", 1)
                current[k.strip()] = v.strip()
    current.update({k: v for k, v in updates.items() if v})
    tmp = USER_ENV.with_suffix(".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write("# loom user config (written by `loom setup`)\n")
        f.writelines(f"{k}={v}\n" for k, v in current.items())
    tmp.replace(USER_ENV)
    return USER_ENV
