import sys
from pathlib import Path

from PySide6.QtCore import QSettings

API_BASE = "https://api.runwayml.com/v1"
MAX_CONCURRENT = 2
DEFAULT_POLL_INTERVAL = 75
DEFAULT_TEAM_ID = ""
DEFAULT_RESOLUTION = "720p"
MIN_DURATION = 4
MAX_DURATION = 15

SETTINGS_KEY_TOKEN = "runway/token"
SETTINGS_KEY_TEAM_ID = "runway/team_id"
SETTINGS_KEY_OUTPUT_DIR = "runway/output_dir"
SETTINGS_KEY_PREFIX = "runway/prefix"
SETTINGS_KEY_SUFFIX = "runway/suffix"
SETTINGS_KEY_POLL = "runway/poll_interval"
SETTINGS_KEY_RESOLUTION = "runway/resolution"
SETTINGS_KEY_AUDIO = "runway/generate_audio"
SETTINGS_KEY_SESSION_ID = "runway/session_id"
SETTINGS_KEY_ASSET_GROUP_ID = "runway/asset_group_id"


# ------------------------------------------------------------------
# Path helpers — shared across UI and app modules (no circular deps)
# ------------------------------------------------------------------

def app_root() -> Path:
    """Writable app root. Works in dev and PyInstaller frozen mode."""
    if getattr(sys, 'frozen', False):
        return Path(sys.executable).parent
    # Running from project root (config.py is in app/)
    return Path(__file__).parent.parent


def app_icon_path() -> Path:
    """Return path to 1.ico. In PyInstaller COLLECT mode the icon is in _internal/."""
    base = app_root()
    p = base / "1.ico"
    if not p.exists():
        p = base / "_internal" / "1.ico"
    return p


def data_dir(team_id: str = "") -> Path:
    """Per-team data directory — isolates file writes across instances."""
    base = app_root() / "data"
    if team_id:
        base = base / team_id
    base.mkdir(parents=True, exist_ok=True)
    return base


def char_assets_path(team_id: str = "") -> Path:
    """Path to character_assets.json — with legacy fallback for reads."""
    legacy = app_root() / "data" / "character_assets.json"
    if team_id:
        team_path = data_dir(team_id) / "character_assets.json"
        if not team_path.exists() and legacy.exists():
            return legacy  # backward compat
        return team_path
    return legacy


def char_assets_write_path(team_id: str = "") -> Path:
    """Write path — always team-specific, never falls back to shared file."""
    if team_id:
        return data_dir(team_id) / "character_assets.json"
    return app_root() / "data" / "character_assets.json"


def batch_log_path(team_id: str = "") -> Path:
    """Path to batch_log.json — with legacy fallback for reads."""
    legacy = app_root() / "data" / "batch_log.json"
    if team_id:
        team_path = data_dir(team_id) / "batch_log.json"
        if not team_path.exists() and legacy.exists():
            return legacy
        return team_path
    return legacy


def settings_scope(team_id: str = "") -> QSettings:
    """Per-team QSettings to avoid config conflicts across instances."""
    if team_id:
        return QSettings("RunwayMLApp", f"settings-{team_id}")
    return QSettings("RunwayMLApp", "settings")
