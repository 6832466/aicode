"""应用配置 —— QConfig 持久化。"""
import os
import tempfile
from qfluentwidgets import QConfig, ConfigItem, BoolValidator


class AppConfig(QConfig):
    """全局单例配置，自动持久化。"""
    output_dir = ConfigItem("Scrape", "OutputDir", "")
    user_data_dir = ConfigItem(
        "Scrape", "UserDataDir",
        os.path.join(tempfile.gettempdir(), "playwright_chrome_profile"),
    )
    silent_mode = ConfigItem("Scrape", "SilentMode", False, BoolValidator())


app_config = AppConfig()
