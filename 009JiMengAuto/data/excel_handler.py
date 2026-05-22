"""Excel 文件读取 - 按需求文档格式"""

import logging
import re
from pathlib import Path
from typing import Optional

import pandas as pd

from data.models import MaterialInfo, MaterialType
from utils.helpers import parse_ratio, infer_material_type, validate_duration, validate_ratio

logger = logging.getLogger(__name__)


class ExcelValidationError(Exception):
    """Excel 验证错误"""
    pass


def read_prompt_excel(path: str) -> list[dict]:
    """读取提示词表

    按需求文档，列定义：
    - 序号（整数）：任务唯一编号，从1开始递增
    - 时长（整数）：视频时长，单位：秒，范围：5~15
    - 比例（字符串）：视频宽高比，可选值：16:9 / 9:16 / 1:1 / 4:3
    - 提示词内容（字符串）：完整的AI生成提示词文本

    场次名根据序号自动生成，格式为"第N场"

    返回：[{seq, scene, duration, ratio, prompt}, ...]
    """
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"提示词表不存在: {path}")

    df = pd.read_excel(path, dtype=str)

    # 必须包含的列（去除场次列）
    expected = {"序号", "时长", "比例", "提示词内容"}
    actual = set(df.columns)
    missing = expected - actual
    if missing:
        raise ExcelValidationError(f"提示词表缺少列: {', '.join(missing)}")

    rows = []
    warnings = []

    for idx, row in df.iterrows():
        # 序号
        seq_raw = row.get("序号", "")
        try:
            seq = int(float(str(seq_raw)))
        except (ValueError, TypeError):
            warnings.append(f"第{idx+2}行序号格式有误: {seq_raw}")
            seq = idx + 1

        # 场次：根据序号自动生成
        scene = f"第{seq}场"

        # 时长
        duration_raw = row.get("时长", "")
        try:
            duration = int(float(str(duration_raw)))
        except (ValueError, TypeError):
            duration = 12
            warnings.append(f"第{idx+2}行时长格式有误，默认使用12秒")

        # 验证时长范围
        valid, msg = validate_duration(duration)
        if not valid:
            warnings.append(f"第{idx+2}行: {msg}")
            duration = max(5, min(15, duration))  # 自动修正

        # 比例
        ratio_raw = str(row.get("比例", "") or "")
        ratio = parse_ratio(ratio_raw)

        # 验证比例
        valid, msg = validate_ratio(ratio)
        if not valid:
            warnings.append(f"第{idx+2}行: {msg}")

        # 提示词内容
        prompt = str(row.get("提示词内容", "") or "").strip()
        if not prompt:
            warnings.append(f"第{idx+2}行提示词为空，已跳过")
            continue

        rows.append({
            "seq": seq,
            "scene": scene,
            "duration": duration,
            "ratio": ratio,
            "prompt": prompt,
        })

    if warnings:
        logger.warning("提示词表导入警告:\n%s", "\n".join(warnings))

    logger.info("读取提示词表: %s, 有效数据 %d 条", path, len(rows))
    return rows


def read_character_excel(path: str) -> dict[str, list[MaterialInfo]]:
    """读取人物对照表

    按需求文档，行式结构：
    - 第一列：人物名字
    - 后续列：各素材路径，列名格式如 "苏晚（图片）" 或 "陈景明音色（音频）"

    示例：
    人物名字    苏晚（图片）    陈景明（图片）    苏晚音色（音频）
    苏晚        E:\\角色图\\苏晚.jpg   E:\\角色图\\陈景明.jpg   E:\\音色\\苏晚.wav
    陈景明      E:\\角色图\\陈景明2.jpg  E:\\角色图\\陈景明3.jpg  E:\\音色\\陈景明.wav

    返回：{人物名: [MaterialInfo列表]}
    """
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"人物对照表不存在: {path}")

    df = pd.read_excel(path, dtype=str)

    # 必须包含"人物名字"列
    if "人物名字" not in df.columns:
        raise ExcelValidationError("人物对照表缺少'人物名字'列")

    result: dict[str, list[MaterialInfo]] = {}
    warnings = []

    for idx, row in df.iterrows():
        char_name = str(row.get("人物名字", "") or "").strip()
        if not char_name:
            continue

        materials: list[MaterialInfo] = []

        # 遍历后续列（素材路径）
        for col_name in df.columns:
            if col_name == "人物名字":
                continue

            file_path = str(row.get(col_name, "") or "").strip()
            if not file_path:
                continue

            # 从列名推断素材类型
            mtype = _infer_type_from_column(col_name, file_path)

            # 验证文件
            exists = Path(file_path).exists()
            file_size = 0
            ext = Path(file_path).suffix.lower() if file_path else ""
            if exists:
                file_size = Path(file_path).stat().st_size

            mat = MaterialInfo(
                character_name=char_name,
                file_path=file_path,
                material_type=MaterialType(mtype),
                file_size=file_size,
                file_extension=ext,
                exists=exists,
                column_name=col_name,
            )
            materials.append(mat)

            if not exists:
                warnings.append(f"人物'{char_name}'素材文件不存在: {file_path}")

        if materials:
            result[char_name] = materials

    if warnings:
        logger.warning("人物对照表导入警告:\n%s", "\n".join(warnings))

    logger.info("读取人物对照表: %s, 人物 %d 个, 素材 %d 条",
                path, len(result), sum(len(m) for m in result.values()))
    return result


def _infer_type_from_column(col_name: str, file_path: str) -> str:
    """从列名和文件路径推断素材类型"""
    # 从列名推断
    col_lower = col_name.lower()
    if "图片" in col_lower or "image" in col_lower or "形象" in col_lower:
        return "image"
    if "音频" in col_lower or "音色" in col_lower or "audio" in col_lower or "声音" in col_lower:
        return "audio"
    if "视频" in col_lower or "video" in col_lower:
        return "video"

    # 从文件路径推断
    return infer_material_type(file_path)


def match_materials_for_prompt(
    prompt: str,
    character_data: dict[str, list[MaterialInfo]],
    scene_characters: Optional[list[str]] = None
) -> list[MaterialInfo]:
    """为提示词匹配素材

    Args:
        prompt: 提示词文本
        character_data: 人物对照表数据 {人物名: [素材列表]}
        scene_characters: 该场次关联的人物名列表（如果已知）

    Returns:
        匹配到的素材列表
    """
    matched: list[MaterialInfo] = []
    seen_paths: set[str] = set()

    # 如果有明确的人物列表，直接匹配
    if scene_characters:
        for char_name in scene_characters:
            if char_name in character_data:
                for mat in character_data[char_name]:
                    if mat.file_path not in seen_paths:
                        matched.append(mat)
                        seen_paths.add(mat.file_path)

    # 否则，尝试从提示词中提取人物名
    if not matched:
        # 尝试精确匹配人物名
        for char_name, mats in character_data.items():
            if char_name in prompt:
                for mat in mats:
                    if mat.file_path not in seen_paths:
                        matched.append(mat)
                        seen_paths.add(mat.file_path)

    logger.debug("提示词匹配素材: %d 条", len(matched))
    return matched


def get_scene_characters(scene: str) -> Optional[list[str]]:
    """从场次名提取人物列表（如果有规律命名）"""
    # 例如："第1场_苏晚陈景明对话"
    # 提取出苏晚、陈景明
    # 这里暂时返回None，需要根据实际命名规则调整
    return None


def create_sample_prompt_excel(output_path: str) -> None:
    """创建示例提示词表（用于测试）"""
    sample_data = {
        "序号": [1, 2, 3, 4, 5, 6, 7],
        "时长": [12, 10, 12, 14, 13, 12, 14],
        "比例": ["16:9", "16:9", "16:9", "16:9", "16:9", "16:9", "9:16"],
        "提示词内容": [
            "猪场办公室内景。破旧账本特写，书写潦草的数字。光线昏暗，灯泡摇晃。镜头特写转中景缓推。",
            "村民围堵货车。愤怒的争吵场景，人群嘈杂，情绪激动。镜头宽景转近景扫过人群。",
            "老村长家中。昏暗灯光下的账本，老人凝神思考。自然光，暖色调。",
            "猪场门口，夕阳余晖。村民们聚集议论。情绪从愤怒转为沉默。镜头从全景推近特写面部。",
            "老村长家里书房。桌上摆满各类账本。老人戴着老花眼镜仔细翻阅。台灯昏黄。",
            "王大爷骑电动车匆忙进村。表情凝重愤怒，急刹车停在人群前。",
            "村口超市门口。一群老人围坐议论，手里拿着账本复印件。神情凝重。",
        ]
    }
    df = pd.DataFrame(sample_data)
    df.to_excel(output_path, index=False)
    logger.info("创建示例提示词表: %s", output_path)


def create_sample_character_excel(output_path: str) -> None:
    """创建示例人物对照表（用于测试）"""
    sample_data = {
        "人物名字": ["苏晚", "陈景明", "老村长"],
        "苏晚（图片）": [
            "E:\\角色图\\苏晚正面.jpg",
            "E:\\角色图\\陈景明.jpg",
            "E:\\角色图\\老村长.jpg",
        ],
        "陈景明（图片）": [
            "E:\\角色图\\陈景明.jpg",
            "E:\\角色图\\陈景明3.jpg",
            "",
        ],
        "苏晚音色（音频）": [
            "E:\\真人音色\\苏晚.WAV",
            "E:\\真人音色\\陈景明音色.WAV",
            "E:\\真人音色\\老村长音色.WAV",
        ],
    }
    df = pd.DataFrame(sample_data)
    df.to_excel(output_path, index=False)
    logger.info("创建示例人物对照表: %s", output_path)