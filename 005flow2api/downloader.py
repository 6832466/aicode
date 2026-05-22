"""Single image save and batch ZIP download utilities."""
import io
import zipfile
from pathlib import Path

from PySide6.QtCore import QObject, QThread, Signal
from PySide6.QtWidgets import QFileDialog

from utils import sanitize_filename


def save_single_image(parent, image_data: bytes, prompt: str) -> bool:
    """Open save dialog and write a single image to disk. Returns True on success."""
    default_name = f"{sanitize_filename(prompt, 40)}.jpg"
    path, _ = QFileDialog.getSaveFileName(
        parent,
        "保存图片",
        default_name,
        "JPEG 图片 (*.jpg *.jpeg);;PNG 图片 (*.png);;所有文件 (*.*)",
    )
    if not path:
        return False
    Path(path).write_bytes(image_data)
    return True


def build_zip_buffer(items: list[tuple[str, bytes]]) -> bytes:
    """Build a ZIP file buffer from (prompt, image_data) pairs. Runs in background thread."""
    buffer = io.BytesIO()
    used_names: dict[str, int] = {}
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for idx, (prompt, image_data) in enumerate(items):
            base = sanitize_filename(prompt, 30)
            if base in used_names:
                used_names[base] += 1
                name = f"{idx:03d}_{base}_{used_names[base]}.jpg"
            else:
                used_names[base] = 0
                name = f"{idx:03d}_{base}.jpg"
            zf.writestr(name, image_data)
    return buffer.getvalue()


class ZipperThread(QThread):
    """Background thread for writing a ZIP archive to disk."""
    finished = Signal(str)
    error = Signal(str)

    def __init__(self, save_path: str, items: list[tuple[str, bytes]], parent=None):
        super().__init__(parent)
        self.save_path = save_path
        self.items = items

    def run(self):
        try:
            data = build_zip_buffer(self.items)
            Path(self.save_path).write_bytes(data)
            self.finished.emit(self.save_path)
        except Exception as e:
            self.error.emit(str(e))
