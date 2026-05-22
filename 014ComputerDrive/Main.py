"""NVIDIA 显卡驱动 / CUDA / cuDNN / PyTorch 推荐工具 — 入口。"""
import sys
from pathlib import Path

# 保证从项目目录或打包后可导入 config / services / ui
_ROOT = Path(__file__).resolve().parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from ui.main_window import run_app

if __name__ == "__main__":
    run_app()
