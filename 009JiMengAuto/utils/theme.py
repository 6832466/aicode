"""深色主题样式定义 - 与界面原型一致"""

# 主题颜色（与HTML原型一致）
THEME = {
    "bg_dark": "#0f172a",      # 主背景色
    "bg_card": "#1e293b",      # 卡片/面板背景
    "bg_hover": "#334155",     # 悬停/选中背景
    "primary": "#6366f1",      # 主色调（紫蓝）
    "primary_hover": "#4f46e5",# 主色调悬停
    "success": "#10b981",      # 成功色（绿）
    "warning": "#f59e0b",      # 警告色（橙）
    "danger": "#ef4444",       # 危险色（红）
    "text_primary": "#f8fafc", # 文字主色
    "text_secondary": "#94a3b8",# 文字次色
    "border": "#475569",       # 边框色
}

# 状态颜色映射
STATUS_COLORS = {
    "pending": {"bg": "rgba(100,116,139,0.2)", "text": "#94a3b8", "dot": "#94a3b8"},
    "generating": {"bg": "rgba(96,165,250,0.15)", "text": "#60a5fa", "dot": "#60a5fa"},
    "completed": {"bg": "rgba(16,185,129,0.15)", "text": "#10b981", "dot": "#10b981"},
    "failed": {"bg": "rgba(239,68,68,0.15)", "text": "#ef4444", "dot": "#ef4444"},
    "downloading": {"bg": "rgba(96,165,250,0.15)", "text": "#60a5fa", "dot": "#60a5fa"},
    "downloaded": {"bg": "rgba(16,185,129,0.15)", "text": "#10b981", "dot": "#10b981"},
}


def apply_dark_theme(app):
    """应用深色主题到 QApplication"""
    from PySide6.QtWidgets import QApplication

    bg_dark = THEME["bg_dark"]
    bg_card = THEME["bg_card"]
    bg_hover = THEME["bg_hover"]
    primary = THEME["primary"]
    primary_hover = THEME["primary_hover"]
    text_primary = THEME["text_primary"]
    text_secondary = THEME["text_secondary"]
    border = THEME["border"]

    # 全局样式
    style = f"""
    QWidget {{
        background-color: {bg_dark};
        color: {text_primary};
        font-family: 'Microsoft YaHei UI', 'Segoe UI', sans-serif;
    }}

    /* 卡片背景 */
    QFrame, QGroupBox {{
        background-color: {bg_card};
        border: 1px solid {border};
        border-radius: 8px;
    }}

    /* 输入框 */
    QLineEdit, QTextEdit, QPlainTextEdit, QComboBox {{
        background-color: {bg_card};
        border: 1px solid {border};
        border-radius: 6px;
        padding: 6px 10px;
        color: {text_primary};
    }}

    QLineEdit:focus, QTextEdit:focus, QComboBox:focus {{
        border-color: {primary};
    }}

    /* 下拉框 */
    QComboBox::drop-down {{
        border: none;
        width: 20px;
    }}

    QComboBox::down-arrow {{
        image: none;
        border-left: 5px solid transparent;
        border-right: 5px solid transparent;
        border-top: 5px solid {text_secondary};
        margin-right: 8px;
    }}

    QComboBox QAbstractItemView {{
        background-color: {bg_card};
        border: 1px solid {border};
        selection-background-color: {bg_hover};
        color: {text_primary};
    }}

    /* 按钮 */
    QPushButton {{
        background-color: {bg_hover};
        border: 1px solid {border};
        border-radius: 8px;
        padding: 7px 14px;
        color: {text_primary};
    }}

    QPushButton:hover {{
        background-color: #475569;
    }}

    QPushButton:pressed {{
        background-color: {primary};
    }}

    /* 主按钮样式 */
    QPushButton[class="primary"] {{
        background-color: {primary};
        border: none;
    }}

    QPushButton[class="primary"]:hover {{
        background-color: {primary_hover};
    }}

    /* 表格 */
    QTableWidget, QTableView {{
        background-color: {bg_card};
        border: 1px solid {border};
        border-radius: 8px;
        gridline-color: rgba(71,85,105,0.3);
    }}

    QTableWidget::item, QTableView::item {{
        padding: 8px 12px;
        border-bottom: 1px solid rgba(71,85,105,0.3);
    }}

    QTableWidget::item:selected, QTableView::item:selected {{
        background-color: rgba(99,102,241,0.12);
    }}

    QHeaderView::section {{
        background-color: {bg_dark};
        border: none;
        border-bottom: 1px solid {border};
        padding: 8px 12px;
        color: {text_secondary};
        font-size: 11px;
    }}

    /* 滚动条 */
    QScrollBar:vertical {{
        background-color: transparent;
        width: 8px;
        border-radius: 4px;
    }}

    QScrollBar::handle:vertical {{
        background-color: #475569;
        border-radius: 4px;
        min-height: 20px;
    }}

    QScrollBar::handle:vertical:hover {{
        background-color: #64748b;
    }}

    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
        height: 0px;
    }}

    /* 标签 */
    QLabel {{
        color: {text_primary};
        background-color: transparent;
    }}

    /* 分割器 */
    QSplitter::handle {{
        background-color: {border};
    }}

    /* 进度条 */
    QProgressBar {{
        background-color: {bg_dark};
        border: none;
        border-radius: 4px;
        height: 8px;
        text-align: center;
    }}

    QProgressBar::chunk {{
        background-color: {primary};
        border-radius: 4px;
    }}

    /* 复选框 */
    QCheckBox::indicator {{
        width: 16px;
        height: 16px;
        border: 2px solid {border};
        border-radius: 3px;
        background-color: transparent;
    }}

    QCheckBox::indicator:checked {{
        background-color: {primary};
        border-color: {primary};
    }}

    /* 菜单 */
    QMenu {{
        background-color: {bg_card};
        border: 1px solid {border};
    }}

    QMenu::item:selected {{
        background-color: {bg_hover};
    }}
    """

    app.setStyleSheet(style)


def get_status_style(status: str) -> dict:
    """获取状态对应的样式"""
    return STATUS_COLORS.get(status, STATUS_COLORS["pending"])
