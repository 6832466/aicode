"""
剪映各版本功能映射表。
用户可以修改此文件来适配不同版本的剪映。
"""

# 大版本号列表（从旧到新）
MAJOR_VERSIONS = ["1.x", "2.x", "3.x", "4.x", "5.x", "6.x", "7.x", "8.x"]

# 补充完整版本号列表
MINOR_VERSIONS = [
    "1.0", "1.1", "1.2", "1.3",
    "2.0", "2.1", "2.2", "2.3",
    "3.0", "3.1", "3.2", "3.3", "3.4", "3.5",
    "4.0", "4.1", "4.2", "4.3", "4.4", "4.5",
    "5.0", "5.1", "5.2", "5.3", "5.4", "5.5",
    "6.0", "6.1", "6.2", "6.3", "6.4", "6.5", "6.6",
    "7.0", "7.1", "7.2", "7.3",
    "8.0", "8.1",
]

# 版本正则：从 "6.8.0.12345" 或 "6.8" 提取主版本号
VERSION_PATTERNS = {
    "full": r'(\d+)\.(\d+)(?:\.(\d+))?(?:\.(\d+))?',
    "major_only": r'(\d+)\.x',
}

# 各版本支持的内容 key （draft_content.json 顶层及深层 key）
# 较新版本会引入新 key，降级到旧版本时需移除不支持的 key
VERSION_KEYS = {
    "1.x": {
        "root": {"version", "draft_name", "tracks", "materials"},
        "track": {"id", "type", "segments", "is_visible", "attribute"},
        "segment": {"id", "material_id", "source_type", "target_timerange", "source_timerange", "attribute"},
        "material": {"id", "name", "type", "path", "duration"},
    },
    "2.x": {
        "root": {"version", "draft_name", "tracks", "materials"},
        "track": {"id", "type", "segments", "is_visible", "attribute", "volume"},
        "segment": {"id", "material_id", "source_type", "target_timerange", "source_timerange", "attribute", "speed"},
        "material": {"id", "name", "type", "path", "duration", "thumbnail"},
    },
    "3.x": {
        "root": {"version", "draft_name", "tracks", "materials"},
        "track": {"id", "type", "segments", "is_visible", "attribute", "volume", "order"},
        "segment": {"id", "material_id", "source_type", "target_timerange", "source_timerange", "attribute", "speed", "transition"},
        "material": {"id", "name", "type", "path", "duration", "thumbnail", "color"},
    },
    "4.x": {
        "root": {"version", "draft_name", "tracks", "materials", "canvas_ratio", "duration"},
        "track": {"id", "type", "segments", "is_visible", "attribute", "volume", "order", "muted"},
        "segment": {"id", "material_id", "source_type", "target_timerange", "source_timerange", "attribute", "speed", "transition", "animation"},
        "material": {"id", "name", "type", "path", "duration", "thumbnail", "color", "metadata"},
    },
    "5.x": {
        "root": {"version", "draft_name", "tracks", "materials", "canvas_ratio", "duration", "audio_setting"},
        "track": {"id", "type", "segments", "is_visible", "attribute", "volume", "order", "muted", "compound_id"},
        "segment": {"id", "material_id", "source_type", "target_timerange", "source_timerange", "attribute", "speed", "transition", "animation", "common_keyframes", "filters"},
        "material": {"id", "name", "type", "path", "duration", "thumbnail", "color", "metadata", "tags"},
    },
    "6.x": {
        "root": {"version", "draft_name", "tracks", "materials", "canvas_ratio", "duration", "audio_setting", "effect_track", "ai_setting"},
        "track": {"id", "type", "segments", "is_visible", "attribute", "volume", "order", "muted", "compound_id", "freeze_point"},
        "segment": {"id", "material_id", "source_type", "target_timerange", "source_timerange", "attribute", "speed", "transition", "animation", "common_keyframes", "filters", "ai_effect", "mask"},
        "material": {"id", "name", "type", "path", "duration", "thumbnail", "color", "metadata", "tags", "ai_generated"},
    },
    "7.x": {
        "root": {"version", "draft_name", "tracks", "materials", "canvas_ratio", "duration", "audio_setting", "effect_track", "ai_setting", "collaboration"},
        "track": {"id", "type", "segments", "is_visible", "attribute", "volume", "order", "muted", "compound_id", "freeze_point", "blend_mode"},
        "segment": {"id", "material_id", "source_type", "target_timerange", "source_timerange", "attribute", "speed", "transition", "animation", "common_keyframes", "filters", "ai_effect", "mask", "tracking_data", "voice_change"},
        "material": {"id", "name", "type", "path", "duration", "thumbnail", "color", "metadata", "tags", "ai_generated", "3d_transform"},
    },
    "8.x": {
        "root": {"version", "draft_name", "tracks", "materials", "canvas_ratio", "duration", "audio_setting", "effect_track", "ai_setting", "collaboration", "cloud_sync"},
        "track": {"id", "type", "segments", "is_visible", "attribute", "volume", "order", "muted", "compound_id", "freeze_point", "blend_mode", "hdr_mode"},
        "segment": {"id", "material_id", "source_type", "target_timerange", "source_timerange", "attribute", "speed", "transition", "animation", "common_keyframes", "filters", "ai_effect", "mask", "tracking_data", "voice_change", "motion_blur"},
        "material": {"id", "name", "type", "path", "duration", "thumbnail", "color", "metadata", "tags", "ai_generated", "3d_transform", "hdr_info"},
    },
}

# 各版本支持的 track 类型
VERSION_TRACK_TYPES = {
    "1.x": {"video", "audio", "text", "sticker", "effect"},
    "2.x": {"video", "audio", "text", "sticker", "effect", "filter", "transition"},
    "3.x": {"video", "audio", "text", "sticker", "effect", "filter", "transition", "animation", "subtitle"},
    "4.x": {"video", "audio", "text", "sticker", "effect", "filter", "transition", "animation", "subtitle", "compound"},
    "5.x": {"video", "audio", "text", "sticker", "effect", "filter", "transition", "animation", "subtitle", "compound", "mask"},
    "6.x": {"video", "audio", "text", "sticker", "effect", "filter", "transition", "animation", "subtitle", "compound", "mask", "ai_effect", "ai_voice"},
    "7.x": {"video", "audio", "text", "sticker", "effect", "filter", "transition", "animation", "subtitle", "compound", "mask", "ai_effect", "ai_voice", "ai_generate"},
    "8.x": {"video", "audio", "text", "sticker", "effect", "filter", "transition", "animation", "subtitle", "compound", "mask", "ai_effect", "ai_voice", "ai_generate", "3d_model"},
}

# 各版本支持的素材/效果类型
VERSION_EFFECT_TYPES = {
    "1.x": {"basic", "color_adjust", "blur"},
    "2.x": {"basic", "color_adjust", "blur", "sharpness", "vignette"},
    "3.x": {"basic", "color_adjust", "blur", "sharpness", "vignette", "lut", "chroma_key"},
    "4.x": {"basic", "color_adjust", "blur", "sharpness", "vignette", "lut", "chroma_key", "noise", "glow"},
    "5.x": {"basic", "color_adjust", "blur", "sharpness", "vignette", "lut", "chroma_key", "noise", "glow", "distortion", "particle"},
    "6.x": {"basic", "color_adjust", "blur", "sharpness", "vignette", "lut", "chroma_key", "noise", "glow", "distortion", "particle", "ai_style", "ai_beauty"},
    "7.x": {"basic", "color_adjust", "blur", "sharpness", "vignette", "lut", "chroma_key", "noise", "glow", "distortion", "particle", "ai_style", "ai_beauty", "ai_retouch", "ai_background"},
    "8.x": {"basic", "color_adjust", "blur", "sharpness", "vignette", "lut", "chroma_key", "noise", "glow", "distortion", "particle", "ai_style", "ai_beauty", "ai_retouch", "ai_background", "ai_relight"},
}


def extract_major_version(version_str: str) -> str:
    """从完整版本号提取主版本，如 '6.8.0' → '6.x'"""
    import re
    match = re.match(r'(\d+)', str(version_str))
    if match:
        major = match.group(1)
        major_ver = f"{major}.x"
        if major_ver in MAJOR_VERSIONS:
            return major_ver
    return "unknown"


def extract_minor_version(version_str: str) -> str:
    """从完整版本号提取次版本，如 '6.8.0.12345' → '6.8'"""
    import re
    match = re.match(r'(\d+\.\d+)', str(version_str))
    if match:
        return match.group(1)
    return "0.0"


def get_supported_keys(version: str, category: str) -> set:
    """获取指定版本的某类别支持的所有 key"""
    return VERSION_KEYS.get(version, {}).get(category, set())


def get_supported_track_types(version: str) -> set:
    """获取指定版本支持的 track 类型"""
    return VERSION_TRACK_TYPES.get(version, set())


def get_supported_effect_types(version: str) -> set:
    """获取指定版本支持的效果类型"""
    return VERSION_EFFECT_TYPES.get(version, set())


def is_version_higher(ver_a: str, ver_b: str) -> bool:
    """判断 ver_a 是否比 ver_b 高"""
    a_idx = MAJOR_VERSIONS.index(ver_a) if ver_a in MAJOR_VERSIONS else -1
    b_idx = MAJOR_VERSIONS.index(ver_b) if ver_b in MAJOR_VERSIONS else -1
    return a_idx > b_idx


def get_all_lower_versions(target_version: str) -> list:
    """获取所有比目标版本低的版本列表"""
    if target_version not in MAJOR_VERSIONS:
        return []
    idx = MAJOR_VERSIONS.index(target_version)
    return MAJOR_VERSIONS[:idx]


def get_unsupported_keys(from_version: str, to_version: str, category: str) -> set:
    """计算降级时需要移除的 key"""
    from_keys = VERSION_KEYS.get(from_version, {}).get(category, set())
    to_keys = VERSION_KEYS.get(to_version, {}).get(category, set())
    return from_keys - to_keys
