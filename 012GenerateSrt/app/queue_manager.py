"""
任务队列管理器 — 状态机驱动批量处理
"""

import asyncio
import logging
import os
import sys
import time
from pathlib import Path
from typing import Optional, Callable

from PySide6.QtCore import QObject, Signal

from app.config import (
    STATE_PENDING, STATE_EXTRACTING, STATE_VAD, STATE_ASR,
    STATE_ALIGNING, STATE_WRITING, STATE_DONE, STATE_FAILED, STATE_STOPPED,
    MODE_ASR, MODE_ALIGNMENT, MAX_LINE_CHARS,
)
from app.models import TaskItem

# 真实处理引擎
from process_video import (
    extract_audio, run_vad_and_asr, run_force_alignment, generate_srt, generate_txt,
    MODEL_SENSEVOICE,
)

logger = logging.getLogger(__name__)

# 调试日志 — 写入文件确保不丢失
_debug_log = Path(__file__).parent.parent / "debug.log"
def _dbg(msg: str):
    ts = time.strftime("%H:%M:%S")
    line = f"[{ts}] {msg}"
    try:
        with open(_debug_log, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass
    print(line, flush=True)


class QueueManager(QObject):
    """任务队列管理器 — 顺序处理，异步驱动"""

    task_updated = Signal(TaskItem)       # 任务状态变更
    all_completed = Signal()              # 全部完成
    log_message = Signal(str)            # 日志消息

    def __init__(self, parent=None):
        super().__init__(parent)
        self._tasks: list[TaskItem] = []
        self._running = False
        self._paused = False
        self._stopped = False
        self._current_task: Optional[TaskItem] = None
        self._fail_count = 0
        self._max_fail = 10

    # ── 队列操作 ──

    def add_task(self, task: TaskItem):
        self._tasks.append(task)
        self._log(f"队列新增: {task.file_name}")

    def remove_task(self, task_id: str):
        self._tasks = [t for t in self._tasks if t.id != task_id]

    def get_all_tasks(self) -> list:
        return list(self._tasks)

    # ── 控制 ──

    def start(self):
        if self._running:
            _dbg("QueueManager.start:already running, skip")
            return
        self._running = True
        self._paused = False
        self._stopped = False
        self._fail_count = 0
        _dbg("QueueManager.start:creating future...")
        future = asyncio.ensure_future(self._process_loop())
        print(f"[DEBUG] QueueManager.start: future created, _tasks={len(self._tasks)}, pending={len([t for t in self._tasks if t.state == STATE_PENDING])}")

    def pause(self):
        self._paused = True
        self._log("队列已暂停")

    def resume(self):
        self._paused = False
        self._log("队列已继续")
        if self._running and not self._stopped:
            asyncio.ensure_future(self._process_loop())

    def stop(self):
        self._stopped = True
        self._paused = False
        self._log("队列已停止")
        # 将 pending 的任务标记为 stopped
        for t in self._tasks:
            if t.state in (STATE_PENDING,):
                t.state = STATE_STOPPED
                self.task_updated.emit(t)

    def is_running(self) -> bool:
        return self._running

    # ── 处理循环 ──

    async def _process_loop(self):
        _dbg("QueueManager._process_loop: entered")
        while self._running and not self._stopped:
            if self._paused:
                await asyncio.sleep(0.5)
                continue

            # 取下一个待处理任务
            pending = [t for t in self._tasks if t.state == STATE_PENDING]
            if not pending:
                self._log("所有任务处理完毕")
                self._running = False
                self.all_completed.emit()
                return

            task = pending[0]
            self._current_task = task
            self._fail_count = 0

            try:
                await self._process_one(task)
            except Exception as e:
                logger.exception(f"任务处理异常: {task.file_name}")
                task.state = STATE_FAILED
                task.error = str(e)
                self.task_updated.emit(task)
                self._fail_count += 1
                if self._fail_count >= self._max_fail:
                    self._log(f"连续失败 {self._fail_count} 次，停止队列")
                    self._stopped = True
                    self._running = False
                    self.all_completed.emit()
                    return

        self._running = False

    async def _process_one(self, task: TaskItem):
        """处理单个任务 — 支持 ASR 转写和强制对齐两种模式"""
        self._log(f"开始处理: {task.file_name} ({task.mode_label})")
        loop = asyncio.get_running_loop()
        audio_path = None

        try:
            # ── 阶段1: 提取音频 ──
            task.state = STATE_EXTRACTING
            task.progress = 0.05
            task.progress_text = "提取音频中..."
            self.task_updated.emit(task)

            audio_path = await loop.run_in_executor(
                None, extract_audio, task.file_path,
            )

            video_dir = str(Path(task.file_path).parent)
            video_stem = Path(task.file_path).stem
            srt_path = os.path.join(video_dir, video_stem + ".srt")
            txt_path = os.path.join(video_dir, video_stem + ".txt")

            if task.mode == MODE_ALIGNMENT:
                # ── 强制对齐模式 ──
                if not task.script_text or not task.script_text.strip():
                    raise ValueError("强制对齐模式需要提供文稿内容，请在右侧详情面板中输入")

                task.state = STATE_ALIGNING
                task.progress = 0.18
                task.progress_text = "CTC 强制对齐..."
                self.task_updated.emit(task)

                def align_progress_cb(stage: str, current: int, total: int):
                    if stage == "loading":
                        task.progress_text = "加载对齐模型..."
                    elif stage == "aligning":
                        task.progress_text = "强制对齐中..."
                        task.progress = 0.50
                    elif stage == "done":
                        task.progress = 0.80
                        task.segments_count = current
                        task.progress_text = f"对齐完成, {current} 段"
                    self.task_updated.emit(task)

                segments = await loop.run_in_executor(
                    None,
                    lambda: run_force_alignment(
                        audio_path,
                        task.script_text,
                        device="cpu",
                        progress_callback=align_progress_cb,
                        max_line_chars=MAX_LINE_CHARS,
                    ),
                )
            else:
                # ── ASR 转写模式 ──
                task.state = STATE_VAD
                task.progress = 0.12
                task.progress_text = "语音活动检测..."
                self.task_updated.emit(task)

                task.state = STATE_ASR
                task.progress = 0.18
                task.progress_text = "SenseVoice 语音识别..."
                self.task_updated.emit(task)

                def asr_progress_cb(stage: str, current: int, total: int):
                    if stage == "vad":
                        task.segments_count = total
                        task.progress = 0.18
                        task.progress_text = f"检测到 {total} 个语音段"
                    else:
                        task.current_segment = current
                        task.progress = 0.18 + (0.72 * current / total) if total > 0 else 0.90
                        task.progress_text = f"识别中... 第 {current}/{total} 段"
                    self.task_updated.emit(task)

                segments = await loop.run_in_executor(
                    None,
                    lambda: run_vad_and_asr(
                        audio_path, device="cpu",
                        progress_callback=asr_progress_cb,
                        asr_model_name=MODEL_SENSEVOICE,
                    ),
                )

            # 检查停止/暂停
            if self._stopped:
                task.state = STATE_STOPPED
                self.task_updated.emit(task)
                return

            # ── 阶段4: 生成字幕 ──
            task.state = STATE_WRITING
            task.progress = 0.93
            task.progress_text = "生成字幕文件..."
            self.task_updated.emit(task)

            await loop.run_in_executor(
                None, generate_srt, segments, srt_path, MAX_LINE_CHARS,
            )
            await loop.run_in_executor(
                None, generate_txt, segments, txt_path,
            )

            task.srt_path = srt_path

            # ── 完成 ──
            task.state = STATE_DONE
            task.progress = 1.0
            task.progress_text = "完成"
            self.task_updated.emit(task)
            self._log(f"完成: {task.file_name} → {task.srt_path}")

        except Exception as e:
            logger.exception(f"处理失败: {task.file_name}")
            raise

        finally:
            # 清理临时音频文件
            if audio_path and os.path.exists(audio_path):
                try:
                    os.remove(audio_path)
                except OSError:
                    pass
            # 清理可能残留的段文件
            seg_pattern = Path(task.file_path).name + ".extracted.wav.seg*.wav"
            for f in Path(task.file_path).parent.glob(seg_pattern):
                try:
                    f.unlink()
                except OSError:
                    pass

    # ── 日志 ──

    def _log(self, msg: str):
        self.log_message.emit(msg)
        logger.info(msg)