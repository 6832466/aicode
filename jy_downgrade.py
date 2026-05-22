"""
剪映草稿版本降级工具 — PySide6 GUI 主程序
"""
import sys
import os
import webbrowser
from pathlib import Path

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QListWidget, QListWidgetItem, QComboBox,
    QCheckBox, QTextEdit, QGroupBox, QSplitter, QMessageBox,
    QFileDialog, QHeaderView, QTableWidget, QTableWidgetItem,
    QAbstractItemView, QDialog, QDialogButtonBox,
)
from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QFont, QColor, QPalette

from jy_version_map import MAJOR_VERSIONS, MINOR_VERSIONS
from jy_draft_parser import DraftParser, DraftInfo
from jy_backup import create_backup, restore_backup, list_backups, delete_backup, open_backup_folder
from jy_downgrade_engine import DowngradeEngine


class BackupManagerDialog(QDialog):
    """备份管理对话框"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("备份管理")
        self.resize(600, 400)
        self.setup_ui()
        self.refresh()

    def setup_ui(self):
        layout = QVBoxLayout(self)

        # 操作栏
        btn_layout = QHBoxLayout()
        btn_refresh = QPushButton("刷新")
        btn_refresh.clicked.connect(self.refresh)
        btn_delete = QPushButton("删除选中")
        btn_delete.clicked.connect(self.delete_selected)
        btn_open_folder = QPushButton("打开备份文件夹")
        btn_open_folder.clicked.connect(lambda: webbrowser.open(open_backup_folder()))
        btn_layout.addWidget(btn_refresh)
        btn_layout.addWidget(btn_delete)
        btn_layout.addStretch()
        btn_layout.addWidget(btn_open_folder)
        layout.addLayout(btn_layout)

        # 备份列表
        self.table = QTableWidget()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["文件名", "草稿名", "大小", "时间"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setColumnHidden(0, False)
        layout.addWidget(self.table)

        # 关闭按钮
        btn_close = QPushButton("关闭")
        btn_close.clicked.connect(self.accept)
        layout.addWidget(btn_close)

    def refresh(self):
        backups = list_backups()
        self.table.setRowCount(len(backups))
        for i, b in enumerate(backups):
            self.table.setItem(i, 0, QTableWidgetItem(b["filename"]))
            self.table.setItem(i, 1, QTableWidgetItem(b["draft_name"]))
            size_mb = f"{b['size'] / 1024:.1f} KB" if b['size'] < 1024*1024 else f"{b['size'] / 1024 / 1024:.1f} MB"
            self.table.setItem(i, 2, QTableWidgetItem(size_mb))
            self.table.setItem(i, 3, QTableWidgetItem(b["time_str"]))
            # 存储完整路径
            self.table.item(i, 0).setData(Qt.UserRole, b["path"])

    def delete_selected(self):
        rows = set(item.row() for item in self.table.selectedItems())
        if not rows:
            QMessageBox.information(self, "提示", "请先选择要删除的备份")
            return
        reply = QMessageBox.question(self, "确认", f"确定删除 {len(rows)} 个备份？")
        if reply == QMessageBox.Yes:
            for r in sorted(rows, reverse=True):
                path = self.table.item(r, 0).data(Qt.UserRole)
                delete_backup(path)
                self.table.removeRow(r)


class ChangePreviewDialog(QDialog):
    """变更预览对话框"""
    def __init__(self, result, parent=None):
        super().__init__(parent)
        self.setWindowTitle("降级变更预览")
        self.resize(500, 400)
        self.setup_ui(result)

    def setup_ui(self, result):
        layout = QVBoxLayout(self)

        text = QTextEdit()
        text.setReadOnly(True)
        text.setFont(QFont("Microsoft YaHei", 10))

        lines = []
        lines.append(f"版本号字段将被修改: {result.version_changes} 处")
        lines.append("")

        if result.tracks_removed:
            lines.append(f"【将被移除的 Track】({len(result.tracks_removed)} 条):")
            for t in result.tracks_removed:
                lines.append(f"  - {t}")
            lines.append("")

        if result.effects_removed:
            lines.append(f"【将被移除的效果/滤镜】({len(result.effects_removed)} 条):")
            for e in result.effects_removed:
                lines.append(f"  - {e}")
            lines.append("")

        if result.keys_removed:
            lines.append(f"【将被移除的数据字段】({len(result.keys_removed)} 条):")
            for k in result.keys_removed:
                lines.append(f"  - {k}")
            lines.append("")

        if result.warnings:
            lines.append(f"【警告】:")
            for w in result.warnings:
                lines.append(f"  - {w}")
            lines.append("")

        if result.errors:
            lines.append(f"【错误】:")
            for e in result.errors:
                lines.append(f"  - {e}")

        if not result.tracks_removed and not result.effects_removed and not result.keys_removed:
            lines.append("未检测到需要移除的内容。")
            lines.append("降级将仅修改版本号字段。")

        text.setPlainText("\n".join(lines))
        layout.addWidget(text)

        btn = QPushButton("关闭")
        btn.clicked.connect(self.accept)
        layout.addWidget(btn)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("剪映草稿版本降级工具 V1.0")
        self.resize(1100, 700)

        self.drafts: list[DraftInfo] = []
        self.current_draft: DraftInfo | None = None
        self.engine = DowngradeEngine()

        self.setup_ui()
        self.refresh_draft_list()

    def setup_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        splitter = QSplitter(Qt.Horizontal)
        main_layout = QHBoxLayout(central)
        main_layout.addWidget(splitter)
        main_layout.setContentsMargins(6, 6, 6, 6)

        # ===== 左侧：草稿列表 =====
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)

        # 工具栏
        toolbar = QHBoxLayout()
        self.lbl_draft_path = QLabel("草稿目录: 未找到")
        self.lbl_draft_path.setStyleSheet("color: gray; font-size: 11px;")
        self.lbl_draft_path.setWordWrap(True)

        btn_scan = QPushButton("扫描草稿")
        btn_scan.clicked.connect(self.refresh_draft_list)
        btn_browse = QPushButton("浏览...")
        btn_browse.clicked.connect(self.browse_draft_folder)

        toolbar.addWidget(btn_scan)
        toolbar.addWidget(btn_browse)
        left_layout.addLayout(toolbar)
        left_layout.addWidget(self.lbl_draft_path)

        # 草稿列表
        self.draft_list = QListWidget()
        self.draft_list.currentItemChanged.connect(self.on_draft_selected)
        left_layout.addWidget(self.draft_list)

        # 统计
        self.lbl_stats = QLabel("")
        self.lbl_stats.setStyleSheet("color: gray; font-size: 11px;")
        left_layout.addWidget(self.lbl_stats)

        splitter.addWidget(left_panel)

        # ===== 右侧：详情与操作 =====
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)

        # 草稿信息
        info_group = QGroupBox("草稿信息")
        info_layout = QVBoxLayout(info_group)
        self.lbl_draft_name = QLabel("名称: -")
        self.lbl_draft_version = QLabel("版本: -")
        self.lbl_draft_major = QLabel("主版本: -")
        self.lbl_draft_folder = QLabel("路径: -")
        self.lbl_draft_folder.setWordWrap(True)
        self.lbl_draft_folder.setStyleSheet("color: gray; font-size: 11px;")

        info_layout.addWidget(self.lbl_draft_name)
        info_layout.addWidget(self.lbl_draft_version)
        info_layout.addWidget(self.lbl_draft_major)
        info_layout.addWidget(self.lbl_draft_folder)
        right_layout.addWidget(info_group)

        # 降级设置
        setting_group = QGroupBox("降级设置")
        setting_layout = QVBoxLayout(setting_group)

        # 目标版本
        ver_layout = QHBoxLayout()
        ver_layout.addWidget(QLabel("目标版本:"))
        self.cmb_target_major = QComboBox()
        self.cmb_target_major.addItems(MAJOR_VERSIONS)
        self.cmb_target_major.setCurrentText("5.x")
        ver_layout.addWidget(self.cmb_target_major)
        ver_layout.addStretch()
        setting_layout.addLayout(ver_layout)

        # 目标次版本（可选）
        minor_layout = QHBoxLayout()
        minor_layout.addWidget(QLabel("目标次版本号:"))
        self.cmb_target_minor = QComboBox()
        self.cmb_target_minor.setEditable(True)
        self.cmb_target_minor.addItems(MINOR_VERSIONS)
        self.cmb_target_minor.setCurrentText("")
        self.cmb_target_minor.setToolTip("留空则自动使用目标主版本的默认值")
        minor_layout.addWidget(self.cmb_target_minor)
        setting_layout.addLayout(minor_layout)

        # 降级模式
        mode_layout = QHBoxLayout()
        mode_layout.addWidget(QLabel("降级模式:"))
        self.chk_mode_version_only = QCheckBox("仅改版本号")
        self.chk_mode_strip = QCheckBox("移除不兼容特性")
        self.chk_mode_strip.setChecked(True)
        self.chk_mode_full = QCheckBox("完整结构转换")
        self.chk_mode_full.setChecked(True)

        # 互斥逻辑：三个档位
        self.chk_mode_version_only.toggled.connect(self._on_mode_changed)
        mode_layout.addWidget(self.chk_mode_version_only)
        mode_layout.addWidget(self.chk_mode_strip)
        mode_layout.addWidget(self.chk_mode_full)
        setting_layout.addLayout(mode_layout)

        right_layout.addWidget(setting_group)

        # 操作按钮
        btn_group = QGroupBox("操作")
        btn_group_layout = QVBoxLayout(btn_group)

        btn_preview = QPushButton("预览变更")
        btn_preview.clicked.connect(self.preview_changes)
        btn_group_layout.addWidget(btn_preview)

        btn_save_and_downgrade = QPushButton("备份并降级")
        btn_save_and_downgrade.setStyleSheet(
            "background-color: #0b57d0; color: white; font-weight: bold; padding: 10px; font-size: 13px;"
        )
        btn_save_and_downgrade.clicked.connect(self.backup_and_downgrade)
        btn_group_layout.addWidget(btn_save_and_downgrade)

        btn_downgrade_only = QPushButton("仅降级（不备份）")
        btn_downgrade_only.setStyleSheet("color: #d32f2f;")
        btn_downgrade_only.clicked.connect(self.downgrade_only)
        btn_group_layout.addWidget(btn_downgrade_only)

        btn_restore = QPushButton("从备份恢复")
        btn_restore.clicked.connect(self.restore_from_backup)
        btn_group_layout.addWidget(btn_restore)

        btn_manage_backups = QPushButton("备份管理")
        btn_manage_backups.clicked.connect(self.open_backup_manager)
        btn_group_layout.addWidget(btn_manage_backups)

        right_layout.addWidget(btn_group)
        right_layout.addStretch()

        splitter.addWidget(right_panel)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 1)

    def _on_mode_changed(self):
        """确保三个模式互斥"""
        sender = self.sender()
        if sender is self.chk_mode_version_only:
            if self.chk_mode_version_only.isChecked():
                self.chk_mode_strip.setChecked(False)
                self.chk_mode_full.setChecked(False)
        elif sender is self.chk_mode_strip:
            if self.chk_mode_strip.isChecked():
                self.chk_mode_version_only.setChecked(False)
                self.chk_mode_full.setChecked(False)
        elif sender is self.chk_mode_full:
            if self.chk_mode_full.isChecked():
                self.chk_mode_version_only.setChecked(False)
                self.chk_mode_strip.setChecked(False)
        # 保证至少一个选中
        if not any([self.chk_mode_version_only.isChecked(),
                    self.chk_mode_strip.isChecked(),
                    self.chk_mode_full.isChecked()]):
            self.chk_mode_full.setChecked(True)

    def _get_mode(self) -> str:
        if self.chk_mode_version_only.isChecked():
            return "version_only"
        if self.chk_mode_strip.isChecked():
            return "strip"
        return "full"

    def refresh_draft_list(self):
        """刷新草稿列表"""
        self.drafts = DraftParser.scan_drafts()

        # 更新路径显示
        default_path = DraftParser.get_default_draft_path()
        if default_path:
            self.lbl_draft_path.setText(f"草稿目录: {default_path}")
        else:
            self.lbl_draft_path.setText("草稿目录: 未找到，请点击\"浏览...\"手动选择")

        # 更新列表
        self.draft_list.clear()
        for d in self.drafts:
            text = f"{d.display_name}"
            if d.version and d.version != "unknown":
                text += f"  [v{d.version}]"
            item = QListWidgetItem(text)
            item.setData(Qt.UserRole, d)
            if d.major_version != "unknown":
                item.setToolTip(f"版本: {d.version} | 路径: {d.folder_path}")
            self.draft_list.addItem(item)

        self.lbl_stats.setText(f"共 {len(self.drafts)} 个草稿")
        self.current_draft = None
        self._clear_draft_info()

    def browse_draft_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "选择剪映草稿目录")
        if folder:
            self.drafts = DraftParser.scan_drafts(folder)
            self.lbl_draft_path.setText(f"草稿目录: {folder}")
            self.draft_list.clear()
            for d in self.drafts:
                text = f"{d.display_name}"
                if d.version and d.version != "unknown":
                    text += f"  [v{d.version}]"
                item = QListWidgetItem(text)
                item.setData(Qt.UserRole, d)
                self.draft_list.addItem(item)
            self.lbl_stats.setText(f"共 {len(self.drafts)} 个草稿")

    def on_draft_selected(self, current, previous):
        if current is None:
            self.current_draft = None
            self._clear_draft_info()
            return
        draft = current.data(Qt.UserRole)
        self.current_draft = draft

        self.lbl_draft_name.setText(f"名称: {draft.display_name}")
        self.lbl_draft_version.setText(f"版本: {draft.version}")
        self.lbl_draft_major.setText(f"主版本: {draft.major_version}")
        self.lbl_draft_folder.setText(f"路径: {draft.folder_path}")

        # 自动设置目标版本为低一级
        if draft.major_version != "unknown" and draft.major_version in MAJOR_VERSIONS:
            idx = MAJOR_VERSIONS.index(draft.major_version)
            if idx > 0:
                self.cmb_target_major.setCurrentText(MAJOR_VERSIONS[idx - 1])

    def _clear_draft_info(self):
        self.lbl_draft_name.setText("名称: -")
        self.lbl_draft_version.setText("版本: -")
        self.lbl_draft_major.setText("主版本: -")
        self.lbl_draft_folder.setText("路径: -")

    def preview_changes(self):
        if self.current_draft is None:
            QMessageBox.warning(self, "提示", "请先选择一个草稿")
            return

        target_major = self.cmb_target_major.currentText()
        result = self.engine.preview_downgrade(self.current_draft, target_major, self._get_mode())

        if result.errors:
            QMessageBox.warning(self, "错误", "\n".join(result.errors))
            return

        dialog = ChangePreviewDialog(result, self)
        dialog.exec()

    def backup_and_downgrade(self):
        if self.current_draft is None:
            QMessageBox.warning(self, "提示", "请先选择一个草稿")
            return

        draft = self.current_draft
        target_major = self.cmb_target_major.currentText()
        target_minor = self.cmb_target_minor.currentText().strip() or None

        # 验证版本
        if draft.major_version == "unknown":
            QMessageBox.warning(self, "错误", "无法检测草稿源版本")
            return

        # 确认
        reply = QMessageBox.question(
            self, "确认操作",
            f"即将对草稿 \"{draft.display_name}\" 执行降级:\n\n"
            f"源版本: {draft.version} ({draft.major_version})\n"
            f"目标版本: {target_major}\n"
            f"模式: {self._get_mode()}\n\n"
            f"将会先创建备份，再执行降级。\n确认继续？"
        )
        if reply != QMessageBox.Yes:
            return

        # 1. 备份
        self.statusBar().showMessage("正在创建备份...")
        backup_path = create_backup(str(draft.folder_path))
        if backup_path is None:
            QMessageBox.critical(self, "错误", "备份创建失败，操作已取消")
            self.statusBar().clearMessage()
            return

        # 2. 降级
        self.statusBar().showMessage("正在执行降级...")
        result = self.engine.execute_downgrade(draft, target_major, target_minor, self._get_mode())

        if result.success:
            msg = f"降级完成!\n\n"
            msg += f"版本号修改: {result.version_changes} 处\n"
            msg += f"移除 track: {len(result.tracks_removed)} 条\n"
            msg += f"移除效果: {len(result.effects_removed)} 条\n"
            msg += f"移除字段: {len(result.keys_removed)} 条\n"
            if result.warnings:
                msg += f"\n警告: {len(result.warnings)} 条"
            msg += f"\n\n备份文件: {os.path.basename(backup_path)}"
            QMessageBox.information(self, "操作成功", msg)
        else:
            msg = "降级失败!\n\n"
            if result.errors:
                msg += "\n".join(result.errors)
            msg += f"\n\n备份文件仍保留: {os.path.basename(backup_path)}"
            QMessageBox.critical(self, "操作失败", msg)

        self.statusBar().clearMessage()
        self.refresh_draft_list()

    def downgrade_only(self):
        if self.current_draft is None:
            QMessageBox.warning(self, "提示", "请先选择一个草稿")
            return

        draft = self.current_draft
        target_major = self.cmb_target_major.currentText()
        target_minor = self.cmb_target_minor.currentText().strip() or None

        if draft.major_version == "unknown":
            QMessageBox.warning(self, "错误", "无法检测草稿源版本")
            return

        reply = QMessageBox.warning(
            self, "危险操作",
            f"即将不备份直接降级草稿 \"{draft.display_name}\" !\n\n"
            f"降级后可能无法恢复。强烈建议先备份!\n\n确认继续？",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        if reply != QMessageBox.Yes:
            return

        self.statusBar().showMessage("正在执行降级（无备份）...")
        result = self.engine.execute_downgrade(draft, target_major, target_minor, self._get_mode())

        if result.success:
            QMessageBox.information(self, "完成", f"降级完成! 版本号修改 {result.version_changes} 处")
        else:
            QMessageBox.critical(self, "失败", "\n".join(result.errors) if result.errors else "未知错误")

        self.statusBar().clearMessage()
        self.refresh_draft_list()

    def restore_from_backup(self):
        if self.current_draft is None:
            QMessageBox.warning(self, "提示", "请先选择一个草稿")
            return

        backups = list_backups(self.current_draft.folder_name)
        if not backups:
            # 也尝试全局搜索
            backups = list_backups()

        if not backups:
            QMessageBox.information(self, "提示", "没有找到任何备份文件")
            return

        # 简易选择对话框
        items = [f"{b['filename']} ({b['time_str']})" for b in backups[:20]]
        # 用 py 标准对话框不够友好，直接恢复最新的
        latest = backups[0]
        reply = QMessageBox.question(
            self, "恢复备份",
            f"找到 {len(backups)} 个备份。\n\n"
            f"最新备份: {latest['filename']}\n"
            f"时间: {latest['time_str']}\n\n"
            f"将用此备份覆盖当前草稿，确认？"
        )
        if reply != QMessageBox.Yes:
            return

        if restore_backup(latest["path"], str(self.current_draft.folder_path)):
            QMessageBox.information(self, "完成", "备份已恢复")
            self.refresh_draft_list()
        else:
            QMessageBox.critical(self, "错误", "恢复失败")

    def open_backup_manager(self):
        dialog = BackupManagerDialog(self)
        dialog.exec()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setFont(QFont("Microsoft YaHei", 9))
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
