"""素材匹配器"""

import json
import logging
from pathlib import Path
from typing import Optional

from data.models import CharacterMaterial, MaterialType
from utils.helpers import infer_material_type

logger = logging.getLogger(__name__)

# 名称映射文件
NAME_MAPPINGS_PATH = Path(__file__).resolve().parent / "name_mappings.json"


class MaterialMatcher:
    """人物素材匹配器"""

    def __init__(self):
        self._materials: list[CharacterMaterial] = []
        self._name_mappings: dict[str, str] = {}
        self._load_name_mappings()

    # ── 素材管理 ──

    def load_materials(self, excel_data: list[dict]):
        """从 excel_handler 读取的数据加载素材"""
        self._materials = []
        for row in excel_data:
            name = row["人物名字"]
            path = row["引用名"]
            mtype = infer_material_type(path)
            self._materials.append(CharacterMaterial(
                character_name=name,
                file_path=path,
                material_type=MaterialType(mtype),
            ))
        logger.info("加载素材: %d 条", len(self._materials))

    def get_all_materials(self) -> list[CharacterMaterial]:
        return list(self._materials)

    # ── 名称映射 ──

    def _load_name_mappings(self):
        """加载名称映射文件"""
        if NAME_MAPPINGS_PATH.exists():
            try:
                data = json.loads(NAME_MAPPINGS_PATH.read_text(encoding="utf-8"))
                self._name_mappings = data.get("mappings", {})
                logger.info("加载名称映射: %d 条", len(self._name_mappings))
            except Exception as e:
                logger.warning("加载名称映射失败: %s", e)

    def save_name_mappings(self, mappings: dict[str, str]):
        """保存名称映射"""
        self._name_mappings = mappings
        NAME_MAPPINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
        data = {"mappings": mappings, "version": 1}
        NAME_MAPPINGS_PATH.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        logger.info("保存名称映射: %d 条", len(mappings))

    def get_name_mappings(self) -> dict[str, str]:
        return dict(self._name_mappings)

    def add_name_mapping(self, prompt_name: str, material_name: str):
        """添加一条名称映射：提示词中的人名 → 素材表中的人名"""
        self._name_mappings[prompt_name] = material_name
        self.save_name_mappings(self._name_mappings)

    # ── 匹配 ──

    def match_materials(self, prompt_text: str) -> list[CharacterMaterial]:
        """从提示词中匹配素材：精确匹配 + 映射回退"""
        matched: list[CharacterMaterial] = []
        seen: set[str] = set()

        for mat in self._materials:
            # 直接精确匹配
            if mat.character_name in prompt_text:
                if mat.character_name not in seen:
                    matched.append(mat)
                    seen.add(mat.character_name)
                continue

            # 映射回退：看提示词中是否包含映射来源
            for prompt_name, material_name in self._name_mappings.items():
                if material_name == mat.character_name and prompt_name in prompt_text:
                    if mat.character_name not in seen:
                        matched.append(mat)
                        seen.add(mat.character_name)
                    break

        logger.debug("提示词匹配素材: %d 条", len(matched))
        return matched

    def find_unmatched_names(self, prompt_text: str) -> list[str]:
        """找出提示词中未匹配到素材的人名"""
        # 简单启发式：找连续2-4个中文字符
        import re
        candidates = set(re.findall(r"[一-鿿]{2,4}", prompt_text))
        # 过滤常见非人名词汇
        skip = {"画面", "镜头", "特写", "中景", "近景", "远景", "对话", "动作", "表情",
                "场景", "室内", "室外", "白天", "黑夜", "微笑", "愤怒", "悲伤", "坐在",
                "站在", "走向", "看着", "拿出", "放在", "转身", "离开", "我们", "这个",
                "那个", "什么", "怎么", "自己", "没有", "一个", "可以", "知道", "就是"}
        candidates -= skip

        # 已匹配的
        matched_names = {m.character_name for m in self.match_materials(prompt_text)}
        # 再检查映射表中的来源名
        for prompt_name in self._name_mappings:
            if prompt_name in prompt_text:
                matched_names.add(prompt_name)

        return [c for c in candidates if c not in matched_names]
