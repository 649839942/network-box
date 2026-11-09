"""交换机巡检工具主窗口 - 左侧工具导航 + 右侧工具面板。"""
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QStackedWidget,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from core.executor_async import BatchInspector
from core.netmiko_utils import vendor_from_device_type
from core.registry import build_panels, load_tool_registry

APP_NAME = "交换机巡检工具"
__version__ = "1.2.1"


class ToolboxWindow(QMainWindow):
    """工具箱壳：由 config/tools.yaml 驱动导航和工具页面。"""

    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"{APP_NAME} v{__version__}")
        self.setMinimumSize(1100, 700)

        self.batch_worker = None
        self.registry = load_tool_registry()
        self.panels = build_panels(self.registry)
        self._stack_index = {}

        self.setup_ui()
        self._wire_coordinating_tools()
        self.statusBar().showMessage("就绪")

    def setup_ui(self):
        central = QWidget()
        root_layout = QHBoxLayout(central)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        # 左侧导航
        nav_panel = QWidget()
        nav_panel.setFixedWidth(230)
        nav_panel.setStyleSheet(
            "background-color: #FFFFFF; border-right: 1px solid #E2E5EA;"
        )
        nav_layout = QVBoxLayout(nav_panel)
        nav_layout.setContentsMargins(12, 16, 12, 12)
        nav_layout.setSpacing(8)

        title_label = QLabel(APP_NAME)
        title_label.setStyleSheet(
            "font-size: 16px; font-weight: 600; color: #1E2028;"
        )
        nav_layout.addWidget(title_label)

        self.nav_tree = QTreeWidget()
        self.nav_tree.setHeaderHidden(True)
        self.nav_tree.setIndentation(14)
        self.nav_tree.setExpandsOnDoubleClick(False)
        self.nav_tree.setStyleSheet(
            """
            QTreeWidget {
                background: transparent;
                border: none;
                outline: none;
            }
            QTreeWidget::item {
                height: 38px;
                padding-left: 8px;
                color: #1E293B;
                font-size: 13px;
                border-radius: 6px;
            }
            QTreeWidget::item:hover {
                background-color: #EFF6FF;
                color: #2563EB;
            }
            QTreeWidget::item:selected {
                background-color: #2563EB;
                color: #FFFFFF;
                font-weight: 600;
                border-radius: 6px;
            }
            QTreeWidget::branch {
                background: transparent;
            }
            """
        )
        nav_layout.addWidget(self.nav_tree, 1)
        root_layout.addWidget(nav_panel)

        # 右侧工具页面
        self.stack = QStackedWidget()
        root_layout.addWidget(self.stack, 1)
        self.setCentralWidget(central)

        self._build_navigation()

    def _build_navigation(self):
        for category in self.registry.get("categories", []):
            category_name = category.get("name", "未分类")
            cat_item = QTreeWidgetItem([f"▼ {category_name}"])
            cat_item.setData(0, Qt.UserRole + 1, category_name)
            cat_item.setFlags(cat_item.flags() & ~Qt.ItemIsSelectable)
            cat_item.setExpanded(True)
            cat_item.setToolTip(0, "单击收起或展开")
            cat_font = QFont()
            cat_font.setBold(True)
            cat_item.setFont(0, cat_font)
            cat_item.setForeground(0, QColor("#64748B"))
            self.nav_tree.addTopLevelItem(cat_item)

            for tool in category.get("tools", []):
                tool_id = tool.get("id")
                panel = self.panels.get(tool_id)
                if panel is None:
                    continue
                tool_item = QTreeWidgetItem([tool.get("name", tool_id)])
                tool_item.setData(0, Qt.UserRole, tool_id)
                tool_item.setToolTip(0, tool.get("description", ""))
                cat_item.addChild(tool_item)
                self._stack_index[tool_id] = self.stack.addWidget(panel)

        self.nav_tree.itemClicked.connect(self.on_tool_selected)
        self.nav_tree.itemExpanded.connect(
            lambda item: self._update_category_arrow(item, True)
        )
        self.nav_tree.itemCollapsed.connect(
            lambda item: self._update_category_arrow(item, False)
        )
        first = self.nav_tree.topLevelItem(0)
        if first and first.childCount():
            self.nav_tree.setCurrentItem(first.child(0))
            self.on_tool_selected(first.child(0), 0)

    def _update_category_arrow(self, item, expanded: bool):
        category_name = item.data(0, Qt.UserRole + 1)
        if category_name:
            item.setText(0, f"{'▼' if expanded else '▶'} {category_name}")

    def on_tool_selected(self, item, column):
        tool_id = item.data(0, Qt.UserRole)
        if not tool_id:
            if item.data(0, Qt.UserRole + 1):
                item.setExpanded(not item.isExpanded())
            return
        index = self._stack_index.get(tool_id)
        if index is not None:
            self.stack.setCurrentIndex(index)

    def _select_tool(self, tool_id: str):
        index = self._stack_index.get(tool_id)
        if index is not None:
            self.stack.setCurrentIndex(index)

    def _wire_coordinating_tools(self):
        inspection = self.panels.get("batch_inspection")
        if inspection:
            inspection.btn_start.clicked.connect(self.start_batch_inspection)
            inspection.btn_stop.clicked.connect(self.stop_batch_inspection)

        result = self.panels.get("result_view")
        if result:
            result.retry_requested.connect(self.on_retry_failed_devices)

        config_panel = self.panels.get("config_compare")
        if config_panel:
            config_panel.save_requested.connect(self.start_config_backup)
            config_panel.backup_finished.connect(self.on_config_backup_finished)

    # ==================== 配置保存编排 ====================

    def start_config_backup(self):
        device_panel = self.panels.get("device_manager")
        config_panel = self.panels.get("config_compare")
        if not (device_panel and config_panel):
            return

        devices = device_panel.get_selected_devices()
        if any(self._device_vendor(device) is None for device in devices):
            QMessageBox.warning(
                self,
                "设备厂商未识别",
                "存在尚未识别厂商的设备，请先在「设备管理」中测试连接。",
            )
            self._select_tool("device_manager")
            return
        config_panel.start_backup(devices)
        if devices:
            self.statusBar().showMessage(f"正在保存 {len(devices)} 台设备配置...")

    def on_config_backup_finished(self, all_success: bool, summary: str):
        self.statusBar().showMessage(summary)

    # ==================== 批量巡检编排 ====================

    def _connect_worker_signals(self):
        inspection = self.panels["batch_inspection"]
        result = self.panels["result_view"]
        self.batch_worker.current_device.connect(inspection.update_device_progress)
        self.batch_worker.device_log.connect(inspection.log)
        self.batch_worker.progress_signal.connect(inspection.update_command_progress)
        self.batch_worker.command_result.connect(result.add_device_result)
        self.batch_worker.device_finished.connect(self._on_device_finished)
        self.batch_worker.batch_finished.connect(self._on_batch_finished)

    def _prepare_worker(self, devices, commands, log_msg, status_msg):
        if self.batch_worker and self.batch_worker.isRunning():
            self.batch_worker.stop()
            if not self.batch_worker.wait(5000):
                self.batch_worker.terminate()
                self.batch_worker.wait(3000)

        self.batch_worker = BatchInspector(devices, commands)
        self._connect_worker_signals()
        inspection = self.panels["batch_inspection"]
        inspection.reset()
        inspection.set_running_state(True)
        inspection.log(log_msg)
        self.statusBar().showMessage(status_msg)
        self._select_tool("batch_inspection")
        self.batch_worker.start()

    @staticmethod
    def _device_vendor(device: dict) -> str:
        return vendor_from_device_type(device.get("device_type", ""))

    def _get_inspection_commands(self, devices: list):
        vendors = {self._device_vendor(device) for device in devices}
        if None in vendors:
            QMessageBox.warning(
                self,
                "设备厂商未识别",
                "存在尚未识别厂商的设备，请先在「设备管理」中测试连接。",
            )
            self._select_tool("device_manager")
            return None
        if len(vendors) != 1:
            QMessageBox.warning(
                self,
                "设备厂商不一致",
                "一次批量巡检只能选择同一厂商的设备，请分别巡检华为、新华三或思科设备。",
            )
            return None

        inspection = self.panels["batch_inspection"]
        device_vendor = next(iter(vendors))
        template_vendor = inspection.get_selected_template()
        if device_vendor != template_vendor:
            template_names = {
                "huawei": "华为 VRP",
                "h3c": "新华三 Comware",
                "cisco": "思科 IOS",
            }
            device_names = {"huawei": "华为", "h3c": "新华三", "cisco": "思科"}
            QMessageBox.warning(
                self,
                "巡检模板不匹配",
                f"当前设备为{device_names[device_vendor]}，请选择"
                f"{template_names.get(device_vendor, '对应厂商')}巡检模板。",
            )
            return None

        commands = inspection.get_selected_commands()
        if not commands:
            QMessageBox.warning(self, "未选择命令", "请至少勾选一条巡检命令")
            return None
        return commands

    def start_batch_inspection(self):
        device_panel = self.panels.get("device_manager")
        inspection = self.panels.get("batch_inspection")
        result = self.panels.get("result_view")
        if not (device_panel and inspection and result):
            return

        devices = device_panel.get_selected_devices()
        if not devices:
            QMessageBox.warning(self, "无设备", "请先在「设备管理」中勾选要巡检的设备")
            self._select_tool("device_manager")
            return

        commands = self._get_inspection_commands(devices)
        if commands is None:
            return

        result.clear_results()
        self._prepare_worker(
            devices,
            commands,
            f"🚀 开始批量巡检...\n  设备数: {len(devices)}, 命令数: {len(commands)}",
            f"巡检中: {len(devices)} 台设备...",
        )

    def stop_batch_inspection(self):
        if self.batch_worker and self.batch_worker.isRunning():
            self.batch_worker.stop()
            inspection = self.panels["batch_inspection"]
            inspection.log("⏹ 正在停止巡检...")

    def _on_device_finished(self, device_ip: str, success: bool):
        status = "✅ 完成" if success else "❌ 失败"
        inspection = self.panels["batch_inspection"]
        inspection.log(f"  → 设备 {device_ip}: {status}")

    def _on_batch_finished(self, all_success: bool, summary: str):
        inspection = self.panels["batch_inspection"]
        result = self.panels["result_view"]
        inspection.set_running_state(False)
        inspection.log(f"\n{'='*50}")
        inspection.log(summary)
        result.update_stats()

        if all_success:
            self.statusBar().showMessage("批量巡检完成")
            QMessageBox.information(self, "巡检完成", summary)
        else:
            self.statusBar().showMessage("巡检完成（部分失败）")
            QMessageBox.warning(
                self,
                "巡检完成",
                summary + "\n\n部分设备巡检失败，请在结果页查看详情",
            )
        self._select_tool("result_view")

    def on_retry_failed_devices(self, failed_ips: list):
        device_panel = self.panels.get("device_manager")
        inspection = self.panels.get("batch_inspection")
        result = self.panels.get("result_view")
        if not (device_panel and inspection and result):
            return

        all_devices = device_panel.get_all_devices()
        retry_devices = [d for d in all_devices if d.get("host") in failed_ips]
        if not retry_devices:
            return

        commands = self._get_inspection_commands(retry_devices)
        if commands is None:
            return

        result.remove_device_results(failed_ips)
        self._prepare_worker(
            retry_devices,
            commands,
            f"🔄 重试 {len(retry_devices)} 台失败设备...",
            f"重试中: {len(retry_devices)} 台设备...",
        )

    # ==================== 关闭事件 ====================

    def closeEvent(self, event):
        if self.batch_worker and self.batch_worker.isRunning():
            self.batch_worker.stop()
            if not self.batch_worker.wait(5000):
                self.batch_worker.terminate()
                self.batch_worker.wait(3000)

        snmp_panel = self.panels.get("snmp_test")
        if snmp_panel:
            snmp_panel.shutdown()
        cmd_panel = self.panels.get("cmd_terminal")
        if cmd_panel:
            cmd_panel.shutdown()
        config_panel = self.panels.get("config_compare")
        if config_panel:
            config_panel.shutdown()
        event.accept()
