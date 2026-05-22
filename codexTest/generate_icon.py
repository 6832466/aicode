from pathlib import Path
import sys

from PySide6.QtCore import QBuffer, QByteArray, QIODevice
from PySide6.QtWidgets import QApplication
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))

from gold_monitor import THEMES, make_app_icon


def pixmap_png_bytes(size: int, accent: str) -> bytes:
    pixmap = make_app_icon(accent).pixmap(size, size)
    data = QByteArray()
    buffer = QBuffer(data)
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    if not pixmap.save(buffer, "PNG"):
        raise RuntimeError(f"Failed to render {size}px icon")
    buffer.close()
    return bytes(data)


def write_multi_size_ico(target: Path, accent: str) -> None:
    images = []
    for size in (16, 24, 32, 48, 64, 128, 256):
        png = pixmap_png_bytes(size, accent)
        images.append(Image.open(__import__("io").BytesIO(png)).convert("RGBA"))
    images[-1].save(
        target,
        format="ICO",
        sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)],
        append_images=images[:-1],
    )


def main() -> int:
    app = QApplication.instance() or QApplication([])
    target = Path(__file__).resolve().parent / "gold_monitor.ico"
    write_multi_size_ico(target, THEMES["aurum_noir"]["accent"])
    app.quit()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
