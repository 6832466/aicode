"""SettingsDialog - Fluent-styled settings panel."""
from typing import Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QSlider,
    QDoubleSpinBox, QSpinBox, QPushButton, QGroupBox, QCheckBox,
)

from . import styles


class SettingsDialog(QDialog):
    settings_applied = Signal(dict)

    def __init__(self, config: dict[str, Any], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Gold Monitor 设置")
        self.setMinimumWidth(440)
        self.setMaximumWidth(520)
        self.setWindowFlags(
            Qt.WindowType.Dialog
            | Qt.WindowType.WindowCloseButtonHint
        )
        self._config = config
        self._build_ui()
        self._load_values()

    def _build_ui(self) -> None:
        self.setStyleSheet(styles.dialog_qss())

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(10)

        layout.addWidget(self._section_title("显示设置"))

        autostart_layout = QHBoxLayout()
        autostart_layout.addWidget(QLabel("开机自动启动"))
        self._autostart_check = QCheckBox()
        autostart_layout.addStretch()
        autostart_layout.addWidget(self._autostart_check)
        layout.addLayout(autostart_layout)

        opacity_layout = QHBoxLayout()
        opacity_layout.addWidget(QLabel("透明度"))
        self._opacity_slider = QSlider(Qt.Orientation.Horizontal)
        self._opacity_slider.setRange(20, 100)
        self._opacity_slider.setTickInterval(10)
        self._opacity_label = QLabel("85%")
        self._opacity_label.setFixedWidth(40)
        self._opacity_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        self._opacity_slider.valueChanged.connect(
            lambda v: self._opacity_label.setText(f"{v}%")
        )
        opacity_layout.addWidget(self._opacity_slider)
        opacity_layout.addWidget(self._opacity_label)
        layout.addLayout(opacity_layout)

        refresh_layout = QHBoxLayout()
        refresh_layout.addWidget(QLabel("刷新间隔(秒)"))
        self._refresh_spin = QSpinBox()
        self._refresh_spin.setRange(2, 300)
        self._refresh_spin.setSuffix(" 秒")
        refresh_layout.addStretch()
        refresh_layout.addWidget(self._refresh_spin)
        layout.addLayout(refresh_layout)

        layout.addWidget(self._section_title("价格阈值提醒 (0 = 关闭)"))

        au_group = QGroupBox("沪金9999 阈值")
        au_layout = QVBoxLayout(au_group)
        au_layout.setSpacing(6)

        au_upper = QHBoxLayout()
        au_upper.addWidget(QLabel("上破"))
        self._au_upper = QDoubleSpinBox()
        self._au_upper.setRange(0, 99999)
        self._au_upper.setDecimals(2)
        self._au_upper.setSuffix(" 元/克")
        self._au_upper.setMinimumWidth(140)
        au_upper.addStretch()
        au_upper.addWidget(self._au_upper)
        au_layout.addLayout(au_upper)

        au_lower = QHBoxLayout()
        au_lower.addWidget(QLabel("下破"))
        self._au_lower = QDoubleSpinBox()
        self._au_lower.setRange(0, 99999)
        self._au_lower.setDecimals(2)
        self._au_lower.setSuffix(" 元/克")
        self._au_lower.setMinimumWidth(140)
        au_lower.addStretch()
        au_lower.addWidget(self._au_lower)
        au_layout.addLayout(au_lower)
        layout.addWidget(au_group)

        xau_group = QGroupBox("国际金 阈值")
        xau_layout = QVBoxLayout(xau_group)
        xau_layout.setSpacing(6)

        xau_upper = QHBoxLayout()
        xau_upper.addWidget(QLabel("上破"))
        self._xau_upper = QDoubleSpinBox()
        self._xau_upper.setRange(0, 99999)
        self._xau_upper.setDecimals(2)
        self._xau_upper.setSuffix(" $")
        self._xau_upper.setMinimumWidth(140)
        xau_upper.addStretch()
        xau_upper.addWidget(self._xau_upper)
        xau_layout.addLayout(xau_upper)

        xau_lower = QHBoxLayout()
        xau_lower.addWidget(QLabel("下破"))
        self._xau_lower = QDoubleSpinBox()
        self._xau_lower.setRange(0, 99999)
        self._xau_lower.setDecimals(2)
        self._xau_lower.setSuffix(" $")
        self._xau_lower.setMinimumWidth(140)
        xau_lower.addStretch()
        xau_lower.addWidget(self._xau_lower)
        xau_layout.addLayout(xau_lower)
        layout.addWidget(xau_group)

        layout.addWidget(self._section_title("异动监测"))

        vol_window = QHBoxLayout()
        vol_window.addWidget(QLabel("监测窗口(分钟)"))
        self._vol_window = QSpinBox()
        self._vol_window.setRange(1, 60)
        vol_window.addStretch()
        vol_window.addWidget(self._vol_window)
        layout.addLayout(vol_window)

        vol_threshold = QHBoxLayout()
        vol_threshold.addWidget(QLabel("异动阈值(%)"))
        self._vol_threshold = QDoubleSpinBox()
        self._vol_threshold.setRange(0.0, 50)
        self._vol_threshold.setDecimals(1)
        self._vol_threshold.setSuffix(" % (0=关闭)")
        vol_threshold.addStretch()
        vol_threshold.addWidget(self._vol_threshold)
        layout.addLayout(vol_threshold)

        cooldown = QHBoxLayout()
        cooldown.addWidget(QLabel("冷却时间(秒)"))
        self._cooldown = QSpinBox()
        self._cooldown.setRange(10, 3600)
        self._cooldown.setSuffix(" 秒")
        cooldown.addStretch()
        cooldown.addWidget(self._cooldown)
        layout.addLayout(cooldown)

        layout.addStretch()

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        cancel_btn = QPushButton("取消")
        cancel_btn.setObjectName("cancelBtn")
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)
        apply_btn = QPushButton("应用")
        apply_btn.clicked.connect(self._apply)
        btn_layout.addWidget(apply_btn)
        layout.addLayout(btn_layout)

    def _section_title(self, text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setObjectName("sectionTitle")
        return lbl

    def _load_values(self) -> None:
        self._autostart_check.setChecked(self._config.get("autostart", False))
        self._opacity_slider.setValue(int(self._config.get("opacity", 0.85) * 100))
        self._refresh_spin.setValue(self._config.get("refresh_interval", 5))
        self._au_upper.setValue(self._config.get("au_threshold_upper", 0))
        self._au_lower.setValue(self._config.get("au_threshold_lower", 0))
        self._xau_upper.setValue(self._config.get("xau_threshold_upper", 0))
        self._xau_lower.setValue(self._config.get("xau_threshold_lower", 0))
        self._vol_window.setValue(self._config.get("volatility_window_minutes", 5))
        self._vol_threshold.setValue(self._config.get("volatility_threshold_pct", 1.0))
        self._cooldown.setValue(self._config.get("alert_cooldown_seconds", 60))

    def _apply(self) -> None:
        updates = {
            "opacity": self._opacity_slider.value() / 100.0,
            "refresh_interval": self._refresh_spin.value(),
            "autostart": self._autostart_check.isChecked(),
            "au_threshold_upper": self._au_upper.value(),
            "au_threshold_lower": self._au_lower.value(),
            "xau_threshold_upper": self._xau_upper.value(),
            "xau_threshold_lower": self._xau_lower.value(),
            "volatility_window_minutes": self._vol_window.value(),
            "volatility_threshold_pct": self._vol_threshold.value(),
            "alert_cooldown_seconds": self._cooldown.value(),
        }
        self.settings_applied.emit(updates)
        self.accept()
