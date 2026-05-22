import logging

from PySide6.QtCore import Qt, QRect
from PySide6.QtGui import QPainter, QColor
from PySide6.QtWidgets import QStyledItemDelegate, QStyle

from app.models import TaskStatus

logger = logging.getLogger(__name__)


class StatusDelegate(QStyledItemDelegate):
    """Plain-text status delegate — no colored dots, shows progress % for running tasks."""

    STATUS_COLORS = {
        "待提交": QColor(150, 150, 150),
        "缺少素材": QColor(255, 87, 34),  # deep orange
        "提交中…": QColor(33, 150, 243),
        "排队中": QColor(255, 152, 0),
        "已完成": QColor(76, 175, 80),
        "失败": QColor(244, 67, 54),
        "下载中…": QColor(255, 193, 7),
        "已下载": QColor(27, 94, 32),
    }

    def paint(self, painter: QPainter, option, index):
        try:
            painter.save()

            status_key = index.data(Qt.UserRole) or ""

            if option.state & QStyle.State_Selected:
                painter.fillRect(option.rect, option.palette.highlight())
            elif status_key == TaskStatus.RUNNING.value:
                painter.fillRect(option.rect, QColor(173, 216, 230))  # light blue

            text = index.data(Qt.DisplayRole) or ""

            if status_key == TaskStatus.RUNNING.value:
                color = QColor(33, 150, 243)
            elif status_key == TaskStatus.DOWNLOADING.value:
                color = QColor(255, 193, 7)
            else:
                color = self.STATUS_COLORS.get(text, QColor(150, 150, 150))

            rect = option.rect.adjusted(4, 0, -4, 0)
            painter.setPen(color)
            painter.drawText(rect, Qt.AlignCenter, text)

            painter.restore()
        except Exception:
            logger.exception("StatusDelegate paint 异常")

    def sizeHint(self, option, index):
        return option.rect.size()
