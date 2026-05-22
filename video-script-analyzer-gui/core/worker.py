# -*- coding: utf-8 -*-
"""QThread workers for async video analysis with concurrent batch support."""
import os
import sys
import traceback
from PySide6.QtCore import QThread, Signal, QObject

from .analyzer import analyze_video


class AnalysisWorker(QThread):
    """单视频分析工作线程"""
    progress = Signal(str, int)
    finished = Signal(bool, str, str)
    log_message = Signal(str, str)  # (message, level: info/success/error)

    def __init__(self, video_path, api_config, output_dir=None):
        super().__init__()
        self.video_path = video_path
        self.api_config = api_config
        self.output_dir = output_dir
        self._stop = False

    def stop(self):
        self._stop = True

    def run(self):
        try:
            if self._stop:
                self.finished.emit(False, "已取消", "")
                return

            def on_progress(msg, pct):
                if not self._stop:
                    self.progress.emit(msg, pct)

            def on_log(msg, level):
                self.log_message.emit(msg, level)

            success, msg, output_path = analyze_video(
                self.video_path, self.api_config, self.output_dir,
                progress_callback=on_progress,
                log_callback=on_log
            )
            self.finished.emit(success, msg, output_path or "")
        except Exception as e:
            tb = traceback.format_exc()
            err_msg = f"工作线程异常: {e}\n{tb[:800]}"
            print(f"[ERROR] {err_msg}", file=sys.stderr)
            self.log_message.emit(err_msg, "error")
            try:
                self.finished.emit(False, f"线程异常: {e}", "")
            except Exception:
                pass


class BatchAnalysisManager(QObject):
    """并发批量分析管理器 — 最多 3 个视频同时分析"""
    file_progress = Signal(str, int, int)    # msg, pct, idx
    file_started = Signal(int, str)          # idx, filename
    file_finished = Signal(int, bool, str, str)  # idx, success, msg, output_path
    batch_finished = Signal(int, int)        # success_count, fail_count
    log_message = Signal(str, str)           # message, level

    MAX_CONCURRENT = 3

    def __init__(self, video_paths, api_config, parent=None):
        super().__init__(parent)
        self.video_paths = video_paths
        self.api_config = api_config
        self._stop = False
        self._active_workers = {}  # idx -> worker
        self._next_idx = 0
        self._success_count = 0
        self._fail_count = 0
        self._total = len(video_paths)

    def start(self):
        try:
            for _ in range(min(self.MAX_CONCURRENT, self._total)):
                self._launch_next()
        except Exception as e:
            tb = traceback.format_exc()
            self.log_message.emit(f"批量管理器启动异常: {e}\n{tb[:800]}", "error")
            self.batch_finished.emit(0, self._total)

    def _launch_next(self):
        try:
            if self._stop:
                self._check_all_done()
                return
            if self._next_idx >= self._total:
                self._check_all_done()
                return

            idx = self._next_idx
            self._next_idx += 1
            vpath = self.video_paths[idx]
            filename = os.path.basename(vpath)

            self.file_started.emit(idx, filename)
            self.log_message.emit(f"[{idx+1}/{self._total}] 开始分析: {filename}", "info")

            worker = AnalysisWorker(vpath, self.api_config)

            # Capture idx in closures
            def make_progress(fidx):
                return lambda msg, pct: self.file_progress.emit(msg, pct, fidx)

            def make_finished(fidx):
                return lambda ok, msg, out: self._on_worker_done(fidx, ok, msg, out)

            worker.progress.connect(make_progress(idx))
            worker.log_message.connect(self.log_message.emit)
            worker.finished.connect(make_finished(idx))
            worker.start()

            self._active_workers[idx] = worker
        except Exception as e:
            tb = traceback.format_exc()
            self.log_message.emit(f"启动分析任务异常 idx={self._next_idx}: {e}\n{tb[:800]}", "error")
            self._fail_count += 1
            self._next_idx += 1
            self._launch_next()

    def _on_worker_done(self, idx, success, msg, output_path):
        try:
            if idx in self._active_workers:
                del self._active_workers[idx]

            if success:
                self._success_count += 1
                self.log_message.emit(f"[{idx+1}/{self._total}] 分析完成", "success")
            else:
                self._fail_count += 1
                self.log_message.emit(f"[{idx+1}/{self._total}] 分析失败: {msg[:60]}", "warning")

            self.file_finished.emit(idx, success, msg, output_path or "")

            # Launch next pending
            self._launch_next()
        except Exception as e:
            tb = traceback.format_exc()
            self.log_message.emit(f"工作线程完成处理异常 idx={idx}: {e}\n{tb[:800]}", "error")
            self._fail_count += 1
            self.file_finished.emit(idx, False, f"处理异常: {e}", "")
            self._launch_next()

    def _check_all_done(self):
        try:
            if not self._active_workers:
                self.batch_finished.emit(self._success_count, self._fail_count)
        except Exception as e:
            tb = traceback.format_exc()
            self.log_message.emit(f"批量完成检查异常: {e}\n{tb[:800]}", "error")

    def stop(self):
        try:
            self._stop = True
            for w in list(self._active_workers.values()):
                w.stop()
                w.quit()
                w.wait(3000)
            self._active_workers.clear()
        except Exception as e:
            self.log_message.emit(f"批量停止异常: {e}", "error")

    def stop_video(self, video_path):
        try:
            for idx, w in list(self._active_workers.items()):
                if w.video_path == video_path:
                    w.stop()
                    w.quit()
                    w.wait(3000)
                    del self._active_workers[idx]
                    self._fail_count += 1
                    self.file_finished.emit(idx, False, "已取消", "")
                    self._launch_next()
                    return
        except Exception as e:
            self.log_message.emit(f"停止单个视频异常: {e}", "error")
