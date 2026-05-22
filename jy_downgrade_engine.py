"""
降级引擎 — 修改版本号、剥离不兼容数据、预览变更。
"""
import copy
import json
from pathlib import Path

from jy_version_map import (
    MAJOR_VERSIONS, VERSION_KEYS, VERSION_TRACK_TYPES, VERSION_EFFECT_TYPES,
    extract_major_version, extract_minor_version,
    get_unsupported_keys, get_supported_track_types, get_supported_effect_types,
    is_version_higher,
)
from jy_draft_parser import DraftInfo, DraftParser


class DowngradeResult:
    """降级操作结果"""
    def __init__(self):
        self.success = False
        self.version_changes = 0        # 修改了多少个版本号字段
        self.keys_removed = []          # 被移除的 key 列表（路径+key名）
        self.tracks_removed = []        # 被移除的 track ID（因类型不支持）
        self.effects_removed = []       # 被移除的效果类型
        self.warnings = []              # 警告信息
        self.errors = []                # 错误信息


class DowngradeEngine:
    """剪映草稿降级引擎"""

    def __init__(self):
        pass

    def preview_downgrade(self, draft: DraftInfo, target_major: str,
                          mode: str = "full") -> DowngradeResult:
        """
        预览降级操作，不实际修改文件。
        mode: 'version_only' | 'strip' | 'full'
        """
        result = DowngradeResult()
        source_major = draft.major_version

        if source_major == "unknown":
            result.errors.append("无法检测源版本号，请手动指定")
            return result

        if target_major not in MAJOR_VERSIONS:
            result.errors.append(f"目标版本 {target_major} 无效")
            return result

        if not is_version_higher(source_major, target_major):
            result.warnings.append(f"源版本 ({source_major}) 不高于目标版本 ({target_major})，无需降级")

        content = copy.deepcopy(draft.content_data)

        # 统计版本号变更
        result.version_changes = self._count_version_fields(content)

        # 统计需要移除的内容
        if mode in ("strip", "full"):
            self._analyze_content_changes(content, source_major, target_major, result)

        result.success = True
        return result

    def execute_downgrade(self, draft: DraftInfo, target_major: str, target_minor: str = None,
                          mode: str = "full") -> DowngradeResult:
        """
        执行降级操作，直接修改 JSON 文件。

        Args:
            draft: 草稿信息对象
            target_major: 目标大版本 (如 '5.x')
            target_minor: 目标次版本号 (如 '5.3'), 留空则用 target_major 推断
            mode: 'version_only' — 仅改版本号
                  'strip' — 改版本号 + 移除不兼容 key 和特性
                  'full' — 改版本号 + 移除不兼容 + 结构转换
        """
        result = DowngradeResult()
        source_major = draft.major_version

        if source_major == "unknown":
            result.errors.append("无法检测源版本号")
            return result

        if target_major not in MAJOR_VERSIONS:
            result.errors.append(f"目标版本 {target_major} 无效")
            return result

        if target_minor is None:
            target_minor = target_major.replace("x", "0") + ".0"

        # 修改 draft_info.json
        info = copy.deepcopy(draft.info_data) if draft.info_json_path else None
        if info:
            ver_changes = DraftParser.set_version_in_dict(info, target_minor)
            result.version_changes += ver_changes

        # 修改 draft_content.json
        content = copy.deepcopy(draft.content_data) if draft.content_json_path else None
        if content:
            ver_changes = DraftParser.set_version_in_dict(content, target_minor)
            result.version_changes += ver_changes

            if mode in ("strip", "full"):
                self._strip_incompatible(content, source_major, target_major, result)

        # 写回文件
        try:
            DraftParser.save_draft(draft, content_data=content, info_data=info)
            result.success = True
        except Exception as e:
            result.errors.append(f"文件写入失败: {e}")

        return result

    def _count_version_fields(self, data: dict) -> int:
        """递归统计版本字段数量"""
        count = 0
        if not isinstance(data, dict):
            return count
        for key, value in data.items():
            key_lower = key.lower().replace(" ", "_")
            if key_lower in DraftParser.VERSION_FIELD_CANDIDATES:
                if isinstance(value, str):
                    count += 1
            elif isinstance(value, dict):
                count += self._count_version_fields(value)
            elif isinstance(value, list):
                for item in value:
                    if isinstance(item, dict):
                        count += self._count_version_fields(item)
        return count

    def _analyze_content_changes(self, content: dict, from_ver: str, to_ver: str,
                                  result: DowngradeResult):
        """分析需要移除的内容（不实际修改）"""
        # 检查顶层 key
        unsupported_root = get_unsupported_keys(from_ver, to_ver, "root")
        for key in unsupported_root:
            if key in content:
                result.keys_removed.append(f"draft_content.json → {key}")

        # 检查 track 中的不兼容项
        tracks = content.get("tracks", [])
        supported_track_types = get_supported_track_types(to_ver)
        unsupported_track_keys = get_unsupported_keys(from_ver, to_ver, "track")
        unsupported_segment_keys = get_unsupported_keys(from_ver, to_ver, "segment")
        unsupported_effect_types = get_supported_effect_types(from_ver) - get_supported_effect_types(to_ver)

        for track in tracks:
            if not isinstance(track, dict):
                continue
            track_type = track.get("type", "")

            # 检查 track 类型
            if track_type and supported_track_types and track_type not in supported_track_types:
                result.tracks_removed.append(f"Track[{track.get('id', '?')}] type={track_type}")

            # 检查 track 不支持的 key
            for key in unsupported_track_keys:
                if key in track:
                    result.keys_removed.append(f"Track[{track.get('id', '?')}] → {key}")

            # 检查 segment
            for seg in track.get("segments", []):
                if not isinstance(seg, dict):
                    continue
                for key in unsupported_segment_keys:
                    if key in seg:
                        result.keys_removed.append(f"Segment[{seg.get('id', '?')}] → {key}")

                # 检查效果
                effects = seg.get("effects", []) or seg.get("filters", [])
                for eff in effects:
                    eff_type = eff.get("type", "") or eff.get("name", "")
                    if eff_type and eff_type in unsupported_effect_types:
                        result.effects_removed.append(f"Segment[{seg.get('id', '?')}] effect={eff_type}")

        # 检查 materials 中不支持的 key
        materials = content.get("materials", {})
        unsupported_material_keys = get_unsupported_keys(from_ver, to_ver, "material")
        for mat_cat, mat_list in materials.items():
            if not isinstance(mat_list, list):
                continue
            for mat in mat_list:
                if not isinstance(mat, dict):
                    continue
                for key in unsupported_material_keys:
                    if key in mat:
                        result.keys_removed.append(f"Material[{mat.get('id', '?')}] → {key}")

        if not result.keys_removed and not result.tracks_removed and not result.effects_removed:
            result.warnings.append("未检测到需要移除的兼容性差异（结构兼容）")

    def _strip_incompatible(self, content: dict, from_ver: str, to_ver: str,
                            result: DowngradeResult):
        """实际移除不兼容数据"""
        # 移除顶层不支持的 key
        unsupported_root = get_unsupported_keys(from_ver, to_ver, "root")
        for key in unsupported_root:
            if key in content:
                del content[key]
                result.keys_removed.append(f"draft_content.json → {key}")

        # 处理 tracks
        unsupported_track_keys = get_unsupported_keys(from_ver, to_ver, "track")
        unsupported_segment_keys = get_unsupported_keys(from_ver, to_ver, "segment")
        supported_track_types = get_supported_track_types(to_ver)
        unsupported_effect_types = get_supported_effect_types(from_ver) - get_supported_effect_types(to_ver)
        unsupported_material_keys = get_unsupported_keys(from_ver, to_ver, "material")

        tracks = content.get("tracks", [])
        new_tracks = []

        for track in tracks:
            if not isinstance(track, dict):
                new_tracks.append(track)
                continue

            track_type = track.get("type", "")
            # 跳过不支持的 track 类型
            if track_type and supported_track_types and track_type not in supported_track_types:
                result.tracks_removed.append(f"Track[{track.get('id', '?')}] type={track_type}")
                continue

            # 移除 track 级别不支持的 key
            for key in unsupported_track_keys:
                if key in track:
                    del track[key]
                    result.keys_removed.append(f"Track[{track.get('id', '?')}] → {key}")

            # 处理 segments
            for seg in track.get("segments", []):
                if not isinstance(seg, dict):
                    continue
                for key in unsupported_segment_keys:
                    if key in seg:
                        del seg[key]
                        result.keys_removed.append(f"Segment[{seg.get('id', '?')}] → {key}")

                # 移除不支持的效果
                for eff_key in ("effects", "filters"):
                    eff_list = seg.get(eff_key, [])
                    if isinstance(eff_list, list):
                        new_eff = []
                        for eff in eff_list:
                            eff_type = eff.get("type", "") or eff.get("name", "")
                            if eff_type in unsupported_effect_types:
                                result.effects_removed.append(f"Segment[{seg.get('id', '?')}] {eff_key}={eff_type}")
                                continue
                            new_eff.append(eff)
                        seg[eff_key] = new_eff

            new_tracks.append(track)

        content["tracks"] = new_tracks

        # 移除 materials 中不支持的 key
        materials = content.get("materials", {})
        for mat_cat, mat_list in materials.items():
            if not isinstance(mat_list, list):
                continue
            for mat in mat_list:
                if not isinstance(mat, dict):
                    continue
                for key in unsupported_material_keys:
                    if key in mat:
                        del mat[key]
                        result.keys_removed.append(f"Material[{mat.get('id', '?')}] → {key}")
