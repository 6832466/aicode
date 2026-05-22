"""配置管理 - 基于 QConfig"""

from pathlib import Path
from typing import Optional

from qfluentwidgets import QConfig, ConfigItem, BoolValidator, RangeValidator


class JMConfig(QConfig):
    """应用配置"""

    # 生成设置
    interval_seconds = ConfigItem("Generation", "interval_seconds", 5)
    retry_times = ConfigItem("Generation", "retry_times", 3)
    prompt_excel_path = ConfigItem(
        "Generation", "prompt_excel_path",
        "C:/Users/Administrator/Desktop/提示词.xlsx",
    )
    character_excel_path = ConfigItem(
        "Generation", "character_excel_path",
        "C:/Users/Administrator/Desktop/人物对照表.xlsx",
    )

    # 下载设置
    save_dir = ConfigItem("Download", "save_dir", "D:/Downloads/jm_videos")
    max_concurrent = ConfigItem("Download", "max_concurrent", 3)
    resume_enabled = ConfigItem("Download", "resume_enabled", True, BoolValidator())

    # 通用设置
    auto_check_cli = ConfigItem("General", "auto_check_cli", True, BoolValidator())


_config_instance: Optional[JMConfig] = None


def get_config() -> JMConfig:
    """获取配置单例"""
    global _config_instance
    if _config_instance is None:
        from qfluentwidgets import qconfig
        cfg = JMConfig()
        cfg_file = Path(__file__).resolve().parent / "settings.json"
        qconfig.load(str(cfg_file), cfg)
        _config_instance = cfg
    return _config_instance
