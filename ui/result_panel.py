"""
巡检结果展示标签页 — 设备→命令组→命令 三级树
"""
import csv
import json
from pathlib import Path

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout,
    QTextEdit, QTreeWidget, QTreeWidgetItem, QPushButton,
    QLabel, QSplitter, QMessageBox, QFileDialog, QHeaderView
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont, QColor


class ResultPanel(QWidget):
    """巡检结果展示 — 设备级树形结构"""

    MAX_OUTPUT_LEN = 50000

    retry_requested = Signal(list)  # 重试请求: 失败设备 IP 列表

    def __init__(self, parent=None):
        super().__init__(parent)
        self.results = {}       # {device_ip: [result_dict, ...]}
        self.device_items = {}  # {device_ip: QTreeWidgetItem}
        self.failed_devices = set()  # 记录失败设备IP
        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(8)
        layout.setContentsMargins(8, 4, 8, 8)

        # ---- 顶部统计 ----
        top_layout = QHBoxLayout()
        self.stats_label = QLabel("统计: 0 台设备, 0 条命令")
        self.stats_label.setObjectName("stats_label")
        top_layout.addWidget(self.stats_label)
        top_layout.addStretch()
        layout.addLayout(top_layout)

        # ---- 分割面板 ----
        splitter = QSplitter(Qt.Horizontal)

        # 左侧：结果树（响应式列宽）
        self.tree_widget = QTreeWidget()
        self.tree_widget.setHeaderLabels(["设备 / 命令组 / 命令", "状态"])
        self.tree_widget.setColumnWidth(0, 300)
        self.tree_widget.setColumnWidth(1, 60)
        header = self.tree_widget.header()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(0, QHeaderView.Stretch)
        header.setSectionResizeMode(1, QHeaderView.Fixed)
        self.tree_widget.setAlternatingRowColors(True)
        self.tree_widget.itemClicked.connect(self.on_tree_item_clicked)
        splitter.addWidget(self.tree_widget)

        # 右侧：输出显示
        self.output_text = QTextEdit()
        self.output_text.setReadOnly(True)
        self.output_text.setFont(QFont("Consolas", 10))
        splitter.addWidget(self.output_text)

        splitter.setSizes([450, 550])
        layout.addWidget(splitter, 1)

        # ---- 底部按钮 ----
        bottom_layout = QHBoxLayout()

        self.btn_retry = QPushButton("🔄 重试失败设备")
        self.btn_retry.setObjectName("btn_tool")
        self.btn_retry.setEnabled(False)
        self.btn_retry.clicked.connect(self.on_retry_clicked)
        bottom_layout.addWidget(self.btn_retry)

        bottom_layout.addStretch()

        self.btn_export = QPushButton("📤 导出结果")
        self.btn_export.setObjectName("btn_tool")
        self.btn_export.clicked.connect(self.export_all_results)
        bottom_layout.addWidget(self.btn_export)

        self.btn_export_log = QPushButton("📋 导出日志")
        self.btn_export_log.setObjectName("btn_tool")
        self.btn_export_log.clicked.connect(self.export_log)
        bottom_layout.addWidget(self.btn_export_log)

        self.btn_clear = QPushButton("🗑️ 清空结果")
        self.btn_clear.setObjectName("clear_button")
        self.btn_clear.setFixedWidth(110)
        self.btn_clear.clicked.connect(self.clear_results)
        bottom_layout.addWidget(self.btn_clear)

        layout.addLayout(bottom_layout)
        layout.addSpacing(12)

    # ==================== 添加结果 ====================

    def add_device_result(self, device_ip: str, result: dict):
        """添加一条设备命令结果"""
        # 记录失败设备
        if not result.get("success", False):
            self.failed_devices.add(device_ip)
        else:
            # 检查该设备是否还有未成功的命令
            device_results = self.results.get(device_ip, [])
            has_failure = any(
                r.get("success") is False
                for r in device_results
            ) or not result.get("success", False)
            if not has_failure and device_ip in self.failed_devices:
                self.failed_devices.discard(device_ip)
        # 存储
        if device_ip not in self.results:
            self.results[device_ip] = []
            self._add_device_node(device_ip)
        self.results[device_ip].append(result)

        # 添加到树
        self._add_result_to_tree(device_ip, result)
        self.update_stats()

    def _add_device_node(self, device_ip: str):
        """添加设备级树节点"""
        item = QTreeWidgetItem()
        item.setText(0, f"📟 {device_ip}")
        item.setFont(0, QFont("Microsoft YaHei", 11, QFont.Bold))
        item.setForeground(0, QColor("#1E2028"))
        item.setData(0, Qt.UserRole, {"type": "device", "device_ip": device_ip})
        self.tree_widget.addTopLevelItem(item)
        item.setExpanded(True)
        self.device_items[device_ip] = item

    def _add_result_to_tree(self, device_ip: str, result: dict):
        """在设备节点下添加一条命令结果"""
        device_item = self.device_items.get(device_ip)
        if not device_item:
            return

        group_name = result.get("group", "未分组")
        success = result.get("success", False)

        # 查找或创建命令组子节点
        group_item = None
        for i in range(device_item.childCount()):
            if device_item.child(i).text(0) == group_name:
                group_item = device_item.child(i)
                break

        if not group_item:
            group_item = QTreeWidgetItem()
            group_item.setText(0, group_name)
            group_item.setFont(0, QFont("Microsoft YaHei", 10))
            group_item.setForeground(0, QColor("#1E2028"))
            group_item.setData(0, Qt.UserRole, {"type": "group", "device_ip": device_ip})
            device_item.addChild(group_item)
            group_item.setExpanded(True)

        # 命令子节点
        cmd_item = QTreeWidgetItem()
        cmd_item.setText(0, f"  {result.get('command', '')}")
        cmd_item.setText(1, "✓" if success else "✗")
        if success:
            cmd_item.setForeground(1, QColor("#16A34A"))
        else:
            cmd_item.setForeground(1, QColor("#DC2626"))
        cmd_item.setData(0, Qt.UserRole, {
            "type": "command",
            "device_ip": device_ip,
            "output": result.get("output", ""),
            "success": success,
        })
        group_item.addChild(cmd_item)

    # ==================== 点击查看 ====================

    def on_tree_item_clicked(self, item, column):
        """点击树节点显示输出"""
        data = item.data(0, Qt.UserRole)
        if not data:
            return

        if data.get("type") == "command":
            output = data.get("output", "")
            self.output_text.setPlainText(output[:self.MAX_OUTPUT_LEN])

        elif data.get("type") == "device":
            # 显示设备汇总
            device_ip = data.get("device_ip", "")
            results = self.results.get(device_ip, [])
            total = len(results)
            success = sum(1 for r in results if r.get("success"))
            summary = (
                f"设备: {device_ip}\n"
                f"状态: {'✅ 全部成功' if success == total else '⚠️ 部分失败'}\n"
                f"命令总数: {total}\n"
                f"成功: {success}\n"
                f"失败: {total - success}\n"
            )
            self.output_text.setPlainText(summary)

        elif data.get("type") == "group":
            self.output_text.setPlainText(f"命令组: {item.text(0)}\n(点击下方具体命令查看输出)")

    # ==================== 统计 ====================

    def update_stats(self):
        """更新统计信息"""
        total_devices = len(self.results)
        total_cmds = sum(len(r) for r in self.results.values())
        success_cmds = sum(
            sum(1 for r in results if r.get("success"))
            for results in self.results.values()
        )
        failed_cmds = total_cmds - success_cmds

        text = f"统计: {total_devices} 台设备, {total_cmds} 条命令"
        if total_cmds > 0:
            text += f" | ✓ {success_cmds}  ✗ {failed_cmds}"

        self.stats_label.setText(text)

        # 更新重试按钮状态
        self.btn_retry.setEnabled(len(self.failed_devices) > 0)
        if self.failed_devices:
            self.btn_retry.setText(f"🔄 重试失败设备 ({len(self.failed_devices)})")
        else:
            self.btn_retry.setText("🔄 重试失败设备")

        if failed_cmds > 0:
            self.stats_label.setStyleSheet("color: #DC2626;")
        elif total_cmds > 0:
            self.stats_label.setStyleSheet("color: #16A34A;")
        else:
            self.stats_label.setStyleSheet("color: #1E2028;")

    def on_retry_clicked(self):
        """点击重试失败设备"""
        if not self.failed_devices:
            return
        failed_ips = list(self.failed_devices)
        self.retry_requested.emit(failed_ips)

    # ==================== 清空与导出 ====================

    def clear_results(self):
        """清空全部结果"""
        self.results.clear()
        self.device_items.clear()
        self.failed_devices.clear()
        self.tree_widget.clear()
        self.output_text.clear()
        self.update_stats()

    def export_all_results(self):
        """导出全部结果到文本/JSON/CSV文件"""
        if not self.results:
            QMessageBox.information(self, "无数据", "没有可导出的结果")
            return

        file_path, _ = QFileDialog.getSaveFileName(
            self, "导出巡检结果", "巡检结果",
            "文本文件 (*.txt);;JSON 文件 (*.json);;CSV 文件 (*.csv)"
        )
        if not file_path:
            return

        try:
            suffix = Path(file_path).suffix.lower()
            if suffix == ".json":
                self._export_json(file_path)
            elif suffix == ".csv":
                self._export_csv(file_path)
            else:
                self._export_txt(file_path)
            QMessageBox.information(self, "导出成功", f"结果已导出到:\n{file_path}")
        except Exception as e:
            QMessageBox.warning(self, "导出失败", str(e))

    def _export_txt(self, file_path: str):
        """导出为纯文本"""
        with open(file_path, "w", encoding="utf-8") as f:
            for device_ip, results in self.results.items():
                f.write(f"{'='*60}\n")
                f.write(f"设备: {device_ip}\n")
                f.write(f"{'='*60}\n\n")
                for r in results:
                    status = "✓" if r.get("success") else "✗"
                    f.write(f"[{status}] [{r.get('group', '')}] {r.get('command', '')}\n")
                    f.write(f"时间: {r.get('timestamp', '')}\n")
                    f.write(f"输出:\n{r.get('output', '')}\n")
                    f.write(f"{'-'*40}\n\n")

    def _export_json(self, file_path: str):
        """导出为 JSON"""
        export_data = []
        for device_ip, results in self.results.items():
            for r in results:
                export_data.append({
                    "device_ip": device_ip,
                    "group": r.get("group", ""),
                    "command": r.get("command", ""),
                    "success": r.get("success", False),
                    "timestamp": r.get("timestamp", ""),
                    "output": r.get("output", ""),
                })
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(export_data, f, ensure_ascii=False, indent=2)

    def _export_csv(self, file_path: str):
        """导出为 CSV"""
        with open(file_path, "w", encoding="utf-8-sig", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["设备IP", "命令组", "命令", "状态", "时间", "输出"])
            for device_ip, results in self.results.items():
                for r in results:
                    writer.writerow([
                        device_ip,
                        r.get("group", ""),
                        r.get("command", ""),
                        "成功" if r.get("success") else "失败",
                        r.get("timestamp", ""),
                        r.get("output", ""),
                    ])

    def export_log(self):
        """导出运行日志（输出区内容）"""
        log_text = self.output_text.toPlainText()
        if not log_text:
            QMessageBox.information(self, "无内容", "当前输出区无日志可导出")
            return

        file_path, _ = QFileDialog.getSaveFileName(
            self, "导出日志", "运行日志.txt", "文本文件 (*.txt)"
        )
        if not file_path:
            return

        try:
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(log_text)
            QMessageBox.information(self, "导出成功", f"日志已导出到:\n{file_path}")
        except Exception as e:
            QMessageBox.warning(self, "导出失败", str(e))

    def remove_device_results(self, device_ips: list):
        """移除指定设备的结果数据"""
        for ip in device_ips:
            self.results.pop(ip, None)
            device_item = self.device_items.pop(ip, None)
            if device_item:
                self.tree_widget.invisibleRootItem().removeChild(device_item)
        self.failed_devices.clear()
        self.output_text.clear()
