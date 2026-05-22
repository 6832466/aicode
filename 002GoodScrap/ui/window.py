"""FloatingWindow - borderless, always-on-top, draggable gold price card."""
from datetime import datetime

from PySide6.QtCore import Qt, QPoint, QTimer, Signal
from PySide6.QtGui import QPixmap, QIcon
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QMenu,
    QApplication,
)

from _icon import get_icon_bytes

from core.fetcher import PriceData
from . import styles

CARD_WIDTH = 280
CARD_HEIGHT = 185


class FloatingWindow(QWidget):
    settings_requested = Signal()
    theme_changed = Signal(str)

    def __init__(self, config_getter, config_setter, save_position):
        super().__init__()
        self._get_config = config_getter
        self._set_config = config_setter
        self._save_position = save_position
        self._dragging = False
        self._drag_pos = QPoint()
        self._flash_timer: QTimer | None = None
        self._flash_steps: list[str] = []
        self._flash_idx: int = 0
        self._prev_au: float = 0.0
        self._prev_xau: float = 0.0

        self._init_window()
        self._init_ui()
        self._init_menu()
        self._restore_position()

    def _init_window(self) -> None:
        self.setObjectName("floatingCard")
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setFixedSize(CARD_WIDTH, CARD_HEIGHT)

        pixmap = QPixmap()
        pixmap.loadFromData(get_icon_bytes())
        self.setWindowIcon(QIcon(pixmap))

        self.setStyleSheet(styles.window_qss())

        cfg = self._get_config()
        self.setWindowOpacity(cfg.get("opacity", 0.85))

    def _init_ui(self) -> None:
        self._content_widget = QWidget(self)
        self._content_widget.setGeometry(0, 0, CARD_WIDTH, CARD_HEIGHT)
        self._content_widget.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self._content_widget.setStyleSheet(styles.content_qss())

        layout = QVBoxLayout(self._content_widget)
        layout.setContentsMargins(16, 14, 16, 12)
        layout.setSpacing(6)

        title = QLabel("GOLD  MONITOR")
        title.setObjectName("titleLabel")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        sep = QLabel()
        sep.setObjectName("separator")
        sep.setFixedHeight(1)
        layout.addWidget(sep)

        au_name = QLabel("沪金9999  (元/克)")
        au_name.setObjectName("nameLabel")
        layout.addWidget(au_name)

        au_row = QHBoxLayout()
        au_row.setSpacing(6)
        self._au_price = QLabel("--.--")
        self._au_price.setObjectName("priceLabelAU")
        self._au_arrow = QLabel("")
        self._au_arrow.setObjectName("priceLabelAU")
        self._au_arrow.setFixedWidth(18)
        self._au_arrow.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._au_change = QLabel("0.00%")
        self._au_change.setObjectName("changeLabelAU")
        au_row.addWidget(self._au_price)
        au_row.addWidget(self._au_arrow)
        au_row.addStretch()
        au_row.addWidget(self._au_change)
        layout.addLayout(au_row)

        xau_name = QLabel("国际金  (美元/盎司)")
        xau_name.setObjectName("nameLabel")
        layout.addWidget(xau_name)

        xau_row = QHBoxLayout()
        xau_row.setSpacing(6)
        self._xau_price = QLabel("--.--")
        self._xau_price.setObjectName("priceLabelXAU")
        self._xau_arrow = QLabel("")
        self._xau_arrow.setObjectName("priceLabelXAU")
        self._xau_arrow.setFixedWidth(18)
        self._xau_arrow.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._xau_change = QLabel("0.00%")
        self._xau_change.setObjectName("changeLabelXAU")
        xau_row.addWidget(self._xau_price)
        xau_row.addWidget(self._xau_arrow)
        xau_row.addStretch()
        xau_row.addWidget(self._xau_change)
        layout.addLayout(xau_row)

        sep2 = QLabel()
        sep2.setObjectName("separator")
        sep2.setFixedHeight(1)
        layout.addWidget(sep2)

        self._time_label = QLabel("等待数据...")
        self._time_label.setObjectName("更新时间")
        self._time_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._time_label)

    def _init_menu(self) -> None:
        self._menu = QMenu(self)
        self._rebuild_menu()

    def _rebuild_menu(self) -> None:
        self._menu.clear()
        self._menu.setStyleSheet(styles.menu_qss())

        theme_menu = self._menu.addMenu("切换主题")
        current = styles.CURRENT
        for name in styles.get_theme_names():
            label = f"● {name}" if name == current else f"    {name}"
            action = theme_menu.addAction(label)
            action.triggered.connect(lambda checked, n=name: self.theme_changed.emit(n))

        self._menu.addSeparator()

        settings_action = self._menu.addAction("设置")
        settings_action.triggered.connect(self.settings_requested.emit)

        self._menu.addSeparator()

        exit_action = self._menu.addAction("退出")
        exit_action.triggered.connect(QApplication.instance().quit)

    def apply_theme(self, name: str) -> None:
        styles.set_theme(name)
        self.setStyleSheet(styles.window_qss())
        self._content_widget.setStyleSheet(styles.content_qss())
        self._rebuild_menu()

    def _restore_position(self) -> None:
        cfg = self._get_config()
        x = cfg.get("window_x", -1)
        y = cfg.get("window_y", -1)
        if x >= 0 and y >= 0:
            self.move(x, y)
        else:
            screen = QApplication.primaryScreen()
            if screen:
                geo = screen.availableGeometry()
                self.move(geo.right() - CARD_WIDTH - 20, geo.top() + 80)

    def update_prices(self, au: PriceData | None, xau: PriceData | None) -> None:
        try:
            self._do_update_prices(au, xau)
        except Exception:
            pass

    def _do_update_prices(self, au: PriceData | None, xau: PriceData | None) -> None:
        now = datetime.now().strftime("%H:%M:%S")

        if au and au.price > 0:
            arrow, arrow_color = self._arrow_for("AU", au.price)
            self._au_price.setText(f"{au.price:.2f}")
            self._au_arrow.setText(arrow)
            self._au_arrow.setStyleSheet(
                f"color: {arrow_color}; font-size: 20px; font-weight: 700;")
            color = styles.get_color("up") if au.change_pct > 0 else (
                styles.get_color("down") if au.change_pct < 0 else styles.get_color("label"))
            sign = "+" if au.change_pct > 0 else ""
            self._au_change.setText(f"{sign}{au.change_pct:.2f}%")
            self._au_change.setStyleSheet(f"color: {color}; font-size: 13px; font-weight: 600;")
        else:
            self._au_price.setText("--.--")
            self._au_arrow.setText("")
            self._au_change.setText("获取失败")
            self._au_change.setStyleSheet(
                f"color: {styles.get_color('time')}; font-size: 13px;")

        if xau and xau.price > 0:
            arrow, arrow_color = self._arrow_for("XAU", xau.price)
            self._xau_price.setText(f"{xau.price:.2f}")
            self._xau_arrow.setText(arrow)
            self._xau_arrow.setStyleSheet(
                f"color: {arrow_color}; font-size: 20px; font-weight: 700;")
            color = styles.get_color("up") if xau.change_pct > 0 else (
                styles.get_color("down") if xau.change_pct < 0 else styles.get_color("label"))
            sign = "+" if xau.change_pct > 0 else ""
            self._xau_change.setText(f"{sign}{xau.change_pct:.2f}%")
            self._xau_change.setStyleSheet(f"color: {color}; font-size: 13px; font-weight: 600;")
        else:
            self._xau_price.setText("--.--")
            self._xau_arrow.setText("")
            self._xau_change.setText("获取失败")
            self._xau_change.setStyleSheet(
                f"color: {styles.get_color('time')}; font-size: 13px;")

        self._time_label.setText(f"更新 {now}")

    def _arrow_for(self, metal: str, price: float) -> tuple[str, str]:
        prev = self._prev_au if metal == "AU" else self._prev_xau
        if prev <= 0:
            if metal == "AU":
                self._prev_au = price
            else:
                self._prev_xau = price
            return "•", styles.get_color("arrow_neutral")
        if price > prev:
            result = "↑", styles.get_color("arrow_up")
        elif price < prev:
            result = "↓", styles.get_color("arrow_down")
        else:
            result = "•", styles.get_color("arrow_neutral")
        if metal == "AU":
            self._prev_au = price
        else:
            self._prev_xau = price
        return result

    def flash_alert(self, direction: str) -> None:
        # Red → Yellow → Green three-color cycle, 2 loops = 6 flashes
        self._flash_steps = ["#F04438", "#F5B800", "#2EA85A"] * 2
        self._flash_idx = 0

        if self._flash_timer:
            self._flash_timer.stop()

        self._flash_timer = QTimer(self)
        self._flash_timer.timeout.connect(self._do_flash_step)
        self._flash_timer.start(350)
        self._do_flash_step()

    def _do_flash_step(self) -> None:
        if self._flash_idx >= len(self._flash_steps):
            self.setStyleSheet(styles.window_qss())
            if self._flash_timer:
                self._flash_timer.stop()
            return
        color = self._flash_steps[self._flash_idx]
        self._flash_idx += 1
        self.setStyleSheet(styles.flash_card_qss_color(color))

    def apply_opacity(self, value: float) -> None:
        self.setWindowOpacity(max(0.2, min(1.0, value)))
        self._set_config("opacity", value)

    def contextMenuEvent(self, event) -> None:
        self._menu.exec(event.globalPosition().toPoint())

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._dragging = True
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, event) -> None:
        if self._dragging:
            self.move(event.globalPosition().toPoint() - self._drag_pos)

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._dragging = False
            pos = self.pos()
            self._save_position(pos.x(), pos.y())
