"""共用 UI 组件 - 深色主题风格"""

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QLabel, QFrame, QSizePolicy
)
from qfluentwidgets import (
    CardWidget, BodyLabel, CaptionLabel, StrongBodyLabel,
    PushButton, PrimaryPushButton, ToolButton,
    FluentIcon, ComboBox, LineEdit, TextEdit,
    ProgressBar, IconWidget,
)

from utils.theme import THEME, STATUS_COLORS


class StatCard(CardWidget):
    """统计卡片 - 用于顶部统计行"""

    def __init__(self, title: str, value: int = 0, icon: str = "",
                 color: str = THEME["text_primary"], parent=None):
        super().__init__(parent)
        self._title = title
        self._icon = icon
        self._color = color

        self._init_ui()
        self.set_value(value)

    def _init_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(12)

        # 图标
        if self._icon:
            icon_label = QLabel(self._icon)
            icon_label.setStyleSheet(f"font-size: 20px;")
            layout.addWidget(icon_label)

        # 数值和标题
        info_layout = QVBoxLayout()
        info_layout.setSpacing(2)

        self._value_label = StrongBodyLabel("0")
        self._value_label.setStyleSheet(f"""
            font-size: 22px;
            font-weight: 700;
            color: {self._color};
        """)
        info_layout.addWidget(self._value_label)

        self._title_label = CaptionLabel(self._title)
        self._title_label.setStyleSheet(f"color: {THEME['text_secondary']};")
        info_layout.addWidget(self._title_label)

        layout.addLayout(info_layout)
        layout.addStretch()

        self.setBorderRadius(10)

    def set_value(self, v: int):
        self._value_label.setText(str(v))

    def set_color(self, color: str):
        self._color = color
        self._value_label.setStyleSheet(f"""
            font-size: 22px;
            font-weight: 700;
            color: {color};
        """)


class StatusBadge(QWidget):
    """状态标签 - 用于表格中显示任务状态"""

    def __init__(self, status: str, parent=None):
        super().__init__(parent)
        self._status = status
        self._init_ui()

    def _init_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        colors = STATUS_COLORS.get(self._status, STATUS_COLORS["pending"])

        # 状态点
        dot = QLabel("●")
        dot.setStyleSheet(f"color: {colors['dot']}; font-size: 10px;")
        dot.setFixedWidth(10)
        layout.addWidget(dot)

        # 状态文本
        text_map = {
            "pending": "待生成",
            "generating": "生成中",
            "completed": "已完成",
            "failed": "失败",
            "downloading": "下载中",
            "downloaded": "已下载",
        }
        text = text_map.get(self._status, self._status)

        label = QLabel(text)
        label.setStyleSheet(f"""
            color: {colors['text']};
            font-size: 11px;
            font-weight: 500;
            padding: 2px 8px;
            background-color: {colors['bg']};
            border-radius: 10px;
        """)
        layout.addWidget(label)

    def update_status(self, status: str):
        self._status = status
        # 需要重新创建UI或更新样式


class NavButton(QWidget):
    """导航按钮 - 用于左侧导航菜单"""

    def __init__(self, icon: str, text: str, active: bool = False, parent=None):
        super().__init__(parent)
        self._active = active
        self._icon = icon
        self._text = text
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 8, 6, 8)
        layout.setSpacing(4)
        layout.setAlignment(Qt.AlignCenter)

        # 图标
        icon_label = QLabel(self._icon)
        icon_label.setAlignment(Qt.AlignCenter)
        icon_label.setStyleSheet(f"font-size: 18px;")
        layout.addWidget(icon_label)

        # 文字
        text_label = QLabel(self._text)
        text_label.setAlignment(Qt.AlignCenter)
        text_label.setStyleSheet(f"""
            font-size: 12px;
            color: {THEME['text_secondary'] if not self._active else THEME['primary']};
        """)
        layout.addWidget(text_label)

        # 背景
        if self._active:
            self.setStyleSheet(f"""
                background-color: rgba(99,102,241,0.15);
                border-radius: 8px;
            """)
        else:
            self.setStyleSheet("background-color: transparent; border-radius: 8px;")

        self.setCursor(Qt.PointingHandCursor)
        self.setFixedHeight(50)

    def set_active(self, active: bool):
        self._active = active
        self._update_style()

    def _update_style(self):
        if self._active:
            self.setStyleSheet(f"""
                background-color: rgba(99,102,241,0.15);
                border-radius: 8px;
            """)
        else:
            self.setStyleSheet("background-color: transparent; border-radius: 8px;")

        # 更新文字颜色
        text_label = self.findChild(QLabel, "")
        for child in self.children():
            if isinstance(child, QLabel) and child.text() == self._text:
                color = THEME['primary'] if self._active else THEME['text_secondary']
                child.setStyleSheet(f"font-size: 12px; color: {color};")


class DetailPanel(CardWidget):
    """详情面板 - 用于右侧任务详情"""

    def __init__(self, title: str = "任务详情", parent=None):
        super().__init__(parent)
        self._title = title
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        # 标题行
        header_layout = QHBoxLayout()
        self._title_label = StrongBodyLabel(self._title)
        self._title_label.setStyleSheet("font-size: 14px;")
        header_layout.addWidget(self._title_label)
        header_layout.addStretch()
        layout.addLayout(header_layout)

        # 内容区域（由外部填充）
        self._content_widget = QWidget()
        self._content_layout = QVBoxLayout(self._content_widget)
        self._content_layout.setContentsMargins(0, 0, 0, 0)
        self._content_layout.setSpacing(8)
        layout.addWidget(self._content_widget)

        self.setBorderRadius(12)

    def set_title(self, title: str):
        self._title_label.setText(title)

    def clear_content(self):
        # 清空内容区域
        while self._content_layout.count():
            item = self._content_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()


class MaterialThumbnail(CardWidget):
    """素材缩略图卡片"""

    def __init__(self, material_info, parent=None):
        super().__init__(parent)
        self._material = material_info
        self._init_ui()

    def _init_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        # 图标/缩略图
        icon_widget = QLabel(self._material.material_type.icon())
        icon_widget.setStyleSheet("""
            font-size: 24px;
            background: linear-gradient(135deg, #4338ca, #7c3aed);
            border-radius: 6px;
            padding: 10px;
        """)
        icon_widget.setFixedSize(44, 44)
        icon_widget.setAlignment(Qt.AlignCenter)
        layout.addWidget(icon_widget)

        # 信息
        info_layout = QVBoxLayout()
        info_layout.setSpacing(2)

        # 列名（素材来源）
        col_label = CaptionLabel(self._material.column_name or self._material.character_name)
        col_label.setStyleSheet(f"font-size: 12px; font-weight: 500;")
        info_layout.addWidget(col_label)

        # 文件路径
        path = self._material.file_path
        if len(path) > 40:
            path = path[:40] + "..."
        path_label = CaptionLabel(path)
        path_label.setStyleSheet(f"color: {THEME['text_secondary']}; font-size: 11px;")
        info_layout.addWidget(path_label)

        # 文件大小
        from utils.helpers import format_file_size
        size_text = format_file_size(self._material.file_size) if self._material.file_size > 0 else "--"
        size_label = CaptionLabel(f"{size_text} · {self._material.file_extension.upper()}")
        size_label.setStyleSheet(f"color: {THEME['text_secondary']}; font-size: 11px;")
        info_layout.addWidget(size_label)

        layout.addLayout(info_layout)
        layout.addStretch()

        # 替换按钮
        btn_replace = ToolButton(FluentIcon.EDIT)
        btn_replace.setFixedSize(28, 28)
        layout.addWidget(btn_replace)

        self.setBorderRadius(8)


class LogLine(QWidget):
    """日志行"""

    def __init__(self, time: str, level: str, message: str, parent=None):
        super().__init__(parent)
        self._time = time
        self._level = level
        self._message = message
        self._init_ui()

    def _init_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 3, 6, 3)
        layout.setSpacing(8)

        # 时间
        time_label = QLabel(self._time)
        time_label.setStyleSheet(f"color: #475569; font-size: 12px;")
        layout.addWidget(time_label)

        # 级别
        level_colors = {
            "INFO": THEME["text_secondary"],
            "WARN": THEME["warning"],
            "ERROR": THEME["danger"],
        }
        level_color = level_colors.get(self._level, THEME["text_secondary"])
        level_label = QLabel(f"[{self._level}]")
        level_label.setStyleSheet(f"color: {level_color}; font-size: 12px; font-weight: 500;")
        layout.addWidget(level_label)

        # 消息
        msg_label = QLabel(self._message)
        msg_label.setStyleSheet(f"color: {THEME['text_primary']}; font-size: 12px;")
        msg_label.setWordWrap(True)
        layout.addWidget(msg_label, 1)

        # 背景
        if self._level == "ERROR":
            self.setStyleSheet(f"background-color: rgba(239,68,68,0.08); border-radius: 3px;")
        elif self._level == "WARN":
            self.setStyleSheet(f"background-color: rgba(245,158,11,0.06); border-radius: 3px;")
        else:
            self.setStyleSheet("background-color: transparent;")