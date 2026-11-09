"""
设备管理标签页 — 多设备表格管理
"""
import csv
from pathlib import Path

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTableWidget, QTableWidgetItem,
    QPushButton, QHeaderView, QComboBox, QCheckBox, QMessageBox, QFileDialog,
    QLabel, QAbstractItemView, QLineEdit, QStyledItemDelegate
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor

from core.executor_async import ConnectionTestWorker
from core.netmiko_utils import VENDOR_NAMES


class OptionDelegate(QStyledItemDelegate):
    """使用固定选项的下拉代理编辑器。"""

    def __init__(self, options, default_value, parent=None):
        super().__init__(parent)
        self.options = options
        self.default_value = default_value

    def createEditor(self, parent, option, index):
        combo = QComboBox(parent)
        combo.addItems(self.options)
        return combo

    def setEditorData(self, editor, index):
        value = index.data(Qt.DisplayRole) or self.default_value
        editor.setCurrentText(value)

    def setModelData(self, editor, model, index):
        model.setData(index, editor.currentText(), Qt.EditRole)

    def updateEditorGeometry(self, editor, option, index):
        editor.setGeometry(option.rect)


class DeviceManagerPanel(QWidget):
    """设备管理标签页 — 表格化管理多台设备"""

    COL_CHECK = 0      # 复选框
    COL_IP = 1         # IP地址
    COL_USER = 2       # 用户名
    COL_PWD = 3        # 密码
    COL_PROTO = 4      # 连接方式 (下拉)
    COL_TYPE = 5       # 设备类型 (华为/新华三/思科)
    COL_STATUS = 6     # 连接状态 (只读)
    COL_COUNT = 7

    HEADERS = ["", "IP地址", "用户名", "密码", "连接方式", "设备类型", "连接状态"]

    # 列配置: (resize_mode, width_or_None)
    _COL_CONFIG = [
        (QHeaderView.Fixed, 36),      # COL_CHECK
        (QHeaderView.Stretch, None),  # COL_IP
        (QHeaderView.Stretch, None),  # COL_USER
        (QHeaderView.Stretch, None),  # COL_PWD
        (QHeaderView.Fixed, 90),      # COL_PROTO
        (QHeaderView.Fixed, 100),     # COL_TYPE
        (QHeaderView.Fixed, 100),     # COL_STATUS
    ]

    def __init__(self, parent=None):
        super().__init__(parent)
        self._testing = False  # 是否正在测试连接
        self._test_pending = 0
        self._test_total = 0
        self._unrecognized_count = 0
        self._workers = []     # 保持连接测试线程引用
        self._ssh_key_path = ""  # SSH 密钥文件路径
        self.setup_ui()
        self.add_row()  # 初始空行

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(4)
        layout.setContentsMargins(8, 4, 8, 8)

        # ---- 工具栏 ----
        toolbar = QHBoxLayout()
        toolbar.setSpacing(6)

        self.btn_add = QPushButton("＋ 添加设备")
        self.btn_add.setObjectName("btn_tool")
        self.btn_add.clicked.connect(self.add_row)
        toolbar.addWidget(self.btn_add)

        self.btn_delete = QPushButton("－ 删除选中")
        self.btn_delete.setObjectName("btn_tool")
        self.btn_delete.clicked.connect(self.delete_selected)
        toolbar.addWidget(self.btn_delete)

        # 全选/取消全选
        self.btn_select_all = QPushButton("全选")
        self.btn_select_all.setObjectName("btn_select_all")
        self.btn_select_all.clicked.connect(self.select_all)
        toolbar.addWidget(self.btn_select_all)

        self.btn_clear_all = QPushButton("取消全选")
        self.btn_clear_all.setObjectName("btn_clear_all")
        self.btn_clear_all.clicked.connect(self.deselect_all)
        toolbar.addWidget(self.btn_clear_all)

        toolbar.addStretch(1)

        # SSH 密钥文件选择（与导入导出合并到右侧区域）
        self.btn_ssh_key = QPushButton("🔑 SSH密钥")
        self.btn_ssh_key.setObjectName("btn_tool")
        self.btn_ssh_key.clicked.connect(self._select_ssh_key)
        toolbar.addWidget(self.btn_ssh_key)

        self.ssh_key_label = QLabel("未选择密钥文件")
        self.ssh_key_label.setObjectName("ssh_key_label")
        toolbar.addWidget(self.ssh_key_label)

        self.btn_import = QPushButton("📂 导入CSV")
        self.btn_import.setObjectName("btn_tool")
        self.btn_import.clicked.connect(self.import_csv)
        toolbar.addWidget(self.btn_import)

        self.btn_export_template = QPushButton("📄 导出模板")
        self.btn_export_template.setObjectName("btn_tool")
        self.btn_export_template.clicked.connect(self.export_template)
        toolbar.addWidget(self.btn_export_template)

        layout.addLayout(toolbar)

        # ---- 设备表格 ----
        self.table = QTableWidget()
        self.table.setColumnCount(self.COL_COUNT)
        self.table.setHorizontalHeaderLabels(self.HEADERS)

        # 表格行为设置
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.AllEditTriggers)

        # 下拉代理编辑器避免选项被表格行高裁剪
        self._proto_delegate = OptionDelegate(["SSH", "Telnet"], "SSH", self.table)
        self.table.setItemDelegateForColumn(self.COL_PROTO, self._proto_delegate)
        self._type_delegate = OptionDelegate(
            ["自动识别", "华为", "新华三", "思科"],
            "自动识别",
            self.table,
        )
        self.table.setItemDelegateForColumn(self.COL_TYPE, self._type_delegate)

        # 列宽（数据驱动）
        header = self.table.horizontalHeader()
        header.setStretchLastSection(False)
        for col, (mode, width) in enumerate(self._COL_CONFIG):
            header.setSectionResizeMode(col, mode)
            if width is not None:
                self.table.setColumnWidth(col, width)

        layout.addWidget(self.table)

        # ---- 底部状态栏 ----
        bottom_layout = QHBoxLayout()

        self.btn_test_all = QPushButton("🔌 测试所有连接")
        self.btn_test_all.setObjectName("connect_button")
        self.btn_test_all.clicked.connect(self.test_all_connections)
        bottom_layout.addWidget(self.btn_test_all)

        bottom_layout.addStretch(1)

        self.device_count_label = QLabel("设备数: 0")
        self.device_count_label.setObjectName("device_count")
        bottom_layout.addWidget(self.device_count_label)

        layout.addLayout(bottom_layout)
        layout.addSpacing(12)

    # ==================== 行操作 ====================

    def add_row(self, data: dict = None):
        """添加一行，可选预填数据"""
        row = self.table.rowCount()
        self.table.insertRow(row)
        self.table.setRowHeight(row, 38)

        # 第0列: 复选框
        cb = QCheckBox()
        cb.setChecked(True)
        self.table.setCellWidget(row, self.COL_CHECK, cb)

        # 第1列: IP地址（居中）
        ip_text = (data or {}).get("ip", "")
        ip_item = QTableWidgetItem(ip_text)
        ip_item.setTextAlignment(Qt.AlignCenter)
        self.table.setItem(row, self.COL_IP, ip_item)

        # 第2列: 用户名（居中）
        user_text = (data or {}).get("username", "")
        user_item = QTableWidgetItem(user_text)
        user_item.setTextAlignment(Qt.AlignCenter)
        self.table.setItem(row, self.COL_USER, user_item)

        # 第3列: 密码（掩码显示 + 显示切换按钮）
        pwd_text = (data or {}).get("password", "")
        pwd_widget = QWidget()
        pwd_layout = QHBoxLayout(pwd_widget)
        pwd_layout.setContentsMargins(4, 0, 4, 0)
        pwd_layout.setSpacing(2)

        pwd_input = QLineEdit(pwd_text)
        pwd_input.setEchoMode(QLineEdit.Password)
        pwd_input.setPlaceholderText("密码")
        pwd_input.setAlignment(Qt.AlignCenter)
        pwd_layout.addWidget(pwd_input)

        pwd_toggle = QPushButton("◉")
        pwd_toggle.setObjectName("pwd_toggle")
        pwd_toggle.setFixedSize(24, 24)
        pwd_toggle.setToolTip("显示/隐藏密码")
        pwd_toggle.setCheckable(True)
        pwd_toggle.toggled.connect(
            lambda checked, le=pwd_input: le.setEchoMode(
                QLineEdit.Normal if checked else QLineEdit.Password
            )
        )
        pwd_layout.addWidget(pwd_toggle)

        self.table.setCellWidget(row, self.COL_PWD, pwd_widget)

        # 第4列: 连接方式 (双击弹出下拉选择)
        proto_text = (data or {}).get("protocol", "SSH")
        proto_item = QTableWidgetItem(proto_text)
        proto_item.setTextAlignment(Qt.AlignCenter)
        self.table.setItem(row, self.COL_PROTO, proto_item)

        # 第5列: 设备类型 (可双击选择或由连接测试自动识别)
        type_text = self._display_device_type((data or {}).get("device_type", "auto"))
        type_item = QTableWidgetItem(type_text)
        type_item.setTextAlignment(Qt.AlignCenter)
        type_item.setForeground(QColor("#1E2028"))
        self.table.setItem(row, self.COL_TYPE, type_item)

        # 第6列: 连接状态 (只读，居中)
        status_item = QTableWidgetItem("未测试")
        status_item.setFlags(status_item.flags() & ~Qt.ItemIsEditable)
        status_item.setForeground(QColor("#6B7280"))
        status_item.setTextAlignment(Qt.AlignCenter)
        self.table.setItem(row, self.COL_STATUS, status_item)

        self._update_count()

    def delete_selected(self):
        """删除选中的行"""
        if self._testing:
            QMessageBox.warning(self, "提示", "测试中无法删除设备")
            return
        rows = set()
        for item in self.table.selectedItems():
            rows.add(item.row())
        for row in sorted(rows, reverse=True):
            self.table.removeRow(row)
        self._update_count()

    def select_all(self):
        """全选所有设备"""
        for row in range(self.table.rowCount()):
            cb = self.table.cellWidget(row, self.COL_CHECK)
            if cb:
                cb.setChecked(True)

    def deselect_all(self):
        """取消全选所有设备"""
        for row in range(self.table.rowCount()):
            cb = self.table.cellWidget(row, self.COL_CHECK)
            if cb:
                cb.setChecked(False)

    def _get_checked_rows(self):
        """获取所有勾选的行号"""
        checked = []
        for row in range(self.table.rowCount()):
            cb = self.table.cellWidget(row, self.COL_CHECK)
            if cb and cb.isChecked():
                checked.append(row)
        return checked

    def _get_filled_rows(self):
        """获取所有已填写IP的行号"""
        filled = []
        for row in range(self.table.rowCount()):
            ip_item = self.table.item(row, self.COL_IP)
            if ip_item and ip_item.text().strip():
                filled.append(row)
        return filled

    # ==================== CSV 导入导出 ====================

    def import_csv(self):
        """从CSV文件导入设备列表"""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "导入设备列表", "", "CSV文件 (*.csv);;所有文件 (*)"
        )
        if not file_path:
            return

        try:
            with open(file_path, "r", encoding="utf-8-sig") as f:
                reader = csv.DictReader(f)
                if not reader.fieldnames:
                    raise ValueError("CSV 文件为空")
                # 列名大小写不敏感
                col_map = {name.lower(): name for name in reader.fieldnames}
                count = 0
                for row_data in reader:
                    ip = row_data.get(col_map.get("ip", ""), "").strip()
                    if not ip:
                        continue
                    self.add_row({
                        "ip": ip,
                        "username": row_data.get(col_map.get("username", ""), "").strip(),
                        "password": row_data.get(col_map.get("password", ""), ""),
                        "protocol": row_data.get(col_map.get("protocol", ""), "SSH").strip(),
                        "device_type": row_data.get(col_map.get("devicetype", ""), "").strip(),
                    })
                    count += 1
            QMessageBox.information(self, "导入成功", f"成功导入 {count} 台设备")
        except Exception as e:
            QMessageBox.warning(self, "导入失败", f"读取CSV文件出错:\n{str(e)}")

    def export_template(self):
        """导出CSV模板"""
        file_path, _ = QFileDialog.getSaveFileName(
            self, "导出模板", "设备列表模板.csv", "CSV文件 (*.csv)"
        )
        if not file_path:
            return
        try:
            with open(file_path, "w", encoding="utf-8-sig", newline="") as f:
                writer = csv.writer(f)
                writer.writerow(["IP", "Username", "Password", "Protocol", "DeviceType"])
                writer.writerow(["192.0.2.10", "operator", "", "SSH", "华为"])
                writer.writerow(["192.0.2.11", "operator", "", "Telnet", "思科"])
                writer.writerow(["192.0.2.12", "operator", "", "SSH", "新华三"])
            QMessageBox.information(self, "导出成功", f"模板已导出到:\n{file_path}")
        except Exception as e:
            QMessageBox.warning(self, "导出失败", str(e))

    # ==================== 连接测试 ====================

    def test_all_connections(self):
        """并行测试所有已填写设备的连接"""
        rows = self._get_filled_rows()
        if not rows:
            QMessageBox.warning(self, "无设备", "请先填写设备IP地址")
            return

        if self._testing:
            return

        self._testing = True
        self._workers = []  # 清除旧 worker，新建一批
        self._test_pending = len(rows)
        self._test_total = len(rows)
        self._unrecognized_count = 0
        self.btn_test_all.setEnabled(False)
        self.btn_test_all.setText(f"测试中 0/{len(rows)}...")

        # 将所有设备状态重置
        for row in rows:
            status_item = self.table.item(row, self.COL_STATUS)
            if status_item:
                status_item.setText("测试中...")
                status_item.setForeground(QColor("#2563EB"))
                status_item.setToolTip("")

        # 并行启动所有测试
        for row in rows:
            config = self.get_device_config(row)
            if not config:
                self._test_pending -= 1
                continue

            worker = ConnectionTestWorker(config)
            worker.finished_signal.connect(
                lambda success, msg, vendor, r=row: self._on_test_finished(
                    r, success, msg, vendor
                )
            )
            self._workers.append(worker)
            worker.start()

        # 如果所有行都因为配置无效导致无 worker 启动，立即重置
        if self._test_pending <= 0:
            self._test_cleanup()

    def _test_cleanup(self):
        """连接测试完成，清理状态（保留 worker 引用直到下次测试）"""
        self._testing = False
        self.btn_test_all.setEnabled(True)
        self.btn_test_all.setText("🔌 测试所有连接")
        if self._unrecognized_count:
            QMessageBox.warning(
                self,
                "厂商未识别",
                f"有 {self._unrecognized_count} 台设备已连接，但无法自动识别厂商。\n"
                "请在设备类型列手动选择华为、新华三或思科后重新测试。",
            )
            self._unrecognized_count = 0

    def _on_test_finished(self, row: int, success: bool, message: str, vendor: str):
        """单台测试完成"""
        status_item = self.table.item(row, self.COL_STATUS)
        type_item = self.table.item(row, self.COL_TYPE)
        was_auto = bool(type_item and type_item.text() == "自动识别")
        if status_item:
            if success:
                if was_auto and vendor:
                    type_item.setText(VENDOR_NAMES[vendor])
                    status_item.setText("✓ 已识别")
                else:
                    status_item.setText("✓ 连接成功")
                status_item.setForeground(QColor("#16A34A"))
            else:
                if message.startswith("连接成功，但未能自动识别"):
                    status_item.setText("✗ 未识别")
                    self._unrecognized_count += 1
                else:
                    status_item.setText("✗ 连接失败")
                status_item.setForeground(QColor("#DC2626"))
            status_item.setToolTip(message)

        self._test_pending -= 1
        done = self._test_total - self._test_pending
        self.btn_test_all.setText(f"测试中 ({done}/{self._test_total})...")

        if self._test_pending <= 0:
            self._test_cleanup()

    # ==================== 配置读取 ====================

    def _get_password(self, row: int) -> str:
        """从表格行读取密码"""
        pwd_widget = self.table.cellWidget(row, self.COL_PWD)
        if pwd_widget:
            pwd_input = pwd_widget.findChild(QLineEdit)
            if pwd_input:
                return pwd_input.text()
        return ""

    def _display_device_type(self, value: str) -> str:
        normalized = str(value).strip().lower()
        if normalized in {"", "auto", "autodetect", "autodetect_telnet", "自动识别"}:
            return "自动识别"
        if normalized in {"华为", "huawei", "huawei_telnet", "huawei_vrp", "huawei_vrpv8"}:
            return "华为"
        if normalized in {
            "新华三", "h3c", "h3c_comware", "h3c_comware_ssh",
            "hp_comware", "hp_comware_ssh", "hp_comware_telnet", "comware",
        }:
            return "新华三"
        if normalized in {"思科", "cisco", "cisco_ios", "cisco_ios_telnet"}:
            return "思科"
        return "自动识别"

    def get_device_config(self, row: int) -> dict:
        """从表格行构建设备配置"""
        ip_item = self.table.item(row, self.COL_IP)
        user_item = self.table.item(row, self.COL_USER)

        ip = ip_item.text().strip() if ip_item else ""
        username = user_item.text().strip() if user_item else ""

        if not ip:
            return None

        password = self._get_password(row)

        proto_item = self.table.item(row, self.COL_PROTO)
        is_telnet = proto_item and proto_item.text() == "Telnet"
        type_item = self.table.item(row, self.COL_TYPE)
        device_vendor = type_item.text() if type_item else "自动识别"

        if device_vendor == "自动识别":
            device_type = "autodetect_telnet" if is_telnet else "autodetect"
        elif is_telnet:
            device_type = {
                "新华三": "hp_comware_telnet",
                "思科": "cisco_ios_telnet",
            }.get(device_vendor, "huawei_telnet")
        else:
            device_type = {
                "新华三": "h3c_comware",
                "思科": "cisco_ios",
            }.get(device_vendor, "huawei")

        config = {
            "device_type": device_type,
            "host": ip,
            "username": username,
            "password": password,
            "port": 23 if is_telnet else 22,
            "timeout": 30,
            "global_delay_factor": 1.5,
        }

        # SSH 密钥认证
        if self._ssh_key_path and not is_telnet:
            key_path = Path(self._ssh_key_path)
            if key_path.exists():
                config["use_keys"] = True
                config["ssh_private_key_file"] = str(key_path)

        return config

    def get_selected_devices(self) -> list:
        """获取所有勾选设备的配置列表"""
        devices = []
        for row in self._get_checked_rows():
            config = self.get_device_config(row)
            if config:
                devices.append(config)
        return devices

    def get_all_devices(self) -> list:
        """获取所有已填写设备的配置列表"""
        devices = []
        for row in self._get_filled_rows():
            config = self.get_device_config(row)
            if config:
                devices.append(config)
        return devices

    # ==================== SSH 密钥 ====================

    def _select_ssh_key(self):
        """选择 SSH 密钥文件"""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "选择 SSH 私钥文件", "", "所有文件 (*);;PPK 密钥 (*.ppk);;PEM 密钥 (*.pem)"
        )
        if file_path:
            self._ssh_key_path = file_path
            self.ssh_key_label.setText(Path(file_path).name)
            self.ssh_key_label.setObjectName("ssh_key_label_active")
            self.ssh_key_label.style().unpolish(self.ssh_key_label)
            self.ssh_key_label.style().polish(self.ssh_key_label)

    # ==================== 内部 ====================

    def _update_count(self):
        """更新底部设备计数"""
        filled = len(self._get_filled_rows())
        self.device_count_label.setText(f"设备数: {filled}")

    def get_device_count(self) -> int:
        """获取有效设备数"""
        return len(self._get_filled_rows())
