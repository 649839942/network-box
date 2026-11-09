"""
巡检执行标签页 — 命令选择 + 执行控制
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox,
    QPushButton, QTableWidget, QTableWidgetItem, QHeaderView,
    QCheckBox, QAbstractItemView, QProgressBar,
    QLabel, QTextEdit, QComboBox
)
from PySide6.QtGui import QFont

from core.config_loader import load_commands_yaml, get_commands_by_group, get_command_config_path


COL_CHECK = 0
COL_GROUP = 1
COL_CMD = 2
COL_NOTE = 3


class InspectionPanel(QWidget):
    """巡检执行标签页 — 命令选择、执行、进度展示"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.commands = []  # 全部命令列表
        self.setup_ui()
        self.load_command_config()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(8, 4, 8, 8)

        # ========== 配置加载错误提示（默认隐藏） ==========
        self.config_error_label = QLabel()
        self.config_error_label.setObjectName("config_error_label")
        self.config_error_label.setWordWrap(True)
        self.config_error_label.hide()
        layout.addWidget(self.config_error_label)

        # ========== 命令选择区 ==========
        self.cmd_group = QGroupBox("选 择 巡 检 命 令")
        self.cmd_group.setObjectName("cmd_group")
        cmd_layout = QVBoxLayout()

        template_row = QHBoxLayout()
        template_row.addWidget(QLabel("巡检模板:"))
        self.template_combo = QComboBox()
        self.template_combo.addItem("华为 VRP", "huawei")
        self.template_combo.addItem("新华三 Comware", "h3c")
        self.template_combo.addItem("思科 IOS", "cisco")
        self.template_combo.currentIndexChanged.connect(self.load_command_config)
        template_row.addWidget(self.template_combo)

        self.btn_reload_config = QPushButton("重新加载配置")
        self.btn_reload_config.setObjectName("btn_tool")
        self.btn_reload_config.clicked.connect(self.load_command_config)
        template_row.addWidget(self.btn_reload_config)
        template_row.addStretch()
        cmd_layout.addLayout(template_row)

        self.cmd_table = QTableWidget()
        self.cmd_table.setColumnCount(4)
        self.cmd_table.setHorizontalHeaderLabels(["", "命令组", "具体命令", "命令作用"])

        # 表格行为
        self.cmd_table.setShowGrid(True)
        self.cmd_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.cmd_table.setSelectionMode(QAbstractItemView.NoSelection)
        self.cmd_table.setAlternatingRowColors(True)
        self.cmd_table.verticalHeader().setVisible(False)
        self.cmd_table.setEditTriggers(QAbstractItemView.NoEditTriggers)

        # 列宽（响应式）
        self.cmd_table.setColumnWidth(COL_CHECK, 40)
        header = self.cmd_table.horizontalHeader()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(COL_GROUP, QHeaderView.Fixed)
        self.cmd_table.setColumnWidth(COL_GROUP, 130)
        header.setSectionResizeMode(COL_CMD, QHeaderView.Stretch)
        header.setSectionResizeMode(COL_NOTE, QHeaderView.Stretch)

        cmd_layout.addWidget(self.cmd_table)

        # 全选/取消全选
        btn_row = QHBoxLayout()
        self.btn_select_all = QPushButton("全选")
        self.btn_select_all.setObjectName("btn_select_all")
        self.btn_select_all.clicked.connect(self.select_all)
        btn_row.addWidget(self.btn_select_all)

        self.btn_clear_all = QPushButton("取消全选")
        self.btn_clear_all.setObjectName("btn_clear_all")
        self.btn_clear_all.clicked.connect(self.deselect_all)
        btn_row.addWidget(self.btn_clear_all)

        btn_row.addStretch()
        cmd_layout.addLayout(btn_row)

        self.cmd_group.setLayout(cmd_layout)
        layout.addWidget(self.cmd_group)

        # ========== 执行控制区 ==========
        control_group = QGroupBox("执行控制")
        control_layout = QVBoxLayout()

        # 进度条
        progress_row = QHBoxLayout()
        progress_row.addWidget(QLabel("执行进度:"))
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setFixedHeight(22)
        progress_row.addWidget(self.progress_bar)
        control_layout.addLayout(progress_row)

        # 设备指示
        device_row = QHBoxLayout()
        self.device_label = QLabel("当前设备: -- (0/0)")
        self.device_label.setObjectName("device_label")
        device_row.addWidget(self.device_label)

        self.device_status = QLabel("等待开始...")
        self.device_status.setObjectName("status_label")
        device_row.addWidget(self.device_status)
        device_row.addStretch()
        control_layout.addLayout(device_row)

        # 日志
        self.log_output = QTextEdit()
        self.log_output.setReadOnly(True)
        self.log_output.setFont(QFont("Consolas", 10))
        self.log_output.setMaximumHeight(120)
        control_layout.addWidget(self.log_output)

        # 按钮行
        action_row = QHBoxLayout()
        action_row.addStretch()

        self.btn_start = QPushButton("🚀 开始巡检")
        self.btn_start.setObjectName("start_button")
        self.btn_start.setFixedSize(140, 40)
        action_row.addWidget(self.btn_start)

        self.btn_stop = QPushButton("⏹ 停止")
        self.btn_stop.setObjectName("clear_button")
        self.btn_stop.setFixedSize(100, 40)
        self.btn_stop.setEnabled(False)
        action_row.addWidget(self.btn_stop)

        control_layout.addLayout(action_row)
        control_group.setLayout(control_layout)
        layout.addWidget(control_group)
        layout.addSpacing(12)

    # ==================== 命令配置 ====================

    def load_command_config(self, *_args):
        """加载命令配置"""
        self.config_error_label.hide()
        self.commands = []
        self.cmd_table.setRowCount(0)
        try:
            config_path = get_command_config_path(self.template_combo.currentData())
            self.btn_reload_config.setToolTip(
                f"当前配置文件：\n{config_path}\n修改 YAML 后点击此按钮重新加载"
            )
            if not config_path.exists():
                msg = f"⚠️ 配置文件不存在: {config_path}"
                self.config_error_label.setText(msg)
                self.config_error_label.show()
                print(f"[ERROR] {msg}")
                return

            config = load_commands_yaml(str(config_path))
            self.commands = get_commands_by_group(config)

            self.cmd_table.setRowCount(len(self.commands))
            for row, cmd in enumerate(self.commands):
                self.cmd_table.setRowHeight(row, 40)

                # 第0列: 复选框
                cb = QCheckBox()
                cb.setChecked(True)
                self.cmd_table.setCellWidget(row, COL_CHECK, cb)

                # 第1列: 命令组
                item_group = QTableWidgetItem(cmd["group"])
                self.cmd_table.setItem(row, COL_GROUP, item_group)

                # 第2列: 具体命令
                item_cmd = QTableWidgetItem(cmd["command"])
                self.cmd_table.setItem(row, COL_CMD, item_cmd)

                # 第3列: 命令作用
                item_note = QTableWidgetItem(cmd.get("note", ""))
                self.cmd_table.setItem(row, COL_NOTE, item_note)

            print(f"[OK] 已加载 {len(self.commands)} 条巡检命令")
        except ValueError as e:
            self.config_error_label.setText(f"⚠️ {e}")
            self.config_error_label.show()
            print(f"[ERROR] {e}")
        except Exception as e:
            self.config_error_label.setText(f"⚠️ 加载命令配置失败: {str(e)}")
            self.config_error_label.show()
            print(f"[ERROR] 加载命令配置失败: {e}")

    def select_all(self):
        """全选"""
        for row in range(self.cmd_table.rowCount()):
            cb = self.cmd_table.cellWidget(row, COL_CHECK)
            if cb:
                cb.setChecked(True)

    def deselect_all(self):
        """取消全选"""
        for row in range(self.cmd_table.rowCount()):
            cb = self.cmd_table.cellWidget(row, COL_CHECK)
            if cb:
                cb.setChecked(False)

    def get_selected_commands(self) -> list:
        """获取勾选的命令列表"""
        commands = []
        for row in range(self.cmd_table.rowCount()):
            cb = self.cmd_table.cellWidget(row, COL_CHECK)
            if cb and cb.isChecked():
                commands.append({
                    "group": self.cmd_table.item(row, COL_GROUP).text(),
                    "command": self.cmd_table.item(row, COL_CMD).text(),
                })
        return commands

    def get_selected_template(self) -> str:
        """返回当前巡检模板对应的厂商标识。"""
        return self.template_combo.currentData()

    # ==================== 执行控制 ====================

    def set_running_state(self, running: bool):
        """切换运行状态"""
        self.btn_start.setEnabled(not running)
        self.btn_stop.setEnabled(running)
        self.cmd_table.setEnabled(not running)
        self.template_combo.setEnabled(not running)
        self.btn_reload_config.setEnabled(not running)
        self.btn_select_all.setEnabled(not running)
        self.btn_clear_all.setEnabled(not running)
        if not running:
            self.device_status.setText("已完成" if self.progress_bar.value() > 0 else "等待开始...")

    # ==================== 进度更新 ====================

    def update_device_progress(self, device_ip: str, current: int, total: int):
        """更新当前设备进度"""
        self.device_label.setText(f"当前设备: {device_ip} ({current}/{total})")
        self.device_status.setText(f"正在巡检 {device_ip}...")

    def update_command_progress(self, current: int, total: int):
        """更新命令执行进度"""
        self.progress_bar.setMaximum(total)
        self.progress_bar.setValue(current)

    def log(self, message: str):
        """追加日志"""
        self.log_output.append(message)
        scrollbar = self.log_output.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def reset(self):
        """重置到初始状态"""
        self.progress_bar.setValue(0)
        self.device_label.setText("当前设备: -- (0/0)")
        self.device_status.setText("等待开始...")
        self.log_output.clear()
        self.config_error_label.hide()
