import asyncio
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFileDialog, QMessageBox,
    QScrollArea, QHeaderView,
)
from qfluentwidgets import (
    PushButton, PrimaryPushButton, BodyLabel, StrongBodyLabel,
    InfoBar, InfoBarPosition, LineEdit,
    ProgressBar, CardWidget, FluentIcon,
)

from app.models import PromptItem, TaskStatus
from app.excel_parser import ExcelParser
from ui.widgets.prompt_table import PromptTableModel, PromptTableView
from ui.widgets.status_delegate import StatusDelegate
from ui.widgets.prefix_suffix_widget import PrefixSuffixWidget
from ui.widgets.log_widget import LogWidget, setup_app_logging
from ui.widgets.edit_dialog import EditDialog


class HomePage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("homePage")
        self._main_window = parent
        self._items: list[PromptItem] = []
        self._char_map: dict[str, str] = {}
        self._last_char_path: str = ""
        self._last_prompt_path: str = ""
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 12, 20, 12)
        layout.setSpacing(12)

        # --- Import row ---
        import_row = QHBoxLayout()
        self._char_label = BodyLabel("角色对照：未加载")
        self._btn_import_char = PushButton("导入 人物对照表")
        self._btn_import_char.clicked.connect(self._on_import_char)
        self._btn_import_prompt = PushButton("导入 提示词")
        self._btn_import_prompt.clicked.connect(self._on_import_prompts)
        import_row.addWidget(self._char_label)
        import_row.addStretch()
        import_row.addWidget(self._btn_import_char)
        import_row.addWidget(self._btn_import_prompt)
        layout.addLayout(import_row)

        # --- Prefix / Suffix ---
        self._prefix_suffix = PrefixSuffixWidget()
        layout.addWidget(self._prefix_suffix)

        # --- Output dir row ---
        out_row = QHBoxLayout()
        out_row.addWidget(BodyLabel("输出目录:"))
        self._output_dir_edit = LineEdit()
        self._output_dir_edit.setPlaceholderText("选择视频下载保存目录…")
        self._output_dir_edit.setReadOnly(True)
        self._btn_output = PushButton("浏览")
        self._btn_output.setIcon(FluentIcon.FOLDER)
        self._btn_output.clicked.connect(self._on_select_output_dir)
        out_row.addWidget(self._output_dir_edit, stretch=1)
        out_row.addWidget(self._btn_output)
        layout.addLayout(out_row)

        # --- Controls row ---
        ctrl_row = QHBoxLayout()
        self._btn_generate = PrimaryPushButton("开始生成")
        self._btn_generate.setEnabled(False)
        self._btn_generate.clicked.connect(self._on_generate)
        self._btn_next = PushButton("下一个")
        self._btn_next.clicked.connect(self._on_submit_next)
        self._btn_download_all = PushButton("批量下载")
        self._btn_download_all.clicked.connect(self._on_download_all)
        self._btn_pause = PushButton("暂停")
        self._btn_pause.clicked.connect(self._on_pause)
        self._btn_pause.setEnabled(False)
        self._btn_resume = PushButton("继续")
        self._btn_resume.clicked.connect(self._on_resume)
        self._btn_resume.setEnabled(False)
        self._btn_stop = PushButton("停止")
        self._btn_stop.clicked.connect(self._on_stop)
        self._btn_stop.setEnabled(False)

        ctrl_row.addWidget(self._btn_generate)
        ctrl_row.addWidget(self._btn_next)
        ctrl_row.addWidget(self._btn_download_all)
        ctrl_row.addWidget(self._btn_pause)
        ctrl_row.addWidget(self._btn_resume)
        ctrl_row.addWidget(self._btn_stop)
        ctrl_row.addStretch()
        layout.addLayout(ctrl_row)

        # --- Progress ---
        self._status_label = BodyLabel("就绪")
        self._progress_bar = ProgressBar()
        self._progress_bar.setVisible(False)
        self._progress_bar.setFixedHeight(6)
        layout.addWidget(self._status_label)
        layout.addWidget(self._progress_bar)

        # --- Table (inside scrollable card) ---
        table_card = CardWidget()
        card_layout = QVBoxLayout(table_card)
        card_layout.setContentsMargins(8, 8, 8, 8)
        card_title = StrongBodyLabel("提示词列表")
        card_layout.addWidget(card_title)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        self._table = PromptTableView()
        self._model = PromptTableModel()
        self._table.setModel(self._model)
        self._table.setItemDelegateForColumn(1, StatusDelegate())
        self._table.verticalHeader().setVisible(False)
        self._table.setShowGrid(False)
        self._table.setAlternatingRowColors(True)
        self._table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Fixed)
        self._table.setColumnWidth(0, 40)
        self._table.setColumnWidth(1, 70)
        self._table.setColumnWidth(3, 100)
        self._table.setColumnWidth(4, 50)
        self._table.setColumnWidth(5, 50)
        self._table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self._table.setMinimumHeight(200)

        scroll.setWidget(self._table)
        card_layout.addWidget(scroll)

        layout.addWidget(table_card, stretch=3)

        # Table interaction signals
        self._table.edit_requested.connect(self._on_edit_item)
        self._table.submit_requested.connect(self._on_submit_single)
        self._table.retry_download_requested.connect(self._on_retry_download)
        self._table.clear_list_requested.connect(self._on_clear_list)
        self._table.reload_requested.connect(self._on_reload)
        self._table.delete_item_requested.connect(self._on_delete_item)

        # --- Log widget ---
        self._log_widget = LogWidget()
        self._log_widget.setMinimumHeight(120)
        layout.addWidget(self._log_widget, stretch=2)

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def prefix_text(self) -> str:
        return self._prefix_suffix.prefix

    @property
    def suffix_text(self) -> str:
        return self._prefix_suffix.suffix

    @property
    def output_dir(self) -> str:
        return self._output_dir_edit.text()

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------

    def _on_import_char(self):
        try:
            path, _ = QFileDialog.getOpenFileName(
                self, "选择 人物对照表", "", "Excel Files (*.xlsx)"
            )
            if not path:
                return
            try:
                self._char_map = ExcelParser.parse_character_mapping(path)
                self._last_char_path = path
                names = "、".join(self._char_map.keys())
                self._char_label.setText(f"角色：{names}")

                # Check which ref_names don't have matching assets
                mw = self._main_window
                char_assets = mw._char_assets if mw and hasattr(mw, '_char_assets') else {}
                if char_assets:
                    missing_refs = []
                    for cn_name, ref_name in self._char_map.items():
                        if ref_name not in char_assets:
                            missing_refs.append(f"{cn_name}→{ref_name}")
                    if missing_refs:
                        InfoBar.warning(
                            "素材库缺少角色",
                            f"以下角色对照在素材库中未找到，请先在「设置→角色素材管理」中加载: {', '.join(missing_refs)}",
                            duration=10000,
                            position=InfoBarPosition.TOP, parent=self,
                        )
                    else:
                        InfoBar.success(
                            "加载成功",
                            f"已加载 {len(self._char_map)} 个角色对照，全部匹配素材库",
                            position=InfoBarPosition.TOP, parent=self,
                        )
                else:
                    InfoBar.warning(
                        "素材库为空",
                        "请先在「设置→角色素材管理」中从网站加载角色引用素材",
                        duration=8000,
                        position=InfoBarPosition.TOP, parent=self,
                    )

                # Also mark existing prompt items with missing refs
                self._update_items_missing_refs()
            except Exception as e:
                logger.exception("_on_import_char 失败")
                InfoBar.error("加载失败", str(e), position=InfoBarPosition.TOP, parent=self)
        except Exception as e:
            logger.exception("_on_import_char 未处理异常")

    def _on_import_prompts(self):
        try:
            if not self._char_map:
                reply = QMessageBox.question(
                    self, "未加载角色对照",
                    "请先导入「人物对照表」？\n（继续将不做角色名替换）",
                    QMessageBox.Yes | QMessageBox.No,
                )
                if reply == QMessageBox.Yes:
                    return

            path, _ = QFileDialog.getOpenFileName(
                self, "选择 提示词", "", "Excel Files (*.xlsx)"
            )
            if not path:
                return

            try:
                self._last_prompt_path = path
                self._items = ExcelParser.parse_prompts(
                    path, self._char_map or {},
                    prefix=self.prefix_text,
                    suffix=self.suffix_text,
                )
                self._model.set_items(self._items)
                self._status_label.setText(f"已加载 {len(self._items)} 条提示词")

                # Mark each item's missing refs for status column
                self._update_items_missing_refs()

                # Check for missing character assets (bulk warning)
                mw = self._main_window
                if mw and hasattr(mw, '_char_assets'):
                    missing = self._find_missing_assets(self._items, mw._char_assets)
                    if missing:
                        names = "、".join(missing)
                        InfoBar.warning(
                            "缺少角色素材",
                            f"以下角色在素材库中未找到: {names}。请先在「设置 → 角色素材管理」中加载对应角色素材",
                            duration=8000,
                            position=InfoBarPosition.TOP, parent=self,
                        )

                InfoBar.success(
                    "加载成功", f"已解析 {len(self._items)} 条提示词",
                    position=InfoBarPosition.TOP, parent=self,
                )
            except Exception as e:
                logger.exception("_on_import_prompts 解析失败")
                InfoBar.error("解析失败", str(e), position=InfoBarPosition.TOP, parent=self)
        except Exception as e:
            logger.exception("_on_import_prompts 未处理异常")

    def _on_select_output_dir(self):
        try:
            path = QFileDialog.getExistingDirectory(self, "选择输出目录")
            if path:
                self._output_dir_edit.setText(path)
        except Exception as e:
            logger.exception("_on_select_output_dir 异常")

    def _on_generate(self):
        try:
            if not self._items:
                InfoBar.warning("无提示词", "请先导入提示词",
                               position=InfoBarPosition.TOP, parent=self)
                return
            if not self.output_dir:
                InfoBar.warning("未选择输出目录", "请先选择视频保存目录",
                               position=InfoBarPosition.TOP, parent=self)
                return

            mw = self._main_window
            if not mw or not hasattr(mw, 'start_batch'):
                InfoBar.error("内部错误", "主窗口未连接",
                             position=InfoBarPosition.TOP, parent=self)
                return

            for item in self._items:
                item.prefix = self.prefix_text
                item.suffix = self.suffix_text

            mw.start_batch(self._items)
            self._btn_generate.setEnabled(False)
            self._btn_pause.setEnabled(True)
            self._btn_resume.setEnabled(False)
            self._btn_stop.setEnabled(True)
            self._progress_bar.setVisible(True)
        except Exception as e:
            logger.exception("_on_generate 异常")

    def _on_pause(self):
        try:
            mw = self._main_window
            if mw and hasattr(mw, 'pause_batch'):
                mw.pause_batch()
            self._btn_pause.setEnabled(False)
            self._btn_resume.setEnabled(True)
        except Exception as e:
            logger.exception("_on_pause 异常")

    def _on_resume(self):
        try:
            mw = self._main_window
            if mw and hasattr(mw, 'resume_batch'):
                mw.resume_batch()
            self._btn_resume.setEnabled(False)
            self._btn_pause.setEnabled(True)
        except Exception as e:
            logger.exception("_on_resume 异常")

    def _on_submit_next(self):
        try:
            mw = self._main_window
            if not mw or not hasattr(mw, 'submit_next'):
                InfoBar.error("内部错误", "主窗口未连接",
                             position=InfoBarPosition.TOP, parent=self)
                return
            if not self.output_dir:
                InfoBar.warning("未选择输出目录", "请先选择视频保存目录",
                               position=InfoBarPosition.TOP, parent=self)
                return
            mw.submit_next()
        except Exception as e:
            logger.exception("_on_submit_next 异常")

    def _on_download_all(self):
        try:
            mw = self._main_window
            if not mw or not hasattr(mw, 'download_all'):
                InfoBar.error("内部错误", "主窗口未连接",
                             position=InfoBarPosition.TOP, parent=self)
                return
            if not self.output_dir:
                InfoBar.warning("未选择输出目录", "请先选择视频保存目录",
                               position=InfoBarPosition.TOP, parent=self)
                return
            mw.download_all()
        except Exception as e:
            logger.exception("_on_download_all 异常")

    def _on_stop(self):
        try:
            mw = self._main_window
            if mw and hasattr(mw, 'stop_batch'):
                mw.stop_batch()
            self._reset_buttons()
        except Exception as e:
            logger.exception("_on_stop 异常")

    def _reset_buttons(self):
        try:
            self._btn_pause.setEnabled(False)
            self._btn_resume.setEnabled(False)
            self._btn_stop.setEnabled(False)
        except Exception as e:
            logger.exception("_reset_buttons 异常")

    # ------------------------------------------------------------------
    # Edit & single submit
    # ------------------------------------------------------------------

    def _on_edit_item(self, row: int):
        try:
            item = self._model.item_at(row)
            if not item:
                return
            mw = self._main_window
            available = list(mw._char_assets.keys()) if mw and hasattr(mw, '_char_assets') else []
            dlg = EditDialog(item, self._char_map or {}, available, self)
            if dlg.exec():
                self._model.update_item(row)
        except Exception as e:
            logger.exception("_on_edit_item 异常")

    def _on_submit_single(self, row: int):
        try:
            item = self._model.item_at(row)
            if not item:
                return
            if not self.output_dir:
                InfoBar.warning("未选择输出目录", "请先选择视频保存目录",
                               position=InfoBarPosition.TOP, parent=self)
                return

            mw = self._main_window
            if not mw or not hasattr(mw, 'submit_single'):
                InfoBar.error("内部错误", "主窗口未连接",
                             position=InfoBarPosition.TOP, parent=self)
                return

            item.prefix = self.prefix_text
            item.suffix = self.suffix_text
            mw.submit_single(item, row)
            # Update button state for single submission
            self._btn_generate.setEnabled(False)
            self._btn_pause.setEnabled(False)
            self._btn_resume.setEnabled(False)
            self._btn_stop.setEnabled(True)
            self._progress_bar.setVisible(True)
        except Exception as e:
            logger.exception("_on_submit_single 异常")

    def _update_items_missing_refs(self):
        """Update missing_refs on every item based on current char_assets."""
        mw = self._main_window
        char_assets = mw._char_assets if mw and hasattr(mw, '_char_assets') else {}
        for item in self._items:
            item.missing_refs = [ref for ref in item.references if ref not in char_assets]
        self._model.set_items(self._items)

    def _find_missing_assets(self, items: list[PromptItem], char_assets: dict) -> set[str]:
        """Return set of reference names used in prompts but missing from char_assets."""
        used_refs = set()
        for item in items:
            for ref in item.references:
                used_refs.add(ref)
        # Also collect actual Chinese names from char_map for display
        missing = set()
        for ref in used_refs:
            if ref not in char_assets:
                # Show the Chinese name if we can find it in char_map
                cn_name = next((cn for cn, rn in self._char_map.items() if rn == ref), ref)
                missing.add(cn_name)
        return missing

    def _on_retry_download(self, row: int):
        try:
            item = self._model.item_at(row)
            if not item:
                return
            mw = self._main_window
            if not mw or not hasattr(mw, 'retry_download'):
                return
            mw.retry_download(item)
        except Exception as e:
            logger.exception("_on_retry_download 异常")

    def _on_delete_item(self, row: int):
        try:
            if 0 <= row < len(self._items):
                self._items.pop(row)
                self._model.set_items(self._items)
                self._status_label.setText(f"已删除第 {row + 1} 条，共 {len(self._items)} 条")
                InfoBar.info("已删除", f"第 {row + 1} 条已移除",
                           position=InfoBarPosition.TOP, parent=self)
        except Exception as e:
            logger.exception("_on_delete_item 异常")

    def _on_clear_list(self):
        try:
            self._items.clear()
            self._model.set_items([])
            self._last_prompt_path = ""
            self._status_label.setText("就绪")
            InfoBar.info("已清空", "提示词列表已清空", position=InfoBarPosition.TOP, parent=self)
        except Exception as e:
            logger.exception("_on_clear_list 异常")

    def _on_reload(self):
        try:
            if not self._last_char_path and not self._last_prompt_path:
                InfoBar.warning("未导入", "请先导入人物对照表和提示词表",
                               position=InfoBarPosition.TOP, parent=self)
                return
            if self._last_char_path:
                try:
                    self._char_map = ExcelParser.parse_character_mapping(self._last_char_path)
                except Exception as e:
                    logger.exception("重新加载角色失败")
                    InfoBar.error("重新加载角色失败", str(e), position=InfoBarPosition.TOP, parent=self)
                    return
            if not self._last_prompt_path:
                InfoBar.warning("未导入提示词", "请先导入提示词表",
                               position=InfoBarPosition.TOP, parent=self)
                return
            try:
                self._items = ExcelParser.parse_prompts(
                    self._last_prompt_path, self._char_map or {},
                    prefix=self.prefix_text,
                    suffix=self.suffix_text,
                )
                self._model.set_items(self._items)
                self._status_label.setText(f"已重新加载 {len(self._items)} 条提示词")

                # Mark each item's missing refs for status column
                self._update_items_missing_refs()

                mw = self._main_window
                if mw and hasattr(mw, '_char_assets'):
                    missing = self._find_missing_assets(self._items, mw._char_assets)
                    if missing:
                        names = "、".join(missing)
                        InfoBar.warning(
                            "缺少角色素材",
                            f"以下角色在素材库中未找到: {names}。请先在「设置 → 角色素材管理」中加载对应角色素材",
                            duration=8000,
                            position=InfoBarPosition.TOP, parent=self,
                        )

                InfoBar.success("重新加载成功", f"已加载 {len(self._items)} 条",
                               position=InfoBarPosition.TOP, parent=self)
            except Exception as e:
                logger.exception("重新加载提示词失败")
                InfoBar.error("重新加载失败", str(e), position=InfoBarPosition.TOP, parent=self)
        except Exception as e:
            logger.exception("_on_reload 未处理异常")

    # ------------------------------------------------------------------
    # Called by MainWindow signals
    # ------------------------------------------------------------------

    def _maybe_write_status_back(self):
        """Write status back to Excel if path is known."""
        if not self._last_prompt_path:
            return
        try:
            ExcelParser.write_status_back(self._last_prompt_path, self._items)
        except Exception as e:
            logger.warning("Failed to write status back to Excel: %s", e)

    def on_item_status_changed(self, index: int, status_str: str, error: str):
        try:
            self._model.update_item(index)
        except Exception as e:
            logger.exception("on_item_status_changed 异常")

    def on_progress_updated(self, done: int, total: int, active: int):
        try:
            self._status_label.setText(
                f"进度：{done}/{total} 已完成 | {active} 正在运行"
            )
            if total > 0:
                self._progress_bar.setValue(int(done / total * 100))
            else:
                self._progress_bar.setValue(0)
        except Exception as e:
            logger.exception("on_progress_updated 异常")

    def on_all_completed(self, success: int, failed: int):
        try:
            self._reset_buttons()
            self._progress_bar.setVisible(False)
            self._status_label.setText(
                f"完成 — {success} 成功, {failed} 失败"
            )
            self._maybe_write_status_back()
            InfoBar.success(
                "批量处理完成",
                f"{success} 个视频已下载, {failed} 个失败",
                duration=5000,
                position=InfoBarPosition.TOP,
                parent=self,
            )
        except Exception as e:
            logger.exception("on_all_completed 异常")

    def on_log_message(self, msg: str):
        try:
            self._status_label.setText(msg)
            self._log_widget.info(msg)
        except Exception as e:
            logger.exception("on_log_message 异常")

    def clear_items(self):
        try:
            self._items.clear()
            self._model.set_items([])
            self._status_label.setText("就绪")
        except Exception as e:
            logger.exception("clear_items 异常")
