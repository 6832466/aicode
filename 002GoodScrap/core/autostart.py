r"""Autostart - enable/disable launch at Windows startup via Registry Run key.

Uses HKCU\Software\Microsoft\Windows\CurrentVersion\Run, which is the standard
per-user startup mechanism. Does NOT require admin privileges.
"""

import os
import sys
import winreg


RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
VALUE_NAME = "GoldMonitor"


def _build_command() -> str:
    """Build the startup command.

    When running as a PyInstaller exe, just reference the exe directly.
    Otherwise use pythonw.exe + the path to main.py (no console flash).
    """
    if getattr(sys, 'frozen', False):
        return f'"{sys.executable}"'

    py_dir = os.path.dirname(sys.executable)
    pythonw = os.path.join(py_dir, "pythonw.exe")
    if not os.path.exists(pythonw):
        pythonw = sys.executable

    script_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    main_py = os.path.join(script_dir, "main.py")

    return f'"{pythonw}" "{main_py}"'


def is_enabled() -> bool:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            _ = winreg.QueryValueEx(key, VALUE_NAME)
        return True
    except FileNotFoundError:
        return False


def enable() -> None:
    command = _build_command()
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_WRITE) as key:
        winreg.SetValueEx(key, VALUE_NAME, 0, winreg.REG_SZ, command)


def disable() -> None:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_WRITE) as key:
            winreg.DeleteValue(key, VALUE_NAME)
    except FileNotFoundError:
        pass


def set_enabled(enabled: bool) -> None:
    if enabled:
        enable()
    else:
        disable()
