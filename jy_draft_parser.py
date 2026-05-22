"""
剪映草稿解析器 — 扫描、读取、版本检测、保存。
"""
import json
import os
import re
from pathlib import Path

from jy_version_map import extract_major_version, extract_minor_version


class DraftInfo:
    """草稿信息数据类"""
    def __init__(self, folder_path: str):
        self.folder_path = Path(folder_path)
        self.name = ""
        self.version = ""
        self.major_version = "unknown"
        self.create_time = ""
        self.update_time = ""
        self.info_json_path = ""
        self.content_json_path = ""
        self._info_data = None
        self._content_data = None

    @property
    def info_data(self) -> dict:
        if self._info_data is None:
            self._info_data = self._load_json(self.info_json_path)
        return self._info_data

    @property
    def content_data(self) -> dict:
        if self._content_data is None:
            self._content_data = self._load_json(self.content_json_path)
        return self._content_data

    def _load_json(self, path) -> dict:
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return {}

    @property
    def display_name(self) -> str:
        return self.name or self.folder_path.name

    @property
    def folder_name(self) -> str:
        return self.folder_path.name


class DraftParser:
    """剪映草稿解析器"""

    # 常见的草稿存储路径模式
    DEFAULT_DRAFT_ROOTS = [
        os.path.expandvars(r"%LOCALAPPDATA%\JianyingPro\User Data\Projects\com.lveditor.draft"),
        os.path.expandvars(r"%LOCALAPPDATA%\剪映Pro\User Data\Projects\com.lveditor.draft"),
        os.path.expandvars(r"%LOCALAPPDATA%\Jianying\User Data\Projects\com.lveditor.draft"),
        os.path.expandvars(r"%APPDATA%\JianyingPro\User Data\Projects\com.lveditor.draft"),
    ]

    # JSON 中可能包含版本号的字段名
    VERSION_FIELD_CANDIDATES = [
        "app_version", "draft_version", "version",
        "new_version", "editor_version", "create_version",
        "app_ver", "ver",
    ]

    @staticmethod
    def get_default_draft_path() -> str | None:
        """获取默认草稿目录"""
        for root in DraftParser.DEFAULT_DRAFT_ROOTS:
            if os.path.isdir(root):
                return root
        return None

    @staticmethod
    def scan_drafts(draft_root: str = None) -> list[DraftInfo]:
        """扫描草稿目录，返回所有有效草稿"""
        if draft_root is None:
            draft_root = DraftParser.get_default_draft_path()
        if draft_root is None or not os.path.isdir(draft_root):
            return []

        drafts = []
        try:
            for entry in os.listdir(draft_root):
                folder = os.path.join(draft_root, entry)
                if not os.path.isdir(folder):
                    continue
                info = DraftParser._parse_draft_folder(folder)
                if info is not None:
                    drafts.append(info)
        except PermissionError:
            pass

        drafts.sort(key=lambda d: d.update_time or "", reverse=True)
        return drafts

    @staticmethod
    def _parse_draft_folder(folder_path: str) -> DraftInfo | None:
        """解析单个草稿文件夹"""
        info_json = os.path.join(folder_path, "draft_info.json")
        content_json = os.path.join(folder_path, "draft_content.json")

        # 至少需要其中一个 JSON 文件
        has_info = os.path.isfile(info_json)
        has_content = os.path.isfile(content_json)

        if not has_info and not has_content:
            return None

        draft = DraftInfo(folder_path)
        draft.info_json_path = info_json
        draft.content_json_path = content_json

        # 从 draft_info.json 读取元数据
        if has_info:
            info = draft.info_data
            draft.name = info.get("draft_name", "") or info.get("name", "")
            draft.create_time = info.get("create_time", "") or info.get("created_at", "")
            draft.update_time = info.get("update_time", "") or info.get("updated_at", "")

        # 检测版本
        draft.version = DraftParser._detect_version(draft, has_info, has_content)
        draft.major_version = extract_major_version(draft.version)

        # 如果 info 里没有名字，尝试从 content 读取
        if not draft.name:
            draft.name = draft.content_data.get("draft_name", "") or draft.content_data.get("name", "")

        return draft

    @staticmethod
    def _detect_version(draft: DraftInfo, has_info: bool, has_content: bool) -> str:
        """从草稿 JSON 中检测版本号"""
        # 优先从 draft_info.json 查找
        if has_info:
            ver = DraftParser._find_version_in_dict(draft.info_data)
            if ver:
                return ver

        # 其次从 draft_content.json 查找
        if has_content:
            ver = DraftParser._find_version_in_dict(draft.content_data)
            if ver:
                return ver

        # 尝试从文件夹名推断（有时文件夹名包含版本）
        for pattern in [r'v?(\d+\.\d+\.\d+)', r'ver[_-](\d+\.\d+)']:
            match = re.search(pattern, draft.folder_path.name, re.IGNORECASE)
            if match:
                return match.group(1)

        return "unknown"

    @staticmethod
    def _find_version_in_dict(data: dict, max_depth: int = 3) -> str | None:
        """在 dict 中递归查找版本号字段（限深度）"""
        if max_depth <= 0:
            return None
        if not isinstance(data, dict):
            return None

        for key, value in data.items():
            key_lower = key.lower().replace(" ", "_")
            # 检查是否为版本字段
            if key_lower in DraftParser.VERSION_FIELD_CANDIDATES:
                if isinstance(value, str) and re.match(r'\d+\.\d+', value):
                    return value
            # 递归查找子 dict
            elif isinstance(value, dict):
                result = DraftParser._find_version_in_dict(value, max_depth - 1)
                if result:
                    return result
        return None

    @staticmethod
    def save_draft(draft: DraftInfo, content_data: dict = None, info_data: dict = None) -> bool:
        """保存修改后的草稿数据"""
        success = True
        try:
            if content_data is not None and draft.content_json_path:
                with open(draft.content_json_path, "w", encoding="utf-8") as f:
                    json.dump(content_data, f, ensure_ascii=False, indent=2)
            if info_data is not None and draft.info_json_path:
                with open(draft.info_json_path, "w", encoding="utf-8") as f:
                    json.dump(info_data, f, ensure_ascii=False, indent=2)
        except (IOError, PermissionError) as e:
            print(f"保存失败: {e}")
            success = False
        return success

    @staticmethod
    def set_version_in_dict(data: dict, new_version: str) -> int:
        """递归修改 dict 中所有版本号字段，返回修改数量"""
        count = 0
        if not isinstance(data, dict):
            return count
        for key in list(data.keys()):
            key_lower = key.lower().replace(" ", "_")
            if key_lower in DraftParser.VERSION_FIELD_CANDIDATES:
                if isinstance(data[key], str):
                    data[key] = new_version
                    count += 1
            elif isinstance(data[key], dict):
                count += DraftParser.set_version_in_dict(data[key], new_version)
        return count
