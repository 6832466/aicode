import asyncio
import json
import logging
import webbrowser
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QScrollArea, QWidget, QCheckBox, QLineEdit, QMessageBox,
)
from PySide6.QtGui import QPixmap
from qfluentwidgets import (
    PrimaryPushButton, PushButton, BodyLabel, StrongBodyLabel,
    InfoBar, InfoBarPosition, LineEdit,
)

from app.config import char_assets_path, char_assets_write_path, app_icon_path

logger = logging.getLogger(__name__)


class AssetManagerDialog(QDialog):
    assets_saved = Signal()

    def __init__(self, client, parent=None):
        super().__init__(parent)
        self.setWindowTitle("角色素材管理 - 从 Seedance 引用加载")
        self.resize(860, 640)
        self._set_icon()
        self._client = client
        self._team_id = getattr(client, '_team_id', '') or ''
        self._references: list[dict] = []
        self._ref_widgets: list[dict] = []
        self._setup_ui()

    def _set_icon(self):
        try:
            from PySide6.QtGui import QIcon
            p = app_icon_path()
            if p.exists():
                self.setWindowIcon(QIcon(str(p)))
        except Exception:
            pass

    @property
    def _assets_read_path(self) -> Path:
        """Read path with legacy fallback for backward compatibility."""
        return char_assets_path(self._team_id)

    @property
    def _assets_write_path(self) -> Path:
        """Write path — always team-specific, never falls back to shared file."""
        return char_assets_write_path(self._team_id)

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        # --- Section 1: Manual add ---
        manual_title = StrongBodyLabel("手动添加素材")
        layout.addWidget(manual_title)

        manual_row = QHBoxLayout()
        manual_row.addWidget(BodyLabel("引用名:"))
        self._manual_ref = LineEdit()
        self._manual_ref.setPlaceholderText("如 chenfeng")
        self._manual_ref.setFixedWidth(120)
        manual_row.addWidget(self._manual_ref)

        manual_row.addWidget(BodyLabel("Asset ID:"))
        self._manual_aid = LineEdit()
        self._manual_aid.setPlaceholderText("RunwayML 素材 ID")
        self._manual_aid.setFixedWidth(260)
        manual_row.addWidget(self._manual_aid)

        self._btn_manual_add = PrimaryPushButton("添加")
        self._btn_manual_add.clicked.connect(self._on_manual_add)
        manual_row.addWidget(self._btn_manual_add)
        manual_row.addStretch()
        layout.addLayout(manual_row)

        # --- Section 2: Fetch from Seedance references ---
        sep1 = QWidget()
        sep1.setFixedHeight(1)
        sep1.setStyleSheet("background: #444;")
        layout.addWidget(sep1)

        fetch_title = StrongBodyLabel("一键加载 Seedance 角色引用")
        layout.addWidget(fetch_title)

        fetch_row = QHBoxLayout()
        self._btn_fetch = PrimaryPushButton("从网站加载引用图片")
        self._btn_fetch.clicked.connect(self._on_fetch)
        fetch_row.addWidget(self._btn_fetch)

        self._btn_open_assets = PushButton("打开引用管理页面")
        self._btn_open_assets.clicked.connect(self._on_open_page)
        fetch_row.addWidget(self._btn_open_assets)

        self._status_label = BodyLabel("点击加载按钮获取 Seedance 中已保存的角色引用")
        self._status_label.setStyleSheet("color: #888;")
        fetch_row.addWidget(self._status_label)
        fetch_row.addStretch()
        layout.addLayout(fetch_row)

        fetch_hint = BodyLabel("这些引用就是在 Seedance 2.0 中已保存的角色参考图。勾选需要的，引用名（tag）会自动填充，可直接保存或修改。\n最多加载最近 100 个引用，避免加载过慢。")
        fetch_hint.setStyleSheet("color: #888; font-size: 11px;")
        layout.addWidget(fetch_hint)

        # Scrollable list
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        self._list_widget = QWidget()
        self._list_layout = QVBoxLayout(self._list_widget)
        self._list_layout.setSpacing(6)
        self._list_layout.addStretch()
        scroll.setWidget(self._list_widget)
        layout.addWidget(scroll, stretch=1)

        # Bottom buttons
        btn_row = QHBoxLayout()
        self._btn_select_all = PushButton("全选")
        self._btn_select_all.clicked.connect(lambda: self._toggle_all(True))
        self._btn_deselect_all = PushButton("取消全选")
        self._btn_deselect_all.clicked.connect(lambda: self._toggle_all(False))
        self._btn_auto_name = PushButton("用 tag 自动填名")
        self._btn_auto_name.clicked.connect(self._on_auto_name)

        btn_row.addWidget(self._btn_select_all)
        btn_row.addWidget(self._btn_deselect_all)
        btn_row.addWidget(self._btn_auto_name)
        btn_row.addStretch()

        self._btn_cancel = PushButton("取消")
        self._btn_cancel.clicked.connect(self.reject)
        self._btn_save = PrimaryPushButton("保存到素材库")
        self._btn_save.clicked.connect(self._on_save)

        btn_row.addWidget(self._btn_cancel)
        btn_row.addWidget(self._btn_save)
        layout.addLayout(btn_row)

    def _on_open_page(self):
        team_id = getattr(self._client, '_team_id', '') or 'LeleRpa'
        webbrowser.open(
            f"https://app.runwayml.com/video-tools/teams/{team_id}/ai-tools/generate"
            "?tool=video&mode=tools"
        )

    # ------------------------------------------------------------------
    # Fetch
    # ------------------------------------------------------------------

    def _on_fetch(self):
        self._btn_fetch.setEnabled(False)
        self._status_label.setText("加载中…")
        self._status_label.setStyleSheet("color: #FF9800;")
        asyncio.ensure_future(self._do_fetch())

    async def _do_fetch(self):
        try:
            self._references = await self._client.get_asset_references(limit=100)
            self._build_list()
            more = "+" if len(self._references) >= 100 else ""
            self._status_label.setText(f"已加载 {len(self._references)}{more} 个角色引用（最多100个）")
            self._status_label.setStyleSheet("color: #4CAF50;")
        except Exception as e:
            logger.exception("加载角色引用失败")
            self._status_label.setText(f"加载失败: {e}")
            self._status_label.setStyleSheet("color: #F44336;")
        finally:
            self._btn_fetch.setEnabled(True)

    # ------------------------------------------------------------------
    # Build list UI
    # ------------------------------------------------------------------

    def _build_list(self):
        # Clear existing
        while self._list_layout.count() > 1:
            item = self._list_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._ref_widgets.clear()

        # Load existing char_assets to pre-check
        existing = {}
        if self._assets_read_path.exists():
            try:
                existing = json.loads(self._assets_read_path.read_text(encoding="utf-8"))
            except Exception:
                pass

        # Reverse map: assetId -> ref_name
        asset_id_to_ref = {}
        for ref_name, info in existing.items():
            aid = info.get("assetId", "")
            if aid:
                asset_id_to_ref[aid] = ref_name

        for ref in self._references:
            tag = ref.get("tag", "")
            asset = ref.get("asset", {})
            asset_id = asset.get("id", "")

            row = QWidget()
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(4, 4, 4, 4)
            row_layout.setSpacing(8)

            # Thumbnail
            thumb_label = QLabel()
            thumb_label.setFixedSize(64, 64)
            thumb_label.setStyleSheet("border: 1px solid #555; border-radius: 4px; background: #222;")
            thumb_label.setScaledContents(True)
            thumb_label.setAlignment(Qt.AlignCenter)

            preview_url = asset.get("previewUrl", "")
            if preview_url:
                asyncio.ensure_future(self._load_thumbnail(preview_url, thumb_label))
            else:
                thumb_label.setText("🖼")
                thumb_label.setAlignment(Qt.AlignCenter)

            row_layout.addWidget(thumb_label)

            # Info column
            info_layout = QVBoxLayout()
            name = asset.get("name", "未命名")[:50]
            tag_label = StrongBodyLabel(f"Tag: {tag}")
            name_label = BodyLabel(name)
            name_label.setWordWrap(True)
            name_label.setStyleSheet("color: #aaa; font-size: 11px;")
            id_label = BodyLabel(f"ID: {asset_id[:24]}…")
            id_label.setStyleSheet("color: #666; font-size: 10px;")
            info_layout.addWidget(tag_label)
            info_layout.addWidget(name_label)
            info_layout.addWidget(id_label)

            row_layout.addLayout(info_layout, stretch=1)

            # Ref name input (pre-filled with tag)
            ref_input = QLineEdit()
            ref_input.setPlaceholderText("引用名")
            ref_input.setFixedWidth(130)

            # Pre-fill: prefer existing mapping, otherwise use tag
            if asset_id in asset_id_to_ref:
                ref_input.setText(asset_id_to_ref[asset_id])
                ref_input.setStyleSheet("color: #4CAF50;")
            elif tag:
                ref_input.setText(tag)

            row_layout.addWidget(ref_input)

            # Checkbox — pre-check if already in char_assets
            cb = QCheckBox()
            cb.setChecked(asset_id in asset_id_to_ref)
            row_layout.addWidget(cb)

            self._list_layout.insertWidget(self._list_layout.count() - 1, row)
            self._ref_widgets.append({
                "ref": ref,
                "checkbox": cb,
                "ref_input": ref_input,
            })

    async def _load_thumbnail(self, url: str, label: QLabel):
        try:
            import aiohttp
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as resp:
                    if resp.status == 200:
                        data = await resp.read()
                        pixmap = QPixmap()
                        pixmap.loadFromData(data)
                        if not pixmap.isNull():
                            label.setPixmap(pixmap.scaled(
                                64, 64, Qt.KeepAspectRatio, Qt.SmoothTransformation
                            ))
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def _on_auto_name(self):
        """Auto-fill ref_input with tag for unchecked items."""
        for w in self._ref_widgets:
            if w["ref_input"].text().strip():
                continue  # Don't overwrite already named ones
            tag = w["ref"].get("tag", "")
            if tag:
                w["ref_input"].setText(tag)

    def _toggle_all(self, checked: bool):
        for w in self._ref_widgets:
            w["checkbox"].setChecked(checked)

    def _on_manual_add(self):
        ref_name = self._manual_ref.text().strip()
        asset_id = self._manual_aid.text().strip()
        if not ref_name or not asset_id:
            InfoBar.warning("请填写完整", "引用名和 Asset ID 都不能为空",
                          position=InfoBarPosition.TOP, parent=self)
            return
        try:
            existing = {}
            if self._assets_read_path.exists():
                try:
                    existing = json.loads(self._assets_read_path.read_text(encoding="utf-8"))
                except Exception:
                    pass
            existing[ref_name] = {
                "assetId": asset_id,
                "url": "",
            }
            write_path = self._assets_write_path
            write_path.parent.mkdir(parents=True, exist_ok=True)
            write_path.write_text(
                json.dumps(existing, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            self.assets_saved.emit()
            InfoBar.success(
                f"已添加 {ref_name}",
                f"引用名: {ref_name}, Asset ID: {asset_id}",
                position=InfoBarPosition.TOP, parent=self.parent(),
            )
            self._manual_ref.clear()
            self._manual_aid.clear()
        except Exception as e:
            logger.exception("手动添加素材失败")
            QMessageBox.warning(self, "添加失败", str(e))

    def _on_save(self):
        try:
            existing = {}
            if self._assets_read_path.exists():
                try:
                    existing = json.loads(self._assets_read_path.read_text(encoding="utf-8"))
                except Exception:
                    pass

            added = 0
            for w in self._ref_widgets:
                if not w["checkbox"].isChecked():
                    continue
                ref_name = w["ref_input"].text().strip()
                if not ref_name:
                    continue
                asset = w["ref"].get("asset", {})
                existing[ref_name] = {
                    "assetId": asset.get("id", ""),
                    "url": asset.get("url", ""),
                }
                added += 1

            write_path = self._assets_write_path
            write_path.parent.mkdir(parents=True, exist_ok=True)
            write_path.write_text(
                json.dumps(existing, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

            self.assets_saved.emit()
            InfoBar.success(
                f"已保存 {added} 个角色素材",
                f"素材已写入 data/{self._team_id}/character_assets.json" if self._team_id else "素材已写入 data/character_assets.json",
                position=InfoBarPosition.TOP, parent=self.parent(),
            )
            self.accept()
        except Exception as e:
            logger.exception("保存素材失败")
            QMessageBox.warning(self, "保存失败", str(e))
