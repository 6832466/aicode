"""
许可证管理 — 硬件绑定激活
(占位实现，后续接入真实许可证逻辑)
"""

import uuid
import hashlib
import platform
import logging
from pathlib import Path
from datetime import datetime

from app.config import data_dir

logger = logging.getLogger(__name__)


class License:
    """
    硬件绑定许可证。
    后续接入真实激活逻辑时替换此模块。
    当前为免费试用模式。
    """

    LICENSE_FILE = "license.key"

    def __init__(self):
        self._key_path = data_dir() / self.LICENSE_FILE
        self._activated = self._check_local()
        logger.info(f"许可证状态: {'已激活' if self._activated else '试用模式'}")

    def is_activated(self) -> bool:
        return self._activated

    def _get_hardware_id(self) -> str:
        """获取硬件指纹"""
        info = f"{platform.node()}-{platform.machine()}-{platform.processor()}"
        return hashlib.sha256(info.encode()).hexdigest()[:16]

    def _check_local(self) -> bool:
        """检查本地许可证"""
        if not self._key_path.exists():
            return False
        try:
            data = self._key_path.read_text(encoding="utf-8").strip()
            expected = self._get_hardware_id()
            return data == expected
        except Exception:
            return False

    def activate(self, key: str) -> bool:
        """激活许可证"""
        # 占位: 简单比对硬件 ID
        if key == self._get_hardware_id():
            self._key_path.write_text(key, encoding="utf-8")
            self._activated = True
            return True
        return False

    def deactivate(self):
        """取消激活"""
        self._key_path.unlink(missing_ok=True)
        self._activated = False