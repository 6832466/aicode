import logging

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout
from qfluentwidgets import (
    PushButton, PrimaryPushButton, BodyLabel, StrongBodyLabel,
    LineEdit, SpinBox, ComboBox, SwitchButton,
    InfoBar, InfoBarPosition, CardWidget, FluentIcon,
)

from app.config import (
    DEFAULT_TEAM_ID,
    SETTINGS_KEY_TOKEN, SETTINGS_KEY_TEAM_ID,
    SETTINGS_KEY_OUTPUT_DIR, SETTINGS_KEY_POLL,
    SETTINGS_KEY_RESOLUTION, SETTINGS_KEY_AUDIO,
    SETTINGS_KEY_PREFIX, SETTINGS_KEY_SUFFIX,
    SETTINGS_KEY_SESSION_ID, SETTINGS_KEY_ASSET_GROUP_ID,
    settings_scope,
)

logger = logging.getLogger(__name__)


class SettingsPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("settingsPage")
        self._main_window = parent
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 12, 20, 12)
        layout.setSpacing(16)

        # --- Auth card ---
        auth_card, auth_layout = self._make_card("身份认证")
        auth_layout.setSpacing(8)

        tok_row = QHBoxLayout()
        tok_row.addWidget(BodyLabel("JWT 令牌:"))
        self._token_edit = LineEdit()
        self._token_edit.setPlaceholderText("粘贴 JWT 令牌到此处")
        self._token_edit.setPlaceholderText("从浏览器 localStorage 粘贴 RW_USER_TOKEN")
        tok_row.addWidget(self._token_edit, stretch=1)
        auth_layout.addLayout(tok_row)

        self._btn_test = PushButton("测试连接")
        self._btn_test.clicked.connect(self._on_test_token)
        self._btn_get_token = PrimaryPushButton("一键获取令牌")
        self._btn_get_token.clicked.connect(self._on_get_token)

        test_row = QHBoxLayout()
        test_row.addWidget(self._btn_test)
        test_row.addWidget(self._btn_get_token)
        test_row.addStretch()
        auth_layout.addLayout(test_row)
        self._test_result = BodyLabel("")
        self._test_result.setStyleSheet("color: #888;")
        auth_layout.addWidget(self._test_result)

        team_row = QHBoxLayout()
        team_row.addWidget(BodyLabel("团队 ID:"))
        self._team_edit = LineEdit()
        self._team_edit.setText(DEFAULT_TEAM_ID)
        team_row.addWidget(self._team_edit)
        auth_layout.addLayout(team_row)

        # Material manager button
        mat_row = QHBoxLayout()
        self._btn_manage_assets = PrimaryPushButton("角色素材管理")
        self._btn_manage_assets.clicked.connect(self._on_manage_assets)
        mat_row.addWidget(self._btn_manage_assets)
        mat_row.addWidget(BodyLabel("一键从网站加载角色参考图"))
        mat_row.addStretch()
        auth_layout.addLayout(mat_row)

        layout.addWidget(auth_card)

        # --- Session info card ---
        sess_card, sess_layout = self._make_card("会话信息（可选）")
        sess_layout.setSpacing(8)

        sid_row = QHBoxLayout()
        sid_row.addWidget(BodyLabel("会话 ID:"))
        self._session_edit = LineEdit()
        self._session_edit.setPlaceholderText("留空则自动检测")
        sid_row.addWidget(self._session_edit, stretch=1)
        sess_layout.addLayout(sid_row)

        ag_row = QHBoxLayout()
        ag_row.addWidget(BodyLabel("资源组 ID:"))
        self._asset_group_edit = LineEdit()
        self._asset_group_edit.setPlaceholderText("留空则自动检测")
        ag_row.addWidget(self._asset_group_edit, stretch=1)
        sess_layout.addLayout(ag_row)

        layout.addWidget(sess_card)

        # --- Generation settings card ---
        gen_card, gen_layout = self._make_card("生成参数")
        gen_layout.setSpacing(8)

        res_row = QHBoxLayout()
        res_row.addWidget(BodyLabel("分辨率:"))
        self._resolution_combo = ComboBox()
        self._resolution_combo.addItems(["480p", "720p", "1080p"])
        self._resolution_combo.setCurrentText("720p")
        res_row.addWidget(self._resolution_combo)
        res_row.addStretch()
        gen_layout.addLayout(res_row)

        audio_row = QHBoxLayout()
        audio_row.addWidget(BodyLabel("生成音频:"))
        self._audio_switch = SwitchButton()
        self._audio_switch.setOnText("开")
        self._audio_switch.setOffText("关")
        self._audio_switch.setChecked(True)
        audio_row.addWidget(self._audio_switch)
        audio_row.addStretch()
        gen_layout.addLayout(audio_row)

        poll_row = QHBoxLayout()
        poll_row.addWidget(BodyLabel("轮询间隔(秒):"))
        self._poll_spin = SpinBox()
        self._poll_spin.setRange(5, 120)
        self._poll_spin.setValue(15)
        poll_row.addWidget(self._poll_spin)
        poll_row.addStretch()
        gen_layout.addLayout(poll_row)

        layout.addWidget(gen_card)

        # --- Prompt defaults card ---
        prompt_card, prompt_layout = self._make_card("提示词默认值")
        prompt_layout.setSpacing(8)

        prefix_row = QHBoxLayout()
        prefix_row.addWidget(BodyLabel("前缀:"))
        self._prefix_edit = LineEdit()
        self._prefix_edit.setPlaceholderText("全局前缀，会加在所有提示词前面")
        prefix_row.addWidget(self._prefix_edit, stretch=1)
        prompt_layout.addLayout(prefix_row)

        suffix_row = QHBoxLayout()
        suffix_row.addWidget(BodyLabel("后缀:"))
        self._suffix_edit = LineEdit()
        self._suffix_edit.setPlaceholderText("全局后缀，会加在所有提示词后面")
        suffix_row.addWidget(self._suffix_edit, stretch=1)
        prompt_layout.addLayout(suffix_row)

        layout.addWidget(prompt_card)

        # --- Save button ---
        self._btn_save = PrimaryPushButton("保存设置")
        self._btn_save.clicked.connect(self._on_save)
        layout.addWidget(self._btn_save, alignment=Qt.AlignLeft)

        layout.addStretch()

        # Load saved settings
        self._load_settings()

    def _make_card(self, title: str) -> tuple[CardWidget, QVBoxLayout]:
        card = CardWidget()
        outer = QVBoxLayout(card)
        outer.setSpacing(8)
        title_label = StrongBodyLabel(title)
        outer.addWidget(title_label)
        # Inner content layout
        content = QVBoxLayout()
        outer.addLayout(content)
        return card, content

    # ------------------------------------------------------------------
    # Persistence via QSettings
    # ------------------------------------------------------------------

    def _load_settings(self):
        try:
            from PySide6.QtCore import QSettings
            # Read team_id from global settings first
            global_s = QSettings("RunwayMLApp", "settings")
            team_id = global_s.value(SETTINGS_KEY_TEAM_ID, DEFAULT_TEAM_ID)
            s = settings_scope(team_id)
            self._token_edit.setText(s.value(SETTINGS_KEY_TOKEN, ""))
            self._team_edit.setText(team_id)
            self._session_edit.setText(s.value(SETTINGS_KEY_SESSION_ID, ""))
            self._asset_group_edit.setText(s.value(SETTINGS_KEY_ASSET_GROUP_ID, ""))
            self._poll_spin.setValue(int(s.value(SETTINGS_KEY_POLL, 15)))
            self._resolution_combo.setCurrentText(s.value(SETTINGS_KEY_RESOLUTION, "720p"))
            self._audio_switch.setChecked(s.value(SETTINGS_KEY_AUDIO, "true") == "true")
            self._prefix_edit.setText(s.value(SETTINGS_KEY_PREFIX, ""))
            self._suffix_edit.setText(s.value(SETTINGS_KEY_SUFFIX, ""))
            output_dir = s.value(SETTINGS_KEY_OUTPUT_DIR, "")
            if output_dir:
                mw = self._main_window
                if mw and hasattr(mw, 'home_page'):
                    mw.home_page._output_dir_edit.setText(output_dir)
        except Exception:
            logger.exception("加载设置失败")

    def _on_save(self):
        try:
            from PySide6.QtCore import QSettings
            team_id = self._team_edit.text()

            # Always save team_id to global scope (needed for bootstrapping)
            global_s = QSettings("RunwayMLApp", "settings")
            global_s.setValue(SETTINGS_KEY_TEAM_ID, team_id)

            # Save everything else to team-specific scope
            s = settings_scope(team_id)
            s.setValue(SETTINGS_KEY_TOKEN, self._token_edit.text())
            s.setValue(SETTINGS_KEY_TEAM_ID, team_id)
            s.setValue(SETTINGS_KEY_SESSION_ID, self._session_edit.text())
            s.setValue(SETTINGS_KEY_ASSET_GROUP_ID, self._asset_group_edit.text())
            s.setValue(SETTINGS_KEY_POLL, self._poll_spin.value())
            s.setValue(SETTINGS_KEY_RESOLUTION, self._resolution_combo.currentText())
            s.setValue(SETTINGS_KEY_AUDIO, "true" if self._audio_switch.isChecked() else "false")
            s.setValue(SETTINGS_KEY_PREFIX, self._prefix_edit.text())
            s.setValue(SETTINGS_KEY_SUFFIX, self._suffix_edit.text())

            mw = self._main_window
            if mw and hasattr(mw, 'home_page'):
                s.setValue(SETTINGS_KEY_OUTPUT_DIR, mw.home_page.output_dir)

            if mw and hasattr(mw, '_apply_settings'):
                mw._apply_settings()

            InfoBar.success(
                "已保存", f"设置已保存成功 (团队 {team_id})",
                position=InfoBarPosition.TOP, parent=self,
            )
        except Exception:
            logger.exception("保存设置失败")

    # ------------------------------------------------------------------
    # Token helper
    # ------------------------------------------------------------------

    def _on_get_token(self):
        try:
            from ui.widgets.token_helper import TokenHelperDialog
            dlg = TokenHelperDialog(self)
            dlg.token_ready.connect(self._on_token_extracted)
            dlg.exec()
        except Exception:
            logger.exception("打开令牌获取对话框失败")

    def _on_token_extracted(self, token: str, team_id: str = ""):
        try:
            self._token_edit.setText(token)
            if team_id:
                self._team_edit.setText(team_id)
            self._on_save()
            team_msg = f"\n团队 ID: {team_id}" if team_id else ""
            InfoBar.success(
                "令牌已保存",
                f"JWT 令牌已自动填入并持久化保存 (长度: {len(token)} 字符){team_msg}",
                position=InfoBarPosition.TOP, parent=self,
            )
        except Exception:
            logger.exception("令牌提取保存失败")

    # ------------------------------------------------------------------
    # Token test
    # ------------------------------------------------------------------

    def _on_manage_assets(self):
        try:
            from ui.widgets.asset_manager_dialog import AssetManagerDialog
            mw = self._main_window
            if not mw or not hasattr(mw, 'client'):
                InfoBar.error("错误", "客户端未初始化", position=InfoBarPosition.TOP, parent=self)
                return

            dlg = AssetManagerDialog(mw.client, self)
            dlg.assets_saved.connect(self._on_assets_saved)
            dlg.exec()
        except Exception:
            logger.exception("打开素材管理失败")

    def _on_assets_saved(self):
        """Reload char_assets after user saves in AssetManagerDialog."""
        try:
            mw = self._main_window
            if mw and hasattr(mw, '_load_char_assets'):
                team_id = mw.client._team_id if hasattr(mw, 'client') else ""
                mw._load_char_assets(team_id)
            # Re-check all prompt items for missing refs
            if mw and hasattr(mw, 'home_page'):
                mw.home_page._update_items_missing_refs()
            InfoBar.success(
                "素材已更新",
                "角色素材库已重新加载",
                position=InfoBarPosition.TOP, parent=self,
            )
        except Exception:
            logger.exception("重新加载素材失败")

    def _on_test_token(self):
        try:
            async def _test():
                try:
                    mw = self._main_window
                    if not mw or not hasattr(mw, 'client'):
                        self._test_result.setText("错误：客户端未初始化")
                        return

                    token = self._token_edit.text()
                    team_id = self._team_edit.text()
                    mw.client.configure(token, team_id)
                    ok, msg = await mw.client.validate_token()
                    self._test_result.setText(msg)
                    if ok:
                        self._test_result.setStyleSheet("color: #4CAF50;")
                    else:
                        self._test_result.setStyleSheet("color: #F44336;")
                except Exception as e:
                    logger.exception("测试连接异常")
                    self._test_result.setText(f"测试异常: {e}")
                    self._test_result.setStyleSheet("color: #F44336;")

            import asyncio
            asyncio.ensure_future(_test())
        except Exception:
            logger.exception("测试连接失败")
