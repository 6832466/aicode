import asyncio
import json
import logging
import uuid
from datetime import datetime
from pathlib import Path
from PySide6.QtCore import Qt, Signal, QAbstractListModel, QModelIndex, QSize
from PySide6.QtWidgets import (
    QFileDialog, QListView, QStyledItemDelegate, QStyle,
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QScrollArea
)
from PySide6.QtGui import QPixmap, QColor, QPainter, QFont
from qfluentwidgets import (
    ScrollArea, CardWidget, BodyLabel, StrongBodyLabel,
    PushButton, ComboBox, LineEdit, SpinBox,
    InfoBar, InfoBarPosition, TextEdit, ImageLabel, MessageBoxBase,
    SubtitleLabel,
)

from app.config import FREE_MODELS, image_cache_dir, data_dir, short_model_name
from app.models import ImageGeneration
from app.modelscope_client import get_client
from ui.widgets.log_widget import LogWidget

logger = logging.getLogger(__name__)


class ImageListModel(QAbstractListModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._data: list[ImageGeneration] = []

    def rowCount(self, parent=QModelIndex()):
        return len(self._data)

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid() or index.row() >= len(self._data):
            return None

        img = self._data[index.row()]

        if role == Qt.DisplayRole:
            return img.prompt[:30]

        if role == Qt.ToolTipRole:
            return img.prompt

        if role == Qt.DecorationRole:
            if img.local_path and Path(img.local_path).exists():
                pixmap = QPixmap(img.local_path)
                if not pixmap.isNull():
                    return pixmap.scaled(80, 80, Qt.AspectRatioMode.KeepAspectRatioByExpanding, Qt.TransformationMode.SmoothTransformation)

        return None

    def set_data(self, data: list[ImageGeneration]):
        self.beginResetModel()
        self._data = data
        self.endResetModel()

    def add_image(self, img: ImageGeneration):
        self.beginInsertRows(QModelIndex(), len(self._data), len(self._data))
        self._data.append(img)
        self.endInsertRows()

    def remove_image(self, row: int):
        if 0 <= row < len(self._data):
            self.beginRemoveRows(QModelIndex(), row, row)
            self._data.pop(row)
            self.endRemoveRows()

    def get_image(self, row: int) -> ImageGeneration | None:
        if 0 <= row < len(self._data):
            return self._data[row]
        return None

    def get_all(self) -> list[ImageGeneration]:
        return self._data.copy()


class ImageThumbDelegate(QStyledItemDelegate):
    """Custom delegate for thumbnail display with 80x80 size."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._size = QSize(80, 80)

    def paint(self, painter, option, index):
        img_data = index.data(Qt.DecorationRole)

        if img_data and isinstance(img_data, QPixmap) and not img_data.isNull():
            pixmap = img_data
        else:
            # Draw placeholder
            pixmap = QPixmap(80, 80)
            pixmap.fill(QColor("#E0E0E0"))
            painter = QPainter(pixmap)
            painter.setPen(QColor("#999999"))
            painter.setFont(QFont("Arial", 10))
            painter.drawText(pixmap.rect(), Qt.AlignCenter, "无图")
            painter.end()
            painter = QPainter(option.widget)

        # Draw background
        painter.save()
        if option.state & QStyle.State_Selected:
            painter.fillRect(option.rect, QColor("#E3F2FD"))
        else:
            painter.fillRect(option.rect, QColor("#FFFFFF"))

        # Draw image centered
        x = option.rect.x() + (option.rect.width() - 80) // 2
        y = option.rect.y() + 5
        painter.drawPixmap(x, y, 80, 80, pixmap)

        # Draw prompt preview below
        prompt = index.data(Qt.DisplayRole)
        if prompt:
            painter.setPen(QColor("#333333"))
            painter.setFont(QFont("Microsoft YaHei", 9))
            text_rect = option.rect.adjusted(5, 90, -5, 0)
            painter.drawText(text_rect, Qt.TextWordWrap, prompt[:20] + "...")

        painter.restore()

    def sizeHint(self, option, index):
        return QSize(100, 120)


class ImagePreviewDialog(MessageBoxBase):
    """Dialog for viewing full-size image with details."""

    def __init__(self, parent=None, img: ImageGeneration = None):
        self._img = img
        super().__init__(parent)
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self.widget)
        layout.setSpacing(12)

        if not self._img:
            layout.addWidget(BodyLabel("无图片信息"))
            return

        # Image display
        if self._img.local_path and Path(self._img.local_path).exists():
            pixmap = QPixmap(self._img.local_path)
            if not pixmap.isNull():
                # Scale to fit
                max_size = 600
                if pixmap.width() > max_size or pixmap.height() > max_size:
                    pixmap = pixmap.scaled(
                        max_size, max_size,
                        Qt.AspectRatioMode.KeepAspectRatio,
                        Qt.TransformationMode.SmoothTransformation
                    )

                img_label = ImageLabel()
                img_label.setPixmap(pixmap)
                layout.addWidget(img_label)

        # Image info
        info_layout = QGridLayout()
        info_layout.setSpacing(8)

        info_layout.addWidget(BodyLabel("模型:"), 0, 0)
        info_layout.addWidget(BodyLabel(self._img.model_id), 0, 1)

        info_layout.addWidget(BodyLabel("尺寸:"), 1, 0)
        info_layout.addWidget(BodyLabel(self._img.size), 1, 1)

        info_layout.addWidget(BodyLabel("种子:"), 2, 0)
        info_layout.addWidget(BodyLabel(str(self._img.seed)), 2, 1)

        info_layout.addWidget(BodyLabel("时间:"), 3, 0)
        info_layout.addWidget(BodyLabel(self._img.timestamp[:19] if self._img.timestamp else ""), 3, 1)

        layout.addLayout(info_layout)

        # Prompt
        layout.addWidget(BodyLabel("提示词:"))
        prompt_label = TextEdit()
        prompt_label.setPlainText(self._img.prompt)
        prompt_label.setReadOnly(True)
        prompt_label.setMaximumHeight(80)
        layout.addWidget(prompt_label)

        # Buttons
        btn_layout = QHBoxLayout()

        self._btn_copy_prompt = PushButton("复制提示词")
        self._btn_copy_prompt.clicked.connect(self._copy_prompt)
        btn_layout.addWidget(self._btn_copy_prompt)

        self._btn_open_folder = PushButton("打开文件夹")
        self._btn_open_folder.clicked.connect(self._open_folder)
        btn_layout.addWidget(self._btn_open_folder)

        btn_layout.addStretch()
        layout.addLayout(btn_layout)

    def _copy_prompt(self):
        from PySide6.QtWidgets import QApplication
        clipboard = QApplication.clipboard()
        clipboard.setText(self._img.prompt)
        InfoBar.success("已复制", "提示词已复制到剪贴板", parent=self)

    def _open_folder(self):
        import os
        import subprocess
        if self._img.local_path:
            folder = Path(self._img.local_path).parent
            subprocess.run(["explorer", str(folder)])


class ImagePage(ScrollArea):
    image_generated = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("imagePage")
        self._pending_prompts: list[str] = []
        self._generating = False
        self._init_ui()
        self._load_history()

    def _init_ui(self):
        container = QWidget()
        self.setWidget(container)
        self.setWidgetResizable(True)

        layout = QVBoxLayout(container)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(16)

        # Header
        header = QHBoxLayout()
        header.addWidget(StrongBodyLabel("文生图"))
        header.addStretch()
        layout.addLayout(header)

        # Settings card
        settings_card = CardWidget()
        settings_layout = QGridLayout(settings_card)
        settings_layout.setContentsMargins(16, 16, 16, 16)
        settings_layout.setVerticalSpacing(12)

        # Model selection
        settings_layout.addWidget(BodyLabel("模型:"), 0, 0)
        self._model_combo = ComboBox()
        for model_id in FREE_MODELS.get("image", []):
            name = short_model_name(model_id)
            self._model_combo.addItem(f"{name} ({model_id})", model_id)
        self._model_combo.setFixedWidth(250)
        settings_layout.addWidget(self._model_combo, 0, 1)

        # Size selection
        settings_layout.addWidget(BodyLabel("尺寸:"), 0, 2)
        self._size_combo = ComboBox()
        self._size_combo.addItems(["512x512", "768x768", "1024x1024", "1024x1792", "1792x1024"])
        self._size_combo.setFixedWidth(120)
        settings_layout.addWidget(self._size_combo, 0, 3)

        # Number of images
        settings_layout.addWidget(BodyLabel("数量:"), 0, 4)
        self._count_spin = SpinBox()
        self._count_spin.setRange(1, 4)
        self._count_spin.setValue(1)
        self._count_spin.setFixedWidth(60)
        settings_layout.addWidget(self._count_spin, 0, 5)

        # Seed
        settings_layout.addWidget(BodyLabel("种子:"), 1, 0)
        self._seed_spin = SpinBox()
        self._seed_spin.setRange(-1, 2147483647)
        self._seed_spin.setValue(-1)
        self._seed_spin.setFixedWidth(100)
        settings_layout.addWidget(self._seed_spin, 1, 1)
        settings_layout.addWidget(BodyLabel("(-1=随机)"), 1, 2)

        layout.addWidget(settings_card)

        # Prompt input area
        prompt_card = CardWidget()
        prompt_layout = QVBoxLayout(prompt_card)
        prompt_layout.setContentsMargins(16, 16, 16, 16)

        prompt_header = QHBoxLayout()
        prompt_header.addWidget(BodyLabel("提示词 (支持中英文):"))
        prompt_header.addStretch()

        self._btn_template = PushButton("模板")
        self._btn_template.setFixedWidth(60)
        prompt_header.addWidget(self._btn_template)

        self._btn_history = PushButton("历史")
        self._btn_history.setFixedWidth(60)
        prompt_header.addWidget(self._btn_history)

        prompt_layout.addLayout(prompt_header)

        self._prompt_edit = TextEdit()
        self._prompt_edit.setPlaceholderText("输入图像描述，如：一只可爱的橘猫在阳光下打盹\n支持多行输入，每行生成一张图")
        self._prompt_edit.setMaximumHeight(100)
        prompt_layout.addWidget(self._prompt_edit)

        # Buttons
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        self._btn_add_queue = PushButton("加入队列")
        self._btn_add_queue.setFixedWidth(90)
        self._btn_add_queue.clicked.connect(self._add_to_queue)
        btn_layout.addWidget(self._btn_add_queue)

        self._btn_generate = PushButton("生成")
        self._btn_generate.setFixedWidth(80)
        self._btn_generate.clicked.connect(self._generate_image)
        btn_layout.addWidget(self._btn_generate)

        prompt_layout.addLayout(btn_layout)
        layout.addWidget(prompt_card)

        # Queue display
        queue_card = CardWidget()
        queue_layout = QVBoxLayout(queue_card)
        queue_layout.setContentsMargins(8, 8, 8, 8)

        queue_header = QHBoxLayout()
        queue_header.addWidget(BodyLabel("待生成队列:"))
        self._queue_label = BodyLabel("0 个任务")
        queue_header.addWidget(self._queue_label)
        queue_header.addStretch()

        self._btn_clear_queue = PushButton("清空队列")
        self._btn_clear_queue.setFixedWidth(80)
        self._btn_clear_queue.clicked.connect(self._clear_queue)
        queue_header.addWidget(self._btn_clear_queue)

        queue_layout.addLayout(queue_header)
        layout.addWidget(queue_card)

        # Generated images grid
        images_card = CardWidget()
        images_layout = QVBoxLayout(images_card)
        images_layout.setContentsMargins(8, 8, 8, 8)

        images_header = QHBoxLayout()
        images_header.addWidget(StrongBodyLabel("生成记录:"))
        images_header.addStretch()

        self._btn_export = PushButton("导出")
        self._btn_export.setFixedWidth(60)
        self._btn_export.clicked.connect(self._export_images)
        images_header.addWidget(self._btn_export)

        self._btn_clear = PushButton("清空")
        self._btn_clear.setFixedWidth(60)
        self._btn_clear.clicked.connect(self._clear_images)
        images_header.addWidget(self._btn_clear)

        images_layout.addLayout(images_header)

        # Image grid with thumbnails
        self._images_list = QListView()
        self._images_list.setViewMode(QListView.IconMode)
        self._images_list.setGridSize(QSize(110, 130))
        self._images_list.setResizeMode(QListView.Adjust)
        self._images_list.setSpacing(10)
        self._images_list.setItemDelegate(ImageThumbDelegate(self))
        self._images_model = ImageListModel()
        self._images_list.setModel(self._images_model)
        self._images_list.doubleClicked.connect(self._show_image_preview)
        self._images_list.setMinimumHeight(300)
        self._images_list.setStyleSheet(
            "QListView { background-color: #FAFAFA; border: 1px solid #E0E0E0; }"
        )
        images_layout.addWidget(self._images_list)

        layout.addWidget(images_card)

        # Log
        self._log_widget = LogWidget()
        layout.addWidget(self._log_widget)

    def _add_to_queue(self):
        prompt = self._prompt_edit.toPlainText().strip()
        if not prompt:
            InfoBar.warning("请输入提示词", parent=self)
            return

        # Support multi-line prompts
        lines = [p.strip() for p in prompt.split("\n") if p.strip()]
        for p in lines:
            self._pending_prompts.append(p)

        self._update_queue_label()
        self._prompt_edit.clear()
        self._log_widget.info(f"已加入 {len(lines)} 个任务到队列")

    def _clear_queue(self):
        self._pending_prompts.clear()
        self._update_queue_label()
        self._log_widget.info("队列已清空")

    def _update_queue_label(self):
        self._queue_label.setText(f"{len(self._pending_prompts)} 个任务")

    def _generate_image(self):
        if self._generating:
            InfoBar.warning("正在生成中，请稍候", parent=self)
            return

        prompt = self._prompt_edit.toPlainText().strip()
        if not prompt and not self._pending_prompts:
            InfoBar.warning("请输入提示词", parent=self)
            return

        if prompt:
            lines = [p.strip() for p in prompt.split("\n") if p.strip()]
            for p in lines:
                self._pending_prompts.append(p)
            self._prompt_edit.clear()

        self._process_queue()

    def _process_queue(self):
        if not self._pending_prompts:
            return

        self._generating = True
        prompt = self._pending_prompts.pop(0)
        self._update_queue_label()

        count = self._count_spin.value()

        async def _generate():
            try:
                client = get_client()
                model_id = self._model_combo.currentData()
                if not model_id:
                    model_id = "FLUX.1/schnell"

                size = self._size_combo.currentText()
                seed = self._seed_spin.value() if self._seed_spin.value() >= 0 else None

                self._log_widget.info(f"正在生成: {prompt[:30]}...")

                for i in range(count):
                    resp = await client.generate_image(
                        model_id=model_id,
                        prompt=prompt,
                        size=size,
                        seed=seed,
                    )

                    # Download and save image
                    if resp.image_url:
                        local_path = await self._download_image(resp.image_url, prompt)
                        img = ImageGeneration(
                            prompt=prompt,
                            model_id=model_id,
                            image_url=resp.image_url,
                            local_path=str(local_path),
                            size=size,
                            seed=seed or -1,
                        )
                        self._images_model.add_image(img)
                        self._save_history()
                        self._log_widget.info(f"生成完成 ({i+1}/{count}): {local_path.name}")

                    if resp.quota:
                        self._log_widget.info(f"剩余额度: {resp.quota.daily_remaining}")

            except Exception as e:
                logger.exception("图像生成失败")
                self._log_widget.error(f"生成失败: {e}")
                InfoBar.error("生成失败", str(e), parent=self)

            finally:
                self._generating = False
                if self._pending_prompts:
                    self._process_queue()

        asyncio.ensure_future(_generate())

    async def _download_image(self, url: str, prompt: str) -> Path:
        """Download image and save to local cache."""
        import aiohttp

        cache_dir = image_cache_dir()
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{timestamp}_{prompt[:20].replace('/', '_')}.png"
        path = cache_dir / filename

        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                if resp.status == 200:
                    path.write_bytes(await resp.read())

        return path

    def _show_image_preview(self, index):
        """Show full-size image preview dialog."""
        img = self._images_model.get_image(index.row())
        if img:
            dlg = ImagePreviewDialog(self, img=img)
            dlg.exec()

    def _clear_images(self):
        self._images_model.set_data([])
        self._save_history()
        self._log_widget.info("生成记录已清空")

    def _export_images(self):
        """Export image history to JSON."""
        path, _ = QFileDialog.getSaveFileName(
            self, "导出生成记录", "images_history.json",
            "JSON Files (*.json)"
        )
        if path:
            images = self._images_model.get_all()
            data = [img.to_dict() for img in images]
            Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            InfoBar.success("导出成功", f"已导出到 {path}", parent=self)

    def _save_history(self):
        """Save generation history to file."""
        history_file = data_dir() / "image_history.json"
        try:
            images = self._images_model.get_all()
            data = [img.to_dict() for img in images]
            history_file.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception as e:
            logger.warning(f"Failed to save image history: {e}")

    def _load_history(self):
        """Load generation history from file."""
        history_file = data_dir() / "image_history.json"
        if history_file.exists():
            try:
                from app.models import ImageGeneration
                data = json.loads(history_file.read_text(encoding="utf-8"))
                images = [ImageGeneration.from_dict(d) for d in data]
                self._images_model.set_data(images)
                self._log_widget.info(f"已加载 {len(images)} 条生成记录")
            except Exception as e:
                logger.warning(f"Failed to load image history: {e}")
