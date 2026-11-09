# scripts/gui_app.py
"""
交换机巡检工具 - GUI启动入口

打包命令:
  pyinstaller --onefile --windowed --add-data "config;config" --name 交换机巡检工具v1.2.1 scripts/gui_app.py
"""
import argparse
import sys
from pathlib import Path

# 添加项目根目录到Python路径（仅开发模式，打包后不需要）
if not getattr(sys, 'frozen', False):
    project_root = Path(__file__).resolve().parent.parent
    sys.path.insert(0, str(project_root))

from PySide6.QtWidgets import QApplication
from ui.toolbox_window import APP_NAME, ToolboxWindow, __version__
from core.config_loader import get_default_config_path


# ============================================================
# 全局 QSS 样式表
# 色彩: 主色 #2563EB | 成功 #16A34A | 危险 #DC2626
#       背景 #F8F9FB | 卡片 #FFFFFF | 边框 #E2E5EA
#       文字主 #1E2028 | 文字次 #6B7280
# ============================================================
GLOBAL_QSS = """
/* ===== 全局 ===== */
QMainWindow, QWidget#centralWidget {
    background-color: #F8F9FB;
    font-family: "Microsoft YaHei", "Segoe UI", sans-serif;
    font-size: 13px;
    color: #1E2028;
}

/* ===== 卡片 ===== */
QGroupBox {
    background-color: #FFFFFF;
    border: 1px solid #E2E5EA;
    border-radius: 8px;
    margin-top: 14px;
    padding: 16px;
    font-weight: 600;
    font-size: 14px;
    color: #1E2028;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 12px;
    padding: 0 8px;
    color: #2563EB;
}
/* 命令选择框标题 — 蓝色大号文字 */
QGroupBox#cmd_group::title {
    color: #2563EB;
    background: transparent;
    padding-top: 5px;
    font-size: 16px;
}

/* ===== 输入框 ===== */
QLineEdit, QSpinBox, QComboBox, QTextEdit, QPlainTextEdit {
    background-color: #FFFFFF;
    border: 1px solid #E2E8F0;
    border-radius: 6px;
    padding: 8px 12px;
    font-size: 14px;
    color: #1E293B;
    selection-background-color: #2563EB;
}
QLineEdit:focus, QSpinBox:focus, QTextEdit:focus, QPlainTextEdit:focus {
    border: 1px solid #2563EB;
}
QLineEdit:hover, QSpinBox:hover, QComboBox:hover {
    border-color: #CBD5E1;
}

/* 下拉菜单 */
QComboBox {
    min-height: 20px;
}
QComboBox::drop-down {
    border: none;
    width: 24px;
}
QComboBox::down-arrow {
    border-left: 5px solid transparent;
    border-right: 5px solid transparent;
    border-top: 5px solid #6B7280;
    margin-right: 4px;
}
QComboBox:on {
    border-color: #2563EB;
}
QComboBox QAbstractItemView {
    background-color: #FFFFFF;
    color: #1E2028;
    border: 1px solid #D0D5DD;
    border-radius: 4px;
    selection-background-color: #E0E7FF;
    selection-color: #1E2028;
    outline: none;
    padding: 2px;
}
QComboBox QAbstractItemView::item {
    padding: 4px 8px;
    min-height: 24px;
}
QComboBox QAbstractItemView::item:hover {
    background-color: #F1F5F9;
}

/* ===== 表格内嵌控件 ===== */
QTableWidget QComboBox {
    border: 1px solid #D0D5DD;
    border-radius: 4px;
    background-color: #FFFFFF;
    color: #1E2028;
    padding: 2px 4px;
    min-height: 24px;
    font-size: 13px;
}
QTableWidget QComboBox::drop-down {
    border: none;
    width: 20px;
}
QTableWidget QComboBox QAbstractItemView {
    background-color: #FFFFFF;
    color: #1E2028;
    border: 1px solid #D0D5DD;
    border-radius: 4px;
    selection-background-color: #E0E7FF;
}
QTableWidget QLineEdit {
    border: 1px solid #D0D5DD;
    border-radius: 4px;
    background-color: #FFFFFF;
    color: #1E2028;
    padding: 2px 4px;
    font-size: 13px;
}
QTableWidget QLineEdit:focus {
    border-color: #2563EB;
}

/* ===== 按钮 ===== */
QPushButton {
    background-color: #2563EB;
    color: white;
    border: none;
    border-radius: 6px;
    padding: 8px 16px;
    font-size: 14px;
    font-weight: 500;
    min-height: 24px;
}
QPushButton:hover {
    background-color: #3B82F6;
}
QPushButton:pressed {
    background-color: #1D4ED8;
}
QPushButton:disabled {
    background-color: #94A3B8;
    color: rgba(255,255,255,0.7);
}

/* 主按钮 */
QPushButton#start_button {
    background-color: #2563EB;
}
QPushButton#start_button:hover {
    background-color: #1D4ED8;
}
QPushButton#start_button:pressed {
    background-color: #1E40AF;
}
QPushButton#start_button:disabled {
    background-color: #93C5FD;
}

/* 绿色按钮 */
QPushButton#connect_button {
    background-color: #16A34A;
}
QPushButton#connect_button:hover {
    background-color: #15803D;
}
QPushButton#connect_button:pressed {
    background-color: #166534;
}
QPushButton#connect_button:disabled {
    background-color: #86EFAC;
}

/* 红色按钮（清空结果） */
QPushButton#clear_button {
    background-color: #EF4444;
}
QPushButton#clear_button:hover {
    background-color: #F87171;
}
QPushButton#clear_button:pressed {
    background-color: #DC2626;
}

/* 工具栏按钮 */
QPushButton#btn_tool {
    background-color: #FFFFFF;
    color: #1E293B;
    border: 1px solid #D0D5DD;
    border-radius: 6px;
    padding: 6px 14px;
    font-weight: 500;
    font-size: 12px;
}
QPushButton#btn_tool:hover {
    background-color: #F1F5F9;
    border-color: #9CA3AF;
}
QPushButton#btn_tool:pressed {
    background-color: #E2E8F0;
}

/* 次要按钮 */
QPushButton#btn_select_all, QPushButton#btn_clear_all {
    background-color: #FFFFFF;
    color: #1E293B;
    border: 1px solid #D0D5DD;
    border-radius: 6px;
    padding: 4px 14px;
    font-weight: 500;
    font-size: 12px;
}
QPushButton#btn_select_all:hover, QPushButton#btn_clear_all:hover {
    background-color: #F1F5F9;
    border-color: #9CA3AF;
}
QPushButton#btn_select_all:pressed, QPushButton#btn_clear_all:pressed {
    background-color: #E2E8F0;
}

/* 密码切换按钮（表格内） */
QPushButton#pwd_toggle {
    background: transparent;
    border: none;
    font-size: 16px;
    padding: 0;
    color: #9CA3AF;
}
QPushButton#pwd_toggle:hover {
    background-color: #F1F5F9;
    border-radius: 4px;
    color: #1E2028;
}
QPushButton#pwd_toggle:checked {
    color: #2563EB;
}

/* ===== QTableWidget ===== */
QTableWidget {
    background-color: #FFFFFF;
    border: 1px solid #E2E8F0;
    border-radius: 8px;
    gridline-color: #F1F5F9;
    alternate-background-color: #F8FAFC;
    selection-background-color: #EFF6FF;
    selection-color: #2563EB;
    color: #1E293B;
    outline: none;
}
QTableWidget::item {
    padding: 6px 8px;
    min-height: 34px;
    color: #1E293B;
    font-size: 13px;
    border-bottom: 1px solid #F1F5F9;
}
QTableWidget::item:hover {
    background-color: #F1F5F9;
}
QTableWidget::item:selected {
    background-color: #EFF6FF;
    color: #2563EB;
}

/* ===== QTableWidget 表头 ===== */
QHeaderView {
    background-color: #F8FAFC;
    border: none;
    font-weight: 600;
    color: #475569;
}
QHeaderView::section {
    background-color: #F8FAFC;
    border: none;
    border-right: 1px solid #E2E8F0;
    border-bottom: 1px solid #E2E8F0;
    padding: 10px 8px;
    font-weight: 600;
    font-size: 13px;
    color: #475569;
}
QHeaderView::section:last {
    border-right: none;
}

/* ===== QTreeWidget ===== */
QTreeWidget {
    background-color: #FFFFFF;
    border: 1px solid #E2E8F0;
    border-radius: 8px;
    alternate-background-color: #F8FAFC;
    selection-background-color: #EFF6FF;
    selection-color: #2563EB;
    color: #1E293B;
    outline: none;
}
QTreeWidget::item {
    padding: 6px 8px;
    min-height: 30px;
    color: #1E293B;
    font-size: 13px;
    border-bottom: 1px solid #F1F5F9;
}
QTreeWidget::item:hover {
    background-color: #F1F5F9;
}
QTreeWidget::item:selected {
    background-color: #EFF6FF;
    color: #2563EB;
}

/* ===== 进度条 ===== */
QProgressBar {
    background-color: #E2E5EA;
    border: none;
    border-radius: 4px;
    text-align: center;
    font-size: 12px;
    color: #1E2028;
    min-height: 20px;
}
QProgressBar::chunk {
    background-color: #2563EB;
    border-radius: 4px;
}

/* ===== 文本输出区 ===== */
QTextEdit {
    border: 1px solid #E2E5EA;
    border-radius: 6px;
    background-color: #1E1E1E;
    color: #D4D4D4;
    padding: 8px;
    font-family: "Consolas", "Courier New", monospace;
    font-size: 12px;
}

/* ===== 标签 ===== */
QLabel {
    color: #1E2028;
    padding: 2px 0;
    font-size: 13px;
}
QLabel#device_count {
    font-weight: bold;
    padding: 4px;
}
QLabel#stats_label {
    font-weight: bold;
    font-size: 14px;
}
QLabel#device_label {
    font-weight: bold;
}
QLabel#status_label {
    color: #6B7280;
}

/* ===== 状态栏 ===== */
QStatusBar {
    background-color: #FFFFFF;
    border-top: 1px solid #E2E5EA;
    color: #6B7280;
    font-size: 12px;
}

/* ===== 分割器 ===== */
QSplitter::handle {
    background-color: #E2E5EA;
    width: 2px;
}

/* ===== 滚动条 ===== */
QScrollBar:vertical {
    background: #F8F9FB;
    width: 10px;
    border: none;
    border-radius: 5px;
}
QScrollBar::handle:vertical {
    background: #CBD5E1;
    border-radius: 5px;
    min-height: 30px;
}
QScrollBar::handle:vertical:hover {
    background: #94A3B8;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0px;
}
QScrollBar:horizontal {
    background: #F8F9FB;
    height: 10px;
    border: none;
    border-radius: 5px;
}
QScrollBar::handle:horizontal {
    background: #CBD5E1;
    border-radius: 5px;
    min-width: 30px;
}
QScrollBar::handle:horizontal:hover {
    background: #94A3B8;
}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
    width: 0px;
}

/* ===== 标签页（QTabWidget） ===== */
QTabWidget::pane {
    border: none;
    background-color: #F8F9FB;
    top: 6px;
    padding-top: 8px;
}
QTabBar::tab {
    background-color: #F1F5F9;
    color: #6B7280;
    border: none;
    padding: 6px 24px;
    margin-right: 3px;
    font-size: 14px;
    font-weight: 500;
    border-top-left-radius: 10px;
    border-top-right-radius: 10px;
    min-height: 30px;
}
QTabBar::tab:selected {
    background-color: #FFFFFF;
    color: #2563EB;
    font-weight: 600;
}
QTabBar::tab:hover:!selected {
    background-color: #E2E8F0;
    color: #1E2028;
}
QTabBar {
    background-color: transparent;
    qproperty-drawBase: 0;
}

/* ===== 标签（移入 QSS 的 inline 样式） ===== */
QLabel#ssh_key_label {
    color: #6B7280;
    font-size: 12px;
}
QLabel#ssh_key_label_active {
    color: #2563EB;
    font-size: 12px;
}
QLabel#config_error_label {
    background-color: #FEE2E2;
    color: #DC2626;
    padding: 8px 12px;
    border-radius: 6px;
    font-weight: 600;
}

/* ===== QMessageBox ===== */
QMessageBox {
    background-color: #FFFFFF;
}
QMessageBox QLabel {
    color: #1E2028;
    font-size: 13px;
}
QMessageBox QPushButton {
    background-color: #2563EB;
    color: white;
    padding: 6px 24px;
    border-radius: 6px;
    min-width: 60px;
}
QMessageBox QPushButton:hover {
    background-color: #1D4ED8;
}
"""


def main():
    """应用程序入口"""
    parser = argparse.ArgumentParser(description=APP_NAME)
    parser.add_argument("--config", "-c", help="自定义命令配置文件路径")
    args = parser.parse_args()

    config_path = Path(args.config) if args.config else get_default_config_path()
    if not config_path.exists():
        print(f"[ERROR] 配置文件不存在: {config_path}")
        print("请确保 config 目录中的巡检模板存在，或使用 --config 指定路径")
        input("按回车键退出...")
        sys.exit(1)

    print(f"[OK] 使用配置文件: {config_path}")
    print(f"[OK] {APP_NAME} v{__version__}")

    app = QApplication(sys.argv)
    app.setApplicationName(f"{APP_NAME} v{__version__}")
    app.setApplicationVersion(__version__)
    app.setStyle("Fusion")

    # 设置全局统一 QSS 样式
    app.setStyleSheet(GLOBAL_QSS)

    window = ToolboxWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
