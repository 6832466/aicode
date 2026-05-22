import sys
import json
from pathlib import Path
from PySide6.QtCore import QSettings

# API endpoints
API_BASE_OPENAI = "https://api-inference.modelscope.cn/v1/"
API_BASE_ANTHROPIC = "https://api-inference.modelscope.cn/compatible-mode/v1/"
API_BASE_IMAGE = "https://api-inference.modelscope.cn/v1/images/generations"

# Rate limits
DAILY_TOTAL_LIMIT = 2000  # Shared across all models
IMAGE_DAILY_LIMIT = 50    # Image generation models

# Settings keys
SETTINGS_KEY_API_KEY = "modelscope/api_key"
SETTINGS_KEY_THEME = "modelscope/theme"
SETTINGS_KEY_REFRESH_INTERVAL = "modelscope/refresh_interval"
SETTINGS_KEY_PROXY_HTTP = "modelscope/proxy_http"
SETTINGS_KEY_PROXY_HTTPS = "modelscope/proxy_https"
SETTINGS_KEY_NOTIFY_THRESHOLD = "modelscope/notify_threshold"
SETTINGS_KEY_NOTIFY_ENABLED = "modelscope/notify_enabled"
SETTINGS_KEY_AUTO_REFRESH = "modelscope/auto_refresh"
SETTINGS_KEY_API_KEYS = "modelscope/api_keys"  # JSON list for multi-key
SETTINGS_KEY_ACTIVE_KEY_INDEX = "modelscope/active_key_index"
SETTINGS_KEY_ACTIVE_KEY_NAME = "modelscope/active_key_name"

# Path helpers
def app_root() -> Path:
    """Writable app root. Works in dev and PyInstaller frozen mode."""
    if getattr(sys, 'frozen', False):
        # One-dir (COLLECT) mode: data lives next to the exe
        return Path(sys.executable).parent
    return Path(__file__).parent.parent


def app_icon_path() -> Path:
    """Return path to 1.ico. Searches multiple locations for frozen compatibility."""
    # In one-file mode, icon is extracted to sys._MEIPASS
    frozen_base = getattr(sys, '_MEIPASS', None)
    if frozen_base:
        p = Path(frozen_base) / "1.ico"
        if p.exists():
            return p
    # In one-dir (COLLECT) mode, icon is in _internal/
    base = app_root()
    for sub in ("", "_internal"):
        p = base / sub / "1.ico"
        if p.exists():
            return p
    # Last resort: return the dev path
    return Path(__file__).parent.parent / "1.ico"


def data_dir() -> Path:
    """Data directory for configs, logs, and cached data."""
    base = app_root() / "data"
    base.mkdir(parents=True, exist_ok=True)
    return base


def config_dir() -> Path:
    """Config directory for JSON settings."""
    base = data_dir() / "config"
    base.mkdir(parents=True, exist_ok=True)
    return base


def models_config_path() -> Path:
    """Path to models.json configuration file."""
    return config_dir() / "models.json"


def quota_history_path() -> Path:
    """Path to quota_history.json for tracking usage."""
    return data_dir() / "quota_history.json"


def chat_history_dir() -> Path:
    """Directory for chat history files."""
    base = data_dir() / "chat_history"
    base.mkdir(parents=True, exist_ok=True)
    return base


def image_cache_dir() -> Path:
    """Directory for cached generated images."""
    base = data_dir() / "images"
    base.mkdir(parents=True, exist_ok=True)
    return base


def settings_scope() -> QSettings:
    """Global QSettings for the application."""
    return QSettings("ModelScopeManager", "settings")


def api_keys_path() -> Path:
    """Path to encrypted API keys storage."""
    return config_dir() / "api_keys.json"


def templates_path() -> Path:
    """Path to prompt templates."""
    return data_dir() / "templates.json"


def batch_tasks_path() -> Path:
    """Path to batch task history."""
    return data_dir() / "batch_tasks.json"


def usage_stats_path() -> Path:
    """Path to usage statistics."""
    return data_dir() / "usage_stats.json"


def groups_config_path() -> Path:
    """Path to model groups configuration."""
    return config_dir() / "groups.json"


# Encryption utilities for Windows DPAPI
def _get_dpapi_key() -> bytes:
    """Get machine-specific key using Windows DPAPI."""
    import base64
    import ctypes
    from ctypes import wintypes

    # Use a fixed entropy for reproducibility across app restarts
    entropy = b"ModelScopeManager_v1"

    # Try to get existing key from registry
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\ModelScopeManager", 0, winreg.KEY_READ) as key:
            encrypted_key, _ = winreg.QueryValueEx(key, "dpapi_key")
            # Decrypt using DPAPI
            crypt32 = ctypes.windll.crypt32
            data_in = base64.b64decode(encrypted_key)
            blob_in = ctypes.create_string_buffer(data_in, len(data_in))
            blob_out = ctypes.c_void_p()
            blob_out_size = wintypes.DWORD()

            if crypt32.CryptUnprotectMessage(
                ctypes.byref(ctypes.c_void_p(len(blob_in))),
                blob_in,
                len(blob_in),
                None,
                None,
                None,
                ctypes.byref(blob_out_size)
            ):
                return base64.urlsafe_b64encode(blob_out.raw[:32])
    except Exception:
        pass

    # Generate new key
    import secrets
    new_key = secrets.token_bytes(32)

    # Encrypt using DPAPI
    crypt32 = ctypes.windll.crypt32
    blob_in = ctypes.create_string_buffer(new_key, 32)
    blob_out = ctypes.c_void_p()
    blob_out_size = wintypes.DWORD()

    entropy_blob = ctypes.create_string_buffer(entropy, len(entropy))

    if crypt32.CryptProtectMessage(
        None,
        blob_in,
        32,
        entropy_blob,
        len(entropy),
        None,
        ctypes.byref(blob_out_size)
    ):
        blob_out = ctypes.create_string_buffer(blob_out_size.value)
        crypt32.CryptProtectMessage(
            None,
            blob_in,
            32,
            entropy_blob,
            len(entropy),
            None,
            blob_out
        )
        encrypted_key = base64.b64encode(blob_out.raw).decode()

        # Save to registry
        try:
            import winreg
            key = winreg.CreateKey(winreg.HKEY_CURRENT_USER, r"Software\ModelScopeManager")
            winreg.SetValueEx(key, "dpapi_key", 0, winreg.REG_SZ, encrypted_key)
            winreg.CloseKey(key)
        except Exception:
            pass

    return base64.urlsafe_b64encode(new_key)


def encrypt_api_key(plain_key: str) -> str:
    """Encrypt API key using Fernet with DPAPI-derived key."""
    try:
        from cryptography.fernet import Fernet
        key = _get_dpapi_key()
        f = Fernet(key)
        encrypted = f.encrypt(plain_key.encode())
        import base64
        return base64.b64encode(encrypted).decode()
    except Exception as e:
        # Fallback to base64 if cryptography unavailable
        import base64
        import logging
        logging.getLogger(__name__).warning(f"Encryption unavailable: {e}")
        return base64.b64encode(plain_key.encode()).decode()


def decrypt_api_key(encrypted_key: str) -> str:
    """Decrypt API key."""
    try:
        from cryptography.fernet import Fernet
        import base64
        key = _get_dpapi_key()
        f = Fernet(key)
        encrypted = base64.b64decode(encrypted_key.encode())
        return f.decrypt(encrypted).decode()
    except Exception as e:
        # Fallback to base64
        import base64
        import logging
        logging.getLogger(__name__).warning(f"Decryption unavailable: {e}")
        try:
            return base64.b64decode(encrypted_key.encode()).decode()
        except Exception:
            return encrypted_key


def load_groups() -> list[str]:
    """Load model groups from config."""
    path = groups_config_path()
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return data.get("groups", [])
        except Exception:
            pass
    return []


def save_groups(groups: list[str]) -> None:
    """Save model groups to config."""
    path = groups_config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {"groups": groups}
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


# Preset model combinations
PRESET_COMBOS = {
    "日常对话": [
        "Qwen/Qwen3-235B-A22B-Instruct-2507",
        "ZhipuAI/GLM-4.7-Flash",
    ],
    "代码开发": [
        "Qwen/Qwen3-Coder-480B-A35B-Instruct",
        "Qwen/Qwen3-Coder-30B-A3B-Instruct",
    ],
    "深度推理": [
        "deepseek-ai/DeepSeek-R1-0528",
        "Qwen/QwQ-32B",
        "ZhipuAI/GLM-5.1",
    ],
    "多模态": [
        "Qwen/Qwen3-VL-235B-A22B-Instruct",
        "Qwen/Qwen3-VL-8B-Instruct",
    ],
    "超长上下文": [
        "MiniMax/MiniMax-M2.5",
        "MiniMax/MiniMax-M1-80k",
    ],
    "全量免费模型": "ALL",
}

# All available free models (verified against API 2026-05-16)
FREE_MODELS = {
    "llm": [
        # Qwen 系列
        "Qwen/Qwen3-Coder-480B-A35B-Instruct",
        "Qwen/Qwen3-Coder-30B-A3B-Instruct",
        "Qwen/Qwen3-235B-A22B-Instruct-2507",
        "Qwen/Qwen3-235B-A22B-Thinking-2507",
        "Qwen/Qwen3-Next-80B-A3B-Instruct",
        "Qwen/Qwen3-Next-80B-A3B-Thinking",
        "Qwen/Qwen3.5-397B-A17B",
        "Qwen/Qwen3.5-122B-A10B",
        "Qwen/Qwen3.5-35B-A3B",
        "Qwen/Qwen3.5-27B",
        "Qwen/Qwen3-32B",
        "Qwen/Qwen3-30B-A3B",
        "Qwen/Qwen3-30B-A3B-Thinking-2507",
        "Qwen/Qwen3-14B",
        "Qwen/Qwen3-8B",
        "Qwen/Qwen3-4B",
        "Qwen/Qwen3-1.7B",
        "Qwen/Qwen3-0.6B",
        "Qwen/QwQ-32B",
        "Qwen/QVQ-72B-Preview",
        # DeepSeek 系列
        "deepseek-ai/DeepSeek-V3.2",
        "deepseek-ai/DeepSeek-V4-Flash",
        "deepseek-ai/DeepSeek-R1-0528",
        # GLM 系列
        "ZhipuAI/GLM-5.1",
        "ZhipuAI/GLM-5",
        "ZhipuAI/GLM-4.7-Flash",
        # MiniMax 系列
        "MiniMax/MiniMax-M2.5",
        "MiniMax/MiniMax-M1-80k",
        # Mistral 系列
        "mistralai/Mistral-Large-Instruct-2407",
        "mistralai/Mistral-Small-Instruct-2409",
        "mistralai/Ministral-8B-Instruct-2410",
        # 其他
        "moonshotai/Kimi-K2.5",
        "stepfun-ai/Step-3.5-Flash",
        "meituan-longcat/LongCat-Flash-Lite",
        "LLM-Research/Llama-4-Maverick-17B-128E-Instruct",
        "XiaomiMiMo/MiMo-V2-Flash",
    ],
    "multimodal": [
        "Qwen/Qwen3-VL-235B-A22B-Instruct",
        "Qwen/Qwen3-VL-8B-Instruct",
        "Qwen/Qwen3-VL-8B-Thinking",
        "OpenGVLab/InternVL3_5-241B-A28B",
        "PaddlePaddle/ERNIE-4.5-VL-28B-A3B-PT",
        "iic/GUI-Owl-1.5-8B-Instruct",
        "iic/GUI-Owl-1.5-8B-Think",
    ],
    "image": [
        "Qwen/Qwen-Image-Edit",
        "MusePublic/Qwen-Image-Edit",
    ],
}

# Model type display names
MODEL_TYPE_NAMES = {
    "llm": "大语言模型",
    "multimodal": "多模态模型",
    "image": "图像模型",
}


# --- Shared utility functions ---

def short_model_name(model_id: str) -> str:
    """Extract short name from full model ID: 'Qwen/Qwen3-8B' -> 'Qwen3-8B'"""
    return model_id.split("/")[-1] if "/" in model_id else model_id


def get_model_type(model_id: str) -> str:
    """Look up the model type (llm/multimodal/image) from FREE_MODELS. Returns 'llm' if not found."""
    for t, ids in FREE_MODELS.items():
        if model_id in ids:
            return t
    return "llm"


def load_json(path: Path, default=None):
    """Load and parse a JSON file. Returns default if file missing or corrupt."""
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def save_json(path: Path, data) -> None:
    """Save data as JSON with consistent formatting."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def apply_theme(theme_index: int) -> None:
    """Apply QFluentWidgets theme from combo index: 0=Auto, 1=Light, 2=Dark."""
    from qfluentwidgets import setTheme, Theme
    theme_map = {0: Theme.AUTO, 1: Theme.LIGHT, 2: Theme.DARK}
    setTheme(theme_map.get(theme_index, Theme.AUTO))