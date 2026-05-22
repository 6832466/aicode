"""License verification — hardware-bound passphrase check.

Uses HMAC-SHA256 with a machine-specific ID as the key and the
user-supplied passphrase as the message.  The resulting token is
stored on disk so subsequent launches skip the prompt.
"""

import hashlib
import hmac
import logging
import os
import subprocess
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

_PASSPHRASE = "师父的起飞之路"
_TOKEN_FILENAME = ".runwayml_license"


def _app_root() -> Path:
    if getattr(sys, 'frozen', False):
        return Path(sys.executable).parent
    return Path(__file__).parent.parent.parent


def _token_path() -> Path:
    return _app_root() / _TOKEN_FILENAME


# ------------------------------------------------------------------
# Machine ID — hardware-bound stable identifier
# ------------------------------------------------------------------


def _get_motherboard_uuid() -> str:
    """wmic csproduct get uuid — most stable hardware ID on Windows."""
    try:
        result = subprocess.run(
            ["wmic", "csproduct", "get", "uuid"],
            capture_output=True, text=True, timeout=5,
            creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0,
        )
        for line in result.stdout.splitlines():
            line = line.strip().lower()
            if line and line != "uuid" and "00000000" not in line.replace("-", ""):
                return line
    except Exception as e:
        logger.debug("Failed to get motherboard UUID: %s", e)
    return ""


def _get_mac_address() -> str:
    """uuid.getnode() — fallback hardware identifier."""
    try:
        import uuid
        node = uuid.getnode()
        if node != 0:
            return format(node, "x")
    except Exception:
        pass
    return ""


def get_machine_id() -> str:
    """Return a stable machine identifier string.

    Tries motherboard UUID first, falls back to MAC address.
    If both fail, raises RuntimeError.
    """
    mid = _get_motherboard_uuid()
    if not mid:
        mid = _get_mac_address()
    if not mid:
        raise RuntimeError("无法获取硬件标识 — 请联系管理员")
    return mid


# ------------------------------------------------------------------
# Token computation
# ------------------------------------------------------------------


def compute_token(machine_id: str, passphrase: str) -> str:
    """HMAC-SHA256: key=machine_id, message=passphrase."""
    return hmac.new(
        machine_id.encode("utf-8"),
        passphrase.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


# ------------------------------------------------------------------
# Public API
# ------------------------------------------------------------------


def is_verified() -> bool:
    """Return True if the stored token matches the current machine + passphrase."""
    path = _token_path()
    if not path.exists():
        return False
    try:
        stored = path.read_text(encoding="utf-8").strip()
        expected = compute_token(get_machine_id(), _PASSPHRASE)
        return hmac.compare_digest(stored, expected)
    except Exception:
        return False


def verify_passphrase(passphrase: str) -> bool:
    """Check user-supplied passphrase against hardware ID.

    Returns True if correct and saves the verification token.
    """
    try:
        machine_id = get_machine_id()
    except RuntimeError:
        logger.exception("硬件标识获取失败")
        return False

    expected = compute_token(machine_id, _PASSPHRASE)
    user_token = compute_token(machine_id, passphrase)

    if hmac.compare_digest(expected, user_token):
        _token_path().write_text(user_token, encoding="utf-8")
        return True
    return False
