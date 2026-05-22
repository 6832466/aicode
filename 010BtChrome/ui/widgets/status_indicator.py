from __future__ import annotations

from PySide6.QtCore import QModelIndex, QRect, QSize, Qt
from PySide6.QtGui import QBrush, QPainter
from PySide6.QtWidgets import QStyledItemDelegate, QStyleOptionViewItem

STATUS_OPEN = "open"
STATUS_CLOSED = "closed"
STATUS_UNKNOWN = "unknown"

COLOR_OPEN = QBrush("#22c55e")  # green
COLOR_CLOSED = QBrush("#94a3b8")  # gray
COLOR_UNKNOWN = QBrush("#f59e0b")  # amber


class StatusDelegate(QStyledItemDelegate):
    """在单元格中绘制状态圆点"""

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex):
        super().paint(painter, option, index)
        status = index.data(Qt.UserRole) or STATUS_UNKNOWN
        color = {
            STATUS_OPEN: COLOR_OPEN,
            STATUS_CLOSED: COLOR_CLOSED,
            STATUS_UNKNOWN: COLOR_UNKNOWN,
        }.get(status, COLOR_UNKNOWN)

        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = option.rect
        size = 10
        x = rect.center().x() - size // 2
        y = rect.center().y() - size // 2
        painter.setBrush(color)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(QRect(x, y, size, size))
        painter.restore()

    def sizeHint(self, option, index):
        return QSize(40, 24)
