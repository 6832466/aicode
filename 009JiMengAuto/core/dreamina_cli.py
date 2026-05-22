"""dreamina CLI 封装 - 替代浏览器自动化"""

import json
import logging
import os
import shutil
import subprocess
import time
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QObject, Signal, QThread

from data.models import Task, TaskStatus

logger = logging.getLogger(__name__)


def _find_binary() -> str:
    """在系统 PATH 和常见安装路径中查找 dreamina CLI"""
    # 先查 PATH
    which = shutil.which("dreamina")
    if which:
        return which
    which = shutil.which("dreamina.exe")
    if which:
        return which
    # 常见安装路径
    candidates = [
        Path.home() / "bin" / "dreamina.exe",
        Path.home() / "bin" / "dreamina",
        Path.home() / ".local" / "bin" / "dreamina",
        Path("/usr/local/bin/dreamina"),
    ]
    for p in candidates:
        if p.exists():
            return str(p)
    return "dreamina"


def _build_env() -> dict:
    """构建子进程环境变量（含代理）"""
    env = os.environ.copy()
    # 如果系统配置了代理但环境变量未设置，自动检测
    if "HTTPS_PROXY" not in env and "https_proxy" not in env:
        try:
            import winreg
            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Internet Settings"
            ) as key:
                enabled = winreg.QueryValueEx(key, "ProxyEnable")[0]
                if enabled:
                    server = winreg.QueryValueEx(key, "ProxyServer")[0]
                    env["HTTPS_PROXY"] = f"http://{server}"
                    env["HTTP_PROXY"] = f"http://{server}"
        except Exception:
            pass
    return env


class DreaminaCLI:
    """dreamina 命令行封装"""

    def __init__(self, binary: Optional[str] = None):
        self._binary = binary or _find_binary()
        self._env = _build_env()
        logger.info("dreamina CLI 路径: %s", self._binary)

    def _run(self, args: list[str], timeout: int = 30) -> subprocess.CompletedProcess:
        """运行 CLI 命令（自动注入代理）"""
        return subprocess.run(
            args, capture_output=True, text=True, timeout=timeout, env=self._env,
        )

    # ── 基础检测 ──

    def check_available(self) -> bool:
        """检查 dreamina CLI 是否可用"""
        try:
            result = self._run([self._binary, "version"])
            ok = result.returncode == 0
            if ok:
                logger.info("dreamina CLI 可用: %s", result.stdout.strip())
            else:
                logger.warning("dreamina CLI 不可用: %s", result.stderr.strip())
            return ok
        except (FileNotFoundError, subprocess.TimeoutExpired) as e:
            logger.warning("dreamina CLI 不可用: %s", e)
            return False

    def check_login(self) -> bool:
        """检查登录状态"""
        try:
            result = self._run([self._binary, "user_credit"], timeout=15)
            return result.returncode == 0
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False

    def login(self, headless: bool = True):
        """执行登录（终端显示二维码）"""
        cmd = [self._binary, "login"]
        if headless:
            cmd.append("--headless")
        logger.info("执行登录: %s", " ".join(cmd))
        subprocess.run(cmd, env=self._env)

    # ── 视频生成 ──

    def text2video(self, prompt: str, duration: int = 5,
                   ratio: str = "16:9", resolution: str = "720p",
                   poll: int = 0, timeout: int = 300) -> dict:
        """提交文生视频任务

        Returns:
            {"ok": True, "submit_id": "...", "video_url": "..."} 或
            {"ok": False, "error": "..."}
        """
        cmd = [
            self._binary, "text2video",
            f"--prompt={prompt}",
            f"--duration={duration}",
            f"--ratio={ratio}",
        ]
        if resolution:
            cmd.append(f"--video_resolution={resolution}")
        if poll > 0:
            cmd.append(f"--poll={poll}")

        logger.info("执行 text2video: %s ...", prompt[:50])
        try:
            result = self._run(cmd, timeout=timeout)
            return self._parse_result(result.stdout, result.stderr, result.returncode)
        except subprocess.TimeoutExpired:
            return {"ok": False, "error": "执行超时"}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def image2video(self, image_path: str, prompt: str, duration: int = 5,
                    poll: int = 0, timeout: int = 300) -> dict:
        """提交图生视频任务"""
        cmd = [
            self._binary, "image2video",
            f"--image={image_path}",
            f"--prompt={prompt}",
            f"--duration={duration}",
        ]
        if poll > 0:
            cmd.append(f"--poll={poll}")

        logger.info("执行 image2video: %s", image_path)
        try:
            result = self._run(cmd, timeout=timeout)
            return self._parse_result(result.stdout, result.stderr, result.returncode)
        except subprocess.TimeoutExpired:
            return {"ok": False, "error": "执行超时"}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    # ── 结果查询 ──

    def query_result(self, submit_id: str, download_dir: Optional[str] = None,
                     timeout: int = 120) -> dict:
        """查询生成结果"""
        cmd = [self._binary, "query_result", f"--submit_id={submit_id}"]
        if download_dir:
            cmd.append(f"--download_dir={download_dir}")

        try:
            result = self._run(cmd, timeout=timeout)
            return self._parse_result(result.stdout, result.stderr, result.returncode)
        except subprocess.TimeoutExpired:
            return {"ok": False, "error": "查询超时"}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def list_task(self, gen_status: Optional[str] = None) -> list[dict]:
        """列出历史任务"""
        cmd = [self._binary, "list_task"]
        if gen_status:
            cmd.append(f"--gen_status={gen_status}")
        try:
            result = self._run(cmd, timeout=30)
            if result.returncode == 0:
                return self._parse_list_output(result.stdout)
            return []
        except Exception:
            return []

    # ── 内部 ──

    def _parse_result(self, stdout: str, stderr: str, returncode: int) -> dict:
        """解析 CLI JSON 输出"""
        if returncode != 0:
            return {"ok": False, "error": stderr.strip() or f"退出码 {returncode}"}

        # 尝试解析 JSON 输出
        for line in stdout.splitlines():
            line = line.strip()
            try:
                data = json.loads(line)
                if isinstance(data, dict):
                    return self._normalize_result(data)
            except json.JSONDecodeError:
                continue

        # 无 JSON，尝试提取 submit_id
        submit_id = self._extract_submit_id(stdout)
        if submit_id:
            return {"ok": True, "submit_id": submit_id}
        return {"ok": True, "raw": stdout.strip()}

    def _normalize_result(self, data: dict) -> dict:
        """规范化返回结果"""
        result = {"ok": data.get("ok", False)}
        if data.get("submit_id"):
            result["submit_id"] = data["submit_id"]
        if data.get("video_url"):
            result["video_url"] = data["video_url"]
        if data.get("gen_status"):
            result["gen_status"] = data["gen_status"]
        if data.get("error"):
            result["error"] = data["error"]
        # 兼容不同字段名
        if not result.get("submit_id") and data.get("data", {}).get("submit_id"):
            result["submit_id"] = data["data"]["submit_id"]
        if not result.get("video_url") and data.get("data", {}).get("video_url"):
            result["video_url"] = data["data"]["video_url"]
        return result

    def _extract_submit_id(self, text: str) -> Optional[str]:
        """从文本中提取 submit_id"""
        import re
        m = re.search(r"submit_id[=:]\s*([a-f0-9]+)", text, re.IGNORECASE)
        if m:
            return m.group(1)
        return None

    def _parse_list_output(self, stdout: str) -> list[dict]:
        """解析 list_task 的输出"""
        tasks = []
        for line in stdout.splitlines():
            line = line.strip()
            try:
                data = json.loads(line)
                if isinstance(data, dict):
                    tasks.append(data)
            except json.JSONDecodeError:
                continue
        return tasks


class GenerationWorker(QObject):
    """生成工作线程（在 QThread 中运行）"""

    progress_updated = Signal(int, int)  # current, total
    task_status_changed = Signal(str, str)  # task_id, status
    generation_finished = Signal()
    log_message = Signal(str)

    def __init__(self, tasks: list[Task], cli: DreaminaCLI,
                 interval: int = 5, retry: int = 3, parent=None):
        super().__init__(parent)
        self._tasks = tasks
        self._cli = cli
        self._interval = interval
        self._retry = retry
        self._stopped = False

    def stop(self):
        """停止生成"""
        self._stopped = True

    def run(self):
        """执行生成循环"""
        total = len(self._tasks)
        self.progress_updated.emit(0, total)

        for i, task in enumerate(self._tasks):
            if self._stopped:
                break

            self.log_message.emit(f"[{i+1}/{total}] 开始生成: {task.scene}")
            self.task_status_changed.emit(task.id, TaskStatus.GENERATING.value)

            success = self._generate_single(task)

            if success:
                self.task_status_changed.emit(task.id, TaskStatus.COMPLETED.value)
                self.log_message.emit(f"[{i+1}/{total}] 完成: {task.scene}")
            else:
                self.task_status_changed.emit(task.id, TaskStatus.FAILED.value)
                self.log_message.emit(f"[{i+1}/{total}] 失败: {task.scene}")

            self.progress_updated.emit(i + 1, total)

            # 任务间隔（最后一个不等待）
            if i < total - 1 and not self._stopped:
                time.sleep(self._interval)

        self.generation_finished.emit()

    def _generate_single(self, task: Task) -> bool:
        """生成单个任务，含重试"""
        for attempt in range(1, self._retry + 1):
            if self._stopped:
                return False

            result = self._cli.text2video(
                prompt=task.prompt,
                duration=task.duration,
                ratio=task.ratio,
                resolution=task.resolution,
                poll=30,
            )

            if result.get("ok"):
                submit_id = result.get("submit_id")
                if submit_id:
                    task.submit_id = submit_id
                    # 如果有 video_url 直接获取
                    if result.get("video_url"):
                        task.video_url = result["video_url"]
                    else:
                        # 查询结果获取 video_url
                        query = self._cli.query_result(submit_id)
                        if query.get("ok") and query.get("video_url"):
                            task.video_url = query["video_url"]
                return True

            logger.warning("生成失败(尝试 %d/%d): %s", attempt, self._retry, result.get("error"))
            if attempt < self._retry:
                time.sleep(self._interval)

        return False
