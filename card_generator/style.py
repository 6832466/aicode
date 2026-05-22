"""Fluent Design 风格的 QSS 样式表"""

# 颜色常量
COLORS = {
    "bg": "#f5f5f7",
    "surface": "#ffffff",
    "surface2": "#f5f5f7",
    "border": "#d2d2d7",
    "text_primary": "#1d1d1f",
    "text_secondary": "#6e6e73",
    "text_tertiary": "#86868b",
    "accent": "#0071e3",
    "accent_hover": "#0077ed",
    "accent_light": "#e8f0fe",
    "red": "#ff3b30",
    "green": "#30d158",
    "orange": "#ff9500",
    "radius": "14px",
    "radius_sm": "8px",
}

GLOBAL_QSS = """
/* ── 全局 ── */
QWidget {
    font-family: "Segoe UI", "Microsoft YaHei", "Microsoft YaHei UI", sans-serif;
    font-size: 13px;
    color: #1d1d1f;
}

QMainWindow {
    background: #f5f5f7;
}

/* ── 滚动条 ── */
QScrollBar:vertical {
    background: transparent;
    width: 6px;
    margin: 0;
}
QScrollBar::handle:vertical {
    background: #d2d2d7;
    border-radius: 3px;
    min-height: 30px;
}
QScrollBar::handle:vertical:hover {
    background: #b0b0b5;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0;
}
QScrollBar:horizontal {
    background: transparent;
    height: 6px;
}
QScrollBar::handle:horizontal {
    background: #d2d2d7;
    border-radius: 3px;
}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
    width: 0;
}

/* ── 输入框 ── */
QTextEdit, QPlainTextEdit, QLineEdit {
    background: #f5f5f7;
    border: 1px solid #d2d2d7;
    border-radius: 8px;
    padding: 8px 10px;
    font-size: 12px;
    color: #1d1d1f;
    selection-background-color: #0071e3;
    selection-color: white;
}
QTextEdit:focus, QPlainTextEdit:focus, QLineEdit:focus {
    border-color: #0071e3;
}

QComboBox {
    background: #f5f5f7;
    border: 1px solid #d2d2d7;
    border-radius: 6px;
    padding: 5px 10px;
    font-size: 12px;
    color: #1d1d1f;
}
QComboBox:focus {
    border-color: #0071e3;
}
QComboBox::drop-down {
    border: none;
    width: 20px;
}
QComboBox QAbstractItemView {
    background: #ffffff;
    border: 1px solid #d2d2d7;
    border-radius: 6px;
    padding: 4px;
    selection-background-color: #e8f0fe;
    selection-color: #1d1d1f;
    outline: none;
}

/* ── 按钮 ── */
QPushButton {
    border: none;
    border-radius: 18px;
    padding: 8px 18px;
    font-size: 13px;
    font-weight: 500;
    background: #f5f5f7;
    color: #1d1d1f;
    border: 1px solid #d2d2d7;
}
QPushButton:hover {
    background: #e8e8ed;
}
QPushButton:pressed {
    background: #dcdce0;
}
QPushButton:disabled {
    opacity: 0.4;
    color: #86868b;
}

QPushButton[cssClass="primary"] {
    background: #0071e3;
    color: white;
    border: none;
}
QPushButton[cssClass="primary"]:hover {
    background: #0077ed;
}
QPushButton[cssClass="primary"]:pressed {
    background: #0066cc;
}

QPushButton[cssClass="danger"] {
    background: rgba(255,59,48,0.1);
    color: #ff3b30;
    border: 1px solid rgba(255,59,48,0.2);
}
QPushButton[cssClass="danger"]:hover {
    background: rgba(255,59,48,0.18);
}

QPushButton[cssClass="retry"] {
    background: rgba(255,149,0,0.1);
    color: #d97706;
    border: 1px solid rgba(255,149,0,0.3);
}
QPushButton[cssClass="retry"]:hover {
    background: rgba(255,149,0,0.2);
}

QPushButton[cssClass="download"] {
    background: rgba(48,209,88,0.1);
    color: #1a8a3c;
    border: 1px solid rgba(48,209,88,0.25);
}
QPushButton[cssClass="download"]:hover {
    background: rgba(48,209,88,0.2);
}

QPushButton[cssClass="ratio"] {
    height: 26px;
    padding: 0 10px;
    border: 1px solid #d2d2d7;
    border-radius: 6px;
    background: #f5f5f7;
    color: #6e6e73;
    font-size: 11px;
    font-weight: 500;
}
QPushButton[cssClass="ratio"]:hover {
    border-color: #0071e3;
    color: #0071e3;
}
QPushButton[cssClass="ratio"][active="true"] {
    background: #0071e3;
    border-color: #0071e3;
    color: white;
    font-weight: 600;
}

QPushButton[cssClass="small"] {
    height: 28px;
    padding: 0 12px;
    font-size: 12px;
    border-radius: 14px;
}

QPushButton[cssClass="inline"] {
    height: 24px;
    padding: 0 8px;
    font-size: 10px;
    border-radius: 12px;
}

QPushButton[cssClass="card-action"] {
    height: 28px;
    padding: 0 10px;
    font-size: 11px;
    border-radius: 14px;
    flex: 1;
}

/* ── 标签 ── */
QLabel[cssClass="section-label"] {
    font-size: 11px;
    font-weight: 600;
    color: #86868b;
    text-transform: uppercase;
    margin-top: 16px;
    margin-bottom: 8px;
}

QLabel[cssClass="sidebar-title"] {
    font-size: 17px;
    font-weight: 600;
    color: #1d1d1f;
}

QLabel[cssClass="sidebar-subtitle"] {
    font-size: 12px;
    color: #86868b;
}

QLabel[cssClass="badge"] {
    font-size: 11px;
    font-weight: 600;
    color: #0071e3;
    background: #e8f0fe;
    border-radius: 10px;
    padding: 2px 8px;
}

QLabel[cssClass="card-name"] {
    font-size: 15px;
    font-weight: 600;
    color: #1d1d1f;
}

QLabel[cssClass="card-aliases"] {
    font-size: 12px;
    color: #86868b;
}

QLabel[cssClass="card-desc"] {
    font-size: 12px;
    color: #6e6e73;
    line-height: 1.5;
}

/* ── 分割线 ── */
QFrame[cssClass="separator"] {
    background: #d2d2d7;
    max-height: 1px;
}

/* ── 复选框 ── */
QCheckBox {
    font-size: 13px;
    color: #1d1d1f;
    spacing: 8px;
}
QCheckBox::indicator {
    width: 15px;
    height: 15px;
    border: 2px solid #d2d2d7;
    border-radius: 4px;
    background: white;
}
QCheckBox::indicator:checked {
    background: #0071e3;
    border-color: #0071e3;
}

/* ── 进度条 ── */
QProgressBar {
    height: 4px;
    background: #d2d2d7;
    border-radius: 2px;
    border: none;
}
QProgressBar::chunk {
    background: #0071e3;
    border-radius: 2px;
}

/* ── 卡片 ── */
QFrame[cssClass="char-card"] {
    background: #ffffff;
    border: 1px solid #d2d2d7;
    border-radius: 14px;
}

QFrame[cssClass="char-card"]:hover {
    border-color: #b0b0b8;
}

/* ── 分组框 ── */
QGroupBox[cssClass="quick-panel"] {
    background: #e8f0fe;
    border: 1px solid rgba(0,113,227,0.2);
    border-radius: 8px;
    margin-top: 8px;
    padding: 0;
}

QGroupBox[cssClass="ref-images-section"] {
    background: #f5f5f7;
    border: 1px dashed #d2d2d7;
    border-radius: 8px;
    padding: 10px;
}

/* ── 工具提示 ── */
QToolTip {
    background: rgba(29,29,31,0.88);
    color: white;
    border-radius: 10px;
    padding: 6px 12px;
    font-size: 12px;
    border: none;
}
"""

# 卡片网格的 QSS - 根据不同比例
CARD_GRID_STYLE = """
QWidget#cardGridWidget {
    background: transparent;
}
"""
