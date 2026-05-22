# -*- coding: utf-8 -*-
"""主窗口 — Fluent Design + 并发批量分析（最多 3 个同时）"""
import os
import subprocess
import sys
import traceback

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout, QVBoxLayout, QWidget, QSplitter,
    QApplication, QMainWindow, QFileDialog, QMessageBox,
)
from PySide6.QtGui import QIcon
from qfluentwidgets import InfoBar, InfoBarPosition

from .sidebar import Sidebar
from .content_area import ContentArea, LogWidget
from .viewer_dialog import ViewerDialog
from core.analyzer import find_script_path
from core.worker import AnalysisWorker, BatchAnalysisManager
from core.notifier import send_error_notification


class MainWindow(QMainWindow):
    """视频分镜脚本分析器 - 主窗口"""

    def __init__(self):
        try:
            super().__init__()
            self.setWindowTitle("乐乐视频分镜脚本提取    微信：rpalele")
            self.resize(1492, 1001)
            self.setMinimumSize(1020, 700)

            icon_path = os.path.join(sys._MEIPASS if getattr(sys, 'frozen', False) else os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "1.ico")
            if os.path.exists(icon_path):
                self.setWindowIcon(QIcon(icon_path))

            screen = QApplication.primaryScreen().geometry()
            self.move(
                (screen.width() - self.width()) // 2,
                (screen.height() - self.height()) // 2
            )

            self.current_worker = None
            self.current_batch_manager = None
            self._setup_ui()
            self._connect_signals()
        except Exception as e:
            tb = traceback.format_exc()
            QMessageBox.critical(None, "主窗口初始化失败", f"初始化主窗口时出错:\n\n{e}\n\n{tb[:500]}")
            raise

    def _setup_ui(self):
        try:
            central = QWidget()
            self.setCentralWidget(central)
            layout = QHBoxLayout(central)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(0)

            self.splitter = QSplitter(Qt.Horizontal)
            self.splitter.setHandleWidth(1)

            self.sidebar = Sidebar()
            self.splitter.addWidget(self.sidebar)

            right_panel = QWidget()
            right_layout = QVBoxLayout(right_panel)
            right_layout.setContentsMargins(0, 0, 0, 0)
            right_layout.setSpacing(0)

            self.content_area = ContentArea()
            right_layout.addWidget(self.content_area)

            self.log_widget = LogWidget()
            right_layout.addWidget(self.log_widget)

            self.splitter.addWidget(right_panel)
            self.splitter.setSizes([350, 1142])

            layout.addWidget(self.splitter)
        except Exception as e:
            tb = traceback.format_exc()
            QMessageBox.critical(self, "UI初始化失败", f"构建界面时出错:\n\n{e}\n\n{tb[:500]}")
            raise

    def _connect_signals(self):
        try:
            self.sidebar.folder_selected.connect(self._on_folder_selected)
            self.sidebar.files_selected.connect(self._on_files_selected)
            self.sidebar.analyze_all_requested.connect(self._on_analyze_all)
            self.sidebar.stop_requested.connect(self._on_stop)
            self.sidebar.config_changed.connect(lambda _: None)
            self.sidebar.export_files_requested.connect(self._export_files)
            self.sidebar.merge_export_requested.connect(self._merge_export)
            self.sidebar.error_occurred.connect(lambda msg: self.append_log(msg, "error"))

            self.content_area.preview_requested.connect(self._on_preview)
            self.content_area.script_requested.connect(self._on_open_script)
            self.content_area.analyze_requested.connect(self._on_analyze_single)
            self.content_area.stop_requested.connect(self._on_stop_single)
            self.content_area.delete_requested.connect(self._on_file_removed)
            self.content_area.retry_all_requested.connect(self._on_retry_all)
            self.content_area.error_occurred.connect(lambda msg: self.append_log(msg, "error"))
        except Exception as e:
            tb = traceback.format_exc()
            QMessageBox.critical(self, "信号连接失败", f"连接信号槽时出错:\n\n{e}\n\n{tb[:500]}")
            raise

    def _log_error(self, context, exc):
        try:
            tb = traceback.format_exc()
            msg = f"{context}: {exc}\n{tb[:800]}"
            self.log_widget.append(msg, "error")
            send_error_notification(msg)
        except Exception:
            # 日志记录本身失败时不应中断主流程
            print(f"[ERROR] 日志记录失败: {context}: {exc}", file=sys.stderr)

    def append_log(self, message, level="info"):
        try:
            self.log_widget.append(message, level)
            if level == "error":
                send_error_notification(message)
        except Exception as e:
            print(f"[ERROR] 追加日志失败: {e}", file=sys.stderr)

    def _on_folder_selected(self, folder):
        try:
            self.content_area.load_videos([folder])
        except Exception as e:
            self._log_error("选择文件夹异常", e)

    def _on_files_selected(self, files):
        try:
            self.content_area.load_videos(files, replace=True)
        except Exception as e:
            self._log_error("选择文件异常", e)

    def _on_file_removed(self, path):
        """ContentArea._remove_video 已处理全部清理，此处仅做日志记录"""
        try:
            self.append_log(f"已移除: {os.path.basename(path)}", "info")
        except Exception as e:
            self._log_error("移除文件异常", e)

    # ── Single analysis ──

    def _on_analyze_single(self, video_path):
        try:
            config = self.sidebar.get_config()
            if not config.get("api_key"):
                InfoBar.warning("缺少配置", "请先配置 API Key",
                               duration=3000, parent=self, position=InfoBarPosition.TOP)
                return

            self.sidebar.set_processing(True)
            self.content_area.update_card_status(video_path, "analyzing", "启动中...", 0)
            self.append_log(f"开始分析: {os.path.basename(video_path)}", "info")

            worker = AnalysisWorker(video_path, config)
            worker.progress.connect(
                lambda msg, pct, vp=video_path: self._on_single_progress(vp, msg, pct)
            )
            worker.finished.connect(
                lambda ok, msg, out, vp=video_path: self._on_single_done(vp, ok, msg, out)
            )
            worker.log_message.connect(lambda msg, lvl="info": self.append_log(msg, lvl))
            worker.start()
            self.current_worker = worker
        except Exception as e:
            self._log_error("启动单个分析异常", e)
            self.sidebar.set_processing(False)

    def _on_single_progress(self, video_path, msg, pct):
        try:
            self.content_area.update_card_status(video_path, "analyzing", msg, pct)
        except Exception as e:
            self._log_error("分析进度更新异常", e)

    def _on_single_done(self, video_path, success, msg, output_path):
        try:
            if success:
                self.content_area.update_card_status(video_path, "done", "已完成", 100)
                self.append_log(f"分析完成: {os.path.basename(video_path)}", "success")
            else:
                self.content_area.update_card_status(video_path, "failed", "分析失败", 0)
                self.append_log(f"分析失败: {os.path.basename(video_path)} — {msg}", "error")
                InfoBar.error("分析失败",
                             f"{os.path.basename(video_path)}: {msg[:80]}",
                             duration=5000, parent=self, position=InfoBarPosition.TOP)
        except Exception as e:
            self._log_error("分析完成处理异常", e)
        finally:
            self.sidebar.set_processing(False)
            self.current_worker = None

    # ── Batch analysis (concurrent, max 3 parallel) ──

    def _on_analyze_all(self):
        try:
            video_paths = self.content_area.get_selected_paths()
            video_paths = [vp for vp in video_paths if not find_script_path(vp)]

            if not video_paths:
                InfoBar.info("无待处理视频", "所有视频已分析完毕",
                            duration=2000, parent=self, position=InfoBarPosition.TOP)
                return

            config = self.sidebar.get_config()
            if not config.get("api_key"):
                InfoBar.warning("缺少配置", "请先配置 API Key",
                               duration=3000, parent=self, position=InfoBarPosition.TOP)
                return

            self.sidebar.set_processing(True)
            self.append_log(f"并发批量分析启动（最多 3 路），共 {len(video_paths)} 个视频", "info")

            self.current_batch_manager = BatchAnalysisManager(video_paths, config)
            self.current_batch_manager.file_started.connect(self._on_batch_file_started)
            self.current_batch_manager.file_progress.connect(self._on_batch_file_progress)
            self.current_batch_manager.file_finished.connect(self._on_batch_file_finished)
            self.current_batch_manager.batch_finished.connect(self._on_batch_done)
            self.current_batch_manager.log_message.connect(
                lambda msg, lvl="info": self.append_log(msg, lvl))
            self.current_batch_manager.start()

            InfoBar.info("并发分析已启动",
                         f"正在同时处理最多 3 个视频，共 {len(video_paths)} 个",
                         duration=3000, parent=self, position=InfoBarPosition.TOP)
        except Exception as e:
            self._log_error("启动批量分析异常", e)
            self.sidebar.set_processing(False)

    def _on_batch_file_started(self, idx, filename):
        try:
            if self.current_batch_manager and idx < len(self.current_batch_manager.video_paths):
                vp = self.current_batch_manager.video_paths[idx]
                self.content_area.update_card_status(vp, "analyzing", "启动中...", 0)
        except Exception as e:
            self._log_error(f"批量文件启动异常 idx={idx}", e)

    def _on_batch_file_progress(self, msg, pct, idx):
        try:
            if self.current_batch_manager and idx < len(self.current_batch_manager.video_paths):
                vp = self.current_batch_manager.video_paths[idx]
                status = "compressing" if "压缩" in msg else "analyzing"
                self.content_area.update_card_status(vp, status, msg, pct)
        except Exception as e:
            self._log_error(f"批量进度更新异常 idx={idx}", e)

    def _on_batch_file_finished(self, idx, success, msg, output_path):
        try:
            if self.current_batch_manager and idx < len(self.current_batch_manager.video_paths):
                vp = self.current_batch_manager.video_paths[idx]
                if success:
                    self.content_area.update_card_status(vp, "done", "已完成", 100)
                else:
                    self.content_area.update_card_status(vp, "failed", "分析失败", 0)
        except Exception as e:
            self._log_error(f"批量文件完成异常 idx={idx}", e)

    def _on_batch_done(self, success_count, fail_count):
        try:
            self.sidebar.set_processing(False)
            self.current_batch_manager = None
            if fail_count == 0:
                self.append_log(f"并发批量分析完成: 全部 {success_count} 个成功", "success")
                InfoBar.success("批量完成", f"全部 {success_count} 个视频分析成功！",
                               duration=5000, parent=self, position=InfoBarPosition.TOP)
            else:
                self.append_log(f"并发批量分析完成: {success_count} 成功, {fail_count} 失败", "error")
                InfoBar.warning("批量完成", f"成功 {success_count} 个，失败 {fail_count} 个",
                               duration=5000, parent=self, position=InfoBarPosition.TOP)
        except Exception as e:
            self._log_error("批量完成处理异常", e)

    def _on_retry_all(self, paths):
        try:
            if not paths:
                InfoBar.info("无需重试", "所有视频已分析完毕",
                            duration=2000, parent=self, position=InfoBarPosition.TOP)
                return
            config = self.sidebar.get_config()
            if not config.get("api_key"):
                InfoBar.warning("缺少配置", "请先配置 API Key",
                               duration=3000, parent=self, position=InfoBarPosition.TOP)
                return

            self.sidebar.set_processing(True)
            self.append_log(f"一键重试启动（最多 3 路），共 {len(paths)} 个视频", "info")

            self.current_batch_manager = BatchAnalysisManager(paths, config)
            self.current_batch_manager.file_started.connect(self._on_batch_file_started)
            self.current_batch_manager.file_progress.connect(self._on_batch_file_progress)
            self.current_batch_manager.file_finished.connect(self._on_batch_file_finished)
            self.current_batch_manager.batch_finished.connect(self._on_batch_done)
            self.current_batch_manager.log_message.connect(
                lambda msg, lvl="info": self.append_log(msg, lvl))
            self.current_batch_manager.start()

            InfoBar.info("重试已启动",
                         f"正在同时处理最多 3 个视频，共 {len(paths)} 个",
                         duration=3000, parent=self, position=InfoBarPosition.TOP)
        except Exception as e:
            self._log_error("一键重试异常", e)
            self.sidebar.set_processing(False)

    def _on_stop(self):
        try:
            if self.current_worker:
                self.current_worker.stop()
                self.current_worker.quit()
                self.current_worker.wait(3000)
                self.current_worker = None
            if self.current_batch_manager:
                for vp in self.current_batch_manager.video_paths:
                    self.content_area.update_card_status(vp, "idle", "就绪", 0)
                self.current_batch_manager.stop()
                self.current_batch_manager = None
            self.sidebar.set_processing(False)
            self.append_log("用户停止分析", "info")
        except Exception as e:
            self._log_error("停止分析异常", e)

    def _on_stop_single(self, video_path):
        try:
            if self.current_worker and self.current_worker.video_path == video_path:
                self.current_worker.stop()
                self.current_worker.quit()
                self.current_worker.wait(3000)
                self.current_worker = None
                self.sidebar.set_processing(False)
                self.content_area.update_card_status(video_path, "idle", "就绪", 0)
                self.append_log(f"用户停止: {os.path.basename(video_path)}", "info")
            if self.current_batch_manager:
                self.current_batch_manager.stop_video(video_path)
                self.content_area.update_card_status(video_path, "idle", "就绪", 0)
                self.append_log(f"用户停止: {os.path.basename(video_path)}", "info")
        except Exception as e:
            self._log_error(f"停止单个分析异常", e)

    def _collect_scripts(self):
        try:
            scripts = []
            for vpath in self.content_area.get_selected_paths():
                sp = find_script_path(vpath)
                if sp and os.path.exists(sp) and os.path.getsize(sp) > 100:
                    scripts.append((vpath, sp))
            return scripts
        except Exception as e:
            self._log_error("收集剧本异常", e)
            return []

    def _export_files(self):
        try:
            scripts = self._collect_scripts()
            if not scripts:
                InfoBar.warning("无剧本", "没有找到已分析的剧本",
                              duration=3000, parent=self, position=InfoBarPosition.TOP)
                return
            folder = QFileDialog.getExistingDirectory(self, "选择导出目录")
            if not folder:
                return
            count = 0
            for _, sp in scripts:
                try:
                    with open(sp, "r", encoding="utf-8") as src:
                        dest = os.path.join(folder, os.path.basename(sp))
                        with open(dest, "w", encoding="utf-8") as dst:
                            dst.write(src.read())
                    count += 1
                except Exception as e:
                    InfoBar.error("导出失败", f"{os.path.basename(sp)}: {e}",
                                duration=3000, parent=self, position=InfoBarPosition.TOP)
            InfoBar.success("导出完成", f"成功导出 {count} 个剧本",
                          duration=3000, parent=self, position=InfoBarPosition.TOP)
        except Exception as e:
            self._log_error("导出文件异常", e)

    def _merge_export(self):
        try:
            scripts = self._collect_scripts()
            if not scripts:
                InfoBar.warning("无剧本", "没有找到已分析的剧本",
                              duration=3000, parent=self, position=InfoBarPosition.TOP)
                return
            folder = QFileDialog.getExistingDirectory(self, "选择导出目录")
            if not folder:
                return
            import re
            sorted_scripts = sorted(scripts, key=lambda x: int(
                re.search(r'(\d+)', os.path.basename(x[0])).group(1)
                if re.search(r'(\d+)', os.path.basename(x[0])) else 0
            ))
            dest = os.path.join(folder, "合集_分镜脚本.txt")
            with open(dest, "w", encoding="utf-8") as out:
                out.write("=" * 60 + "\n")
                out.write(f"视频分镜脚本合集  ·  共 {len(sorted_scripts)} 集\n")
                out.write("=" * 60 + "\n\n")
                for i, (_, sp) in enumerate(sorted_scripts, 1):
                    out.write(f"\n{'─' * 60}\n 第 {i} 集\n{'─' * 60}\n\n")
                    with open(sp, "r", encoding="utf-8") as src:
                        out.write(src.read())
                    out.write("\n\n")
            InfoBar.success("合并导出完成", f"已保存到: {dest}",
                          duration=3000, parent=self, position=InfoBarPosition.TOP)
        except Exception as e:
            self._log_error("合并导出异常", e)

    def _on_preview(self, video_path):
        try:
            dialog = ViewerDialog(
                video_path=video_path,
                video_paths=self.content_area.get_selected_paths(),
                parent=self
            )
            dialog.error_occurred.connect(lambda msg: self.append_log(msg, "error"))
            dialog.show()
        except Exception as e:
            self._log_error("打开预览异常", e)

    def _on_open_script(self, script_path):
        try:
            if script_path and os.path.exists(script_path):
                if sys.platform == "win32":
                    subprocess.Popen(["explorer", "/select,", os.path.normpath(script_path)])
                else:
                    subprocess.Popen(["xdg-open", os.path.dirname(script_path)])
        except Exception as e:
            self._log_error("定位剧本文件异常", e)
