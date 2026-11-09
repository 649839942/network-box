"""Configuration import, export, and side-by-side comparison page."""
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QFont, QTextCharFormat, QTextCursor, QTextFormat
from PySide6.QtWidgets import (
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from core.config_backup_worker import ConfigBackupWorker
from core.config_compare import VENDOR_NAMES, compare_config_lines, detect_config_vendor


class ConfigPane(QGroupBox):
    """A single configuration editor with import/export controls."""

    def __init__(self, title: str, parent=None):
        super().__init__(title, parent)
        self.source_path = None
        self.vendor = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 18, 12, 12)
        layout.setSpacing(8)

        info_row = QHBoxLayout()
        self.file_label = QLabel("未导入文件")
        self.file_label.setObjectName("config_file_label")
        info_row.addWidget(self.file_label, 1)

        self.vendor_label = QLabel("厂商: 未识别")
        self.vendor_label.setObjectName("config_vendor_label")
        info_row.addWidget(self.vendor_label)
        layout.addLayout(info_row)

        action_row = QHBoxLayout()
        self.btn_import = QPushButton("导入配置")
        self.btn_import.setObjectName("btn_tool")
        action_row.addWidget(self.btn_import)

        self.btn_export = QPushButton("导出配置")
        self.btn_export.setObjectName("btn_tool")
        action_row.addWidget(self.btn_export)
        action_row.addStretch(1)
        layout.addLayout(action_row)

        self.editor = QPlainTextEdit()
        self.editor.setFont(QFont("Consolas", 10))
        self.editor.setLineWrapMode(QPlainTextEdit.NoWrap)
        self.editor.setPlaceholderText("导入或粘贴华为 / 新华三 / 思科配置")
        self.editor.setMinimumHeight(260)
        self.editor.setStyleSheet(
            "QPlainTextEdit { background-color: #FFFFFF; color: #1E293B; }"
        )
        layout.addWidget(self.editor, 1)

    def set_content(self, text: str, file_path: Path, vendor: str):
        self.source_path = file_path
        self.vendor = vendor
        self.editor.blockSignals(True)
        self.editor.setPlainText(text)
        self.editor.blockSignals(False)
        self.file_label.setText(file_path.name)
        self.file_label.setToolTip(str(file_path))
        self.vendor_label.setText(f"厂商: {VENDOR_NAMES[vendor]}")
        self.vendor_label.setStyleSheet("color: #2563EB; font-weight: 600;")

    def set_vendor(self, vendor):
        self.vendor = vendor
        if vendor:
            self.vendor_label.setText(f"厂商: {VENDOR_NAMES[vendor]}")
            self.vendor_label.setStyleSheet("color: #2563EB; font-weight: 600;")
        else:
            self.vendor_label.setText("厂商: 未识别")
            self.vendor_label.setStyleSheet("color: #DC2626; font-weight: 600;")

    def clear_content(self):
        self.source_path = None
        self.vendor = None
        self.editor.blockSignals(True)
        self.editor.clear()
        self.editor.blockSignals(False)
        self.file_label.setText("未导入文件")
        self.file_label.setToolTip("")
        self.vendor_label.setText("厂商: 未识别")
        self.vendor_label.setStyleSheet("color: #6B7280;")
        self.clear_highlights()

    def mark_dirty(self):
        self.source_path = None
        self.vendor = None
        self.file_label.setText("手动编辑内容")
        self.file_label.setToolTip("")
        self.vendor_label.setText("厂商: 待比较")
        self.vendor_label.setStyleSheet("color: #B45309; font-weight: 600;")

    def clear_highlights(self):
        self.editor.setExtraSelections([])

    def highlight_lines(self, line_indexes, color: str):
        selections = []
        document = self.editor.document()
        for line_index in line_indexes:
            block = document.findBlockByNumber(line_index)
            if not block.isValid():
                continue
            cursor = QTextCursor(block)
            cursor.movePosition(QTextCursor.StartOfBlock)
            cursor.movePosition(QTextCursor.EndOfBlock, QTextCursor.KeepAnchor)

            selection = QTextEdit.ExtraSelection()
            selection.cursor = cursor
            char_format = QTextCharFormat()
            char_format.setBackground(QColor(color))
            char_format.setProperty(QTextFormat.FullWidthSelection, True)
            selection.format = char_format
            selections.append(selection)
        self.editor.setExtraSelections(selections)


class ConfigComparePanel(QWidget):
    """Huawei/H3C/Cisco configuration import, export, and comparison page."""

    save_requested = Signal()
    backup_finished = Signal(bool, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.backup_dir = Path.home() / "Documents" / "network-box" / "config-backups"
        self.backup_worker = None
        self._backup_results = []
        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 8)
        layout.setSpacing(8)

        action_row = QHBoxLayout()
        support_label = QLabel("支持格式: 华为 / 新华三 / 思科文本配置")
        support_label.setStyleSheet("color: #6B7280;")
        action_row.addWidget(support_label)
        action_row.addStretch(1)

        self.btn_compare = QPushButton("开始比较")
        self.btn_compare.setObjectName("start_button")
        self.btn_compare.setMinimumWidth(120)
        action_row.addWidget(self.btn_compare)

        self.btn_clear = QPushButton("清空")
        self.btn_clear.setObjectName("clear_button")
        self.btn_clear.setMinimumWidth(90)
        action_row.addWidget(self.btn_clear)
        layout.addLayout(action_row)

        backup_group = QGroupBox("保存交换机配置")
        backup_layout = QVBoxLayout(backup_group)
        backup_layout.setSpacing(6)

        directory_row = QHBoxLayout()
        self.btn_choose_dir = QPushButton("选择保存目录")
        self.btn_choose_dir.setObjectName("btn_tool")
        directory_row.addWidget(self.btn_choose_dir)

        self.backup_dir_label = QLabel()
        self.backup_dir_label.setObjectName("backup_dir_label")
        self.backup_dir_label.setToolTip(str(self.backup_dir))
        directory_row.addWidget(self.backup_dir_label, 1)
        backup_layout.addLayout(directory_row)

        save_row = QHBoxLayout()
        self.backup_status_label = QLabel("请在设备管理页勾选需要保存配置的设备")
        self.backup_status_label.setObjectName("backup_status_label")
        save_row.addWidget(self.backup_status_label, 1)

        self.btn_save_devices = QPushButton("保存已选设备配置")
        self.btn_save_devices.setObjectName("connect_button")
        self.btn_save_devices.setMinimumWidth(160)
        save_row.addWidget(self.btn_save_devices)
        backup_layout.addLayout(save_row)
        layout.addWidget(backup_group)

        self.splitter = QSplitter(Qt.Horizontal)
        self.left_pane = ConfigPane("配置 A（旧配置）")
        self.right_pane = ConfigPane("配置 B（新配置）")
        self.splitter.addWidget(self.left_pane)
        self.splitter.addWidget(self.right_pane)
        self.splitter.setSizes([520, 520])
        self.splitter.setStretchFactor(0, 1)
        self.splitter.setStretchFactor(1, 1)
        layout.addWidget(self.splitter, 1)

        status_row = QHBoxLayout()
        self.stats_label = QLabel("等待导入配置")
        self.stats_label.setObjectName("config_diff_stats")
        status_row.addWidget(self.stats_label, 1)

        old_legend = QLabel("旧配置差异")
        old_legend.setStyleSheet(
            "background-color: #FDE2E2; color: #991B1B; padding: 3px 8px; border-radius: 4px;"
        )
        status_row.addWidget(old_legend)
        new_legend = QLabel("新配置差异")
        new_legend.setStyleSheet(
            "background-color: #DCFCE7; color: #166534; padding: 3px 8px; border-radius: 4px;"
        )
        status_row.addWidget(new_legend)
        layout.addLayout(status_row)

        self.left_pane.btn_import.clicked.connect(
            lambda: self.import_config(self.left_pane)
        )
        self.right_pane.btn_import.clicked.connect(
            lambda: self.import_config(self.right_pane)
        )
        self.left_pane.btn_export.clicked.connect(
            lambda: self.export_config(self.left_pane)
        )
        self.right_pane.btn_export.clicked.connect(
            lambda: self.export_config(self.right_pane)
        )
        self.btn_compare.clicked.connect(self.compare_configs)
        self.btn_clear.clicked.connect(self.clear_all)
        self.btn_choose_dir.clicked.connect(self.choose_backup_dir)
        self.btn_save_devices.clicked.connect(lambda: self.save_requested.emit())

        self.left_pane.editor.textChanged.connect(
            lambda: self.on_content_changed(self.left_pane)
        )
        self.right_pane.editor.textChanged.connect(
            lambda: self.on_content_changed(self.right_pane)
        )
        self.left_pane.editor.verticalScrollBar().valueChanged.connect(
            self.right_pane.editor.verticalScrollBar().setValue
        )
        self.right_pane.editor.verticalScrollBar().valueChanged.connect(
            self.left_pane.editor.verticalScrollBar().setValue
        )
        self._update_backup_dir_label()

    def _update_backup_dir_label(self):
        self.backup_dir_label.setText(f"保存目录: {self.backup_dir}")
        self.backup_dir_label.setToolTip(str(self.backup_dir))

    def choose_backup_dir(self):
        try:
            self.backup_dir.mkdir(parents=True, exist_ok=True)
        except Exception as exc:
            QMessageBox.warning(self, "目录不可用", str(exc))
            return

        selected_dir = QFileDialog.getExistingDirectory(
            self,
            "选择配置保存目录",
            str(self.backup_dir),
        )
        if selected_dir:
            self.backup_dir = Path(selected_dir)
            self._update_backup_dir_label()

    def start_backup(self, devices: list):
        if self.backup_worker and self.backup_worker.isRunning():
            QMessageBox.information(self, "正在保存", "设备配置正在保存中，请稍候")
            return
        if not devices:
            QMessageBox.warning(
                self,
                "未选择设备",
                "请先在设备管理页勾选需要保存配置的设备。",
            )
            return

        self._backup_results = []
        self.backup_worker = ConfigBackupWorker(devices, self.backup_dir)
        self.backup_worker.device_started.connect(self.on_backup_device_started)
        self.backup_worker.device_finished.connect(self.on_backup_device_finished)
        self.backup_worker.progress_signal.connect(self.on_backup_progress)
        self.backup_worker.finished_signal.connect(self.on_backup_finished)
        self.set_backup_running(True)
        self.backup_status_label.setText("准备保存配置...")
        self.backup_status_label.setStyleSheet("color: #2563EB; font-weight: 600;")
        self.backup_worker.start()

    def set_backup_running(self, running: bool):
        self.btn_save_devices.setEnabled(not running)
        self.btn_choose_dir.setEnabled(not running)

    def on_backup_device_started(self, host: str, current: int, total: int):
        self.backup_status_label.setText(f"正在保存 {host} ({current}/{total})...")

    def on_backup_device_finished(self, host: str, success: bool, message: str, file_path: str):
        self._backup_results.append(f"{host}: {message}")
        color = "#16A34A" if success else "#DC2626"
        self.backup_status_label.setText(f"{host}: {message}")
        self.backup_status_label.setStyleSheet(f"color: {color}; font-weight: 600;")

    def on_backup_progress(self, current: int, total: int):
        self.backup_status_label.setText(f"配置保存进度: {current}/{total}")

    def on_backup_finished(self, all_success: bool, summary: str):
        self.set_backup_running(False)
        self.backup_status_label.setText(summary)
        color = "#16A34A" if all_success else "#DC2626"
        self.backup_status_label.setStyleSheet(f"color: {color}; font-weight: 600;")

        details = "\n".join(self._backup_results)
        message = f"{summary}\n\n{details}" if details else summary
        if all_success:
            QMessageBox.information(self, "保存完成", message)
        else:
            QMessageBox.warning(self, "保存完成", message)
        self.backup_finished.emit(all_success, summary)

    def shutdown(self):
        if self.backup_worker and self.backup_worker.isRunning():
            self.backup_worker.stop()
            if not self.backup_worker.wait(5000):
                self.backup_worker.terminate()
                self.backup_worker.wait(3000)

    def import_config(self, pane: ConfigPane):
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "导入交换机配置",
            "",
            "配置文件 (*.cfg *.conf *.txt);;所有文件 (*)",
        )
        if not file_path:
            return

        path = Path(file_path)
        try:
            config_text = path.read_text(encoding="utf-8-sig")
        except UnicodeDecodeError:
            QMessageBox.warning(
                self,
                "导入失败",
                "配置文件不是 UTF-8 编码，请转换为 UTF-8 后重试。",
            )
            return
        except Exception as exc:
            QMessageBox.warning(self, "导入失败", str(exc))
            return

        vendor = detect_config_vendor(config_text)
        if vendor is None:
            QMessageBox.warning(
                self,
                "无法识别厂商",
                "无法识别配置厂商，当前仅支持华为、新华三和思科配置。",
            )
            return

        other_pane = self.right_pane if pane is self.left_pane else self.left_pane
        other_vendor = detect_config_vendor(other_pane.editor.toPlainText())
        if other_vendor and other_vendor != vendor:
            QMessageBox.warning(self, "无法比较", "厂商不同，无法比较")
            return

        pane.set_content(config_text, path, vendor)
        pane.clear_highlights()
        self.stats_label.setText("配置已导入，点击“开始比较”")
        self.stats_label.setStyleSheet("color: #6B7280;")

    def export_config(self, pane: ConfigPane):
        config_text = pane.editor.toPlainText()
        if not config_text.strip():
            QMessageBox.information(self, "无内容", "没有可导出的配置内容")
            return

        vendor = detect_config_vendor(config_text)
        if vendor:
            pane.set_vendor(vendor)
            default_name = f"{vendor}_配置.cfg"
        elif pane.source_path:
            default_name = pane.source_path.name
        else:
            default_name = "交换机配置.cfg"

        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "导出交换机配置",
            default_name,
            "配置文件 (*.cfg);;文本文件 (*.txt);;所有文件 (*)",
        )
        if not file_path:
            return

        try:
            Path(file_path).write_text(config_text, encoding="utf-8", newline="\n")
            QMessageBox.information(self, "导出成功", f"配置已导出到:\n{file_path}")
        except Exception as exc:
            QMessageBox.warning(self, "导出失败", str(exc))

    def compare_configs(self):
        old_text = self.left_pane.editor.toPlainText()
        new_text = self.right_pane.editor.toPlainText()
        if not old_text.strip() or not new_text.strip():
            QMessageBox.warning(self, "缺少配置", "请先在左右两侧导入或粘贴配置")
            return

        old_vendor = detect_config_vendor(old_text)
        new_vendor = detect_config_vendor(new_text)
        self.left_pane.set_vendor(old_vendor)
        self.right_pane.set_vendor(new_vendor)

        if old_vendor is None or new_vendor is None:
            QMessageBox.warning(
                self,
                "无法识别厂商",
                "至少有一侧配置无法识别厂商，当前仅支持华为、新华三和思科配置。",
            )
            return
        if old_vendor != new_vendor:
            QMessageBox.warning(self, "无法比较", "厂商不同，无法比较")
            return

        result = compare_config_lines(old_text, new_text)
        self.left_pane.highlight_lines(result["old_indexes"], "#FDE2E2")
        self.right_pane.highlight_lines(result["new_indexes"], "#DCFCE7")

        if result["changed_blocks"] == 0:
            self.stats_label.setText("两个配置内容一致")
            self.stats_label.setStyleSheet("color: #16A34A; font-weight: 600;")
        else:
            self.stats_label.setText(
                f"发现 {result['changed_blocks']} 处差异："
                f"左侧 {len(result['old_indexes'])} 行，"
                f"右侧 {len(result['new_indexes'])} 行"
            )
            self.stats_label.setStyleSheet("color: #1E2028; font-weight: 600;")

    def on_content_changed(self, pane: ConfigPane):
        pane.mark_dirty()
        self.left_pane.clear_highlights()
        self.right_pane.clear_highlights()
        self.stats_label.setText("内容已更改，请重新比较")
        self.stats_label.setStyleSheet("color: #6B7280;")

    def clear_all(self):
        self.left_pane.clear_content()
        self.right_pane.clear_content()
        self.stats_label.setText("等待导入配置")
        self.stats_label.setStyleSheet("color: #6B7280;")
