"""Persistent configuration using qfluentwidgets QConfig."""
from qfluentwidgets import QConfig, ConfigItem, OptionsConfigItem, OptionsValidator


class AppConfig(QConfig):
    """Application-level persistent configuration."""

    # API connection
    api_base_url = ConfigItem("API", "BaseUrl", "http://localhost:8000")
    api_key = ConfigItem("API", "Key", "")
    model_name = ConfigItem("API", "ModelName", "gemini-3.1-flash-image")
    api_endpoint_path = ConfigItem("API", "EndpointPath", "/v1/chat/completions")

    # Generation defaults
    aspect_ratio = OptionsConfigItem(
        "Generation", "AspectRatio", "方形 (1:1)",
        OptionsValidator(["横屏 (16:9)", "竖屏 (9:16)", "方形 (1:1)", "4:3", "3:4"])
    )
    resolution = OptionsConfigItem(
        "Generation", "Resolution", "2K",
        OptionsValidator(["1K", "2K", "4K"])
    )

    # Built-in server
    server_auto_start = ConfigItem("Server", "AutoStart", False)
    use_local_server = ConfigItem("Server", "UseLocalServer", True)

    # Remote API session-based auth (for servers that disable Bearer token)
    api_session_cookie = ConfigItem("API", "SessionCookie", "")
    api_user_id = ConfigItem("API", "UserId", "13679")

    # Remote API preset
    remote_preset = ConfigItem("API", "RemotePreset", "bj.nfai.lol")

    # Chrome CDP connection (local mode — gemini_cdp)
    chrome_debug_port = ConfigItem("CDP", "DebugPort", 9222)
    chrome_debug_host = ConfigItem("CDP", "DebugHost", "127.0.0.1")
    chrome_exe_path = ConfigItem("CDP", "ChromeExePath", "")


cfg = AppConfig()
cfg.load()
