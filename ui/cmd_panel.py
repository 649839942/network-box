"""
CMD 命令面板 — 集成 Ping / Tracert 与常用网络命令执行。
"""
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from core.cmd_worker import CmdWorker

CMD_HINTS = """常用命令提示：
  ping <IP或域名>        测试连通性
  ping <IP> -t           持续测试（可在执行中点击“停止”结束）
  tracert <IP或域名>     路由追踪
  ipconfig /all          查看本机网络配置
  netstat -ano           查看端口与网络连接
  nslookup <域名>        查询域名解析
"""


class CmdPanel(QWidget):
    """工具箱内的 CMD 命令执行页面。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._worker = None
        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(8, 4, 8, 8)

        # 目标与快捷命令
        target_group = QGroupBox("目标与快捷命令")
        target_layout = QHBoxLayout(target_group)
        target_layout.addWidget(QLabel("目标:"))

        self.target_edit = QLineEdit()
        self.target_edit.setPlaceholderText("IP 地址或域名，例如 192.0.2.1")
        target_layout.addWidget(self.target_edit, 1)

        self.btn_ping = QPushButton("Ping")
        self.btn_ping.setObjectName("connect_button")
        self.btn_ping.clicked.connect(lambda: self._quick_command("ping"))
        target_layout.addWidget(self.btn_ping)

        self.btn_ping_t = QPushButton("Ping -t")
        self.btn_ping_t.setObjectName("connect_button")
        self.btn_ping_t.clicked.connect(lambda: self._quick_command("ping -t"))
        target_layout.addWidget(self.btn_ping_t)

        self.btn_tracert = QPushButton("Tracert")
        self.btn_tracert.setObjectName("connect_button")
        self.btn_tracert.clicked.connect(lambda: self._quick_command("tracert"))
        target_layout.addWidget(self.btn_tracert)

        layout.addWidget(target_group)

        # 自定义命令
        command_group = QGroupBox("自定义命令")
        command_layout = QHBoxLayout(command_group)

        self.command_edit = QLineEdit()
        self.command_edit.setPlaceholderText("输入完整命令，例如 ping 192.0.2.1 -n 5")
        self.command_edit.returnPressed.connect(self.run_command)
        command_layout.addWidget(self.command_edit, 1)

        self.btn_run = QPushButton("执行")
        self.btn_run.setObjectName("start_button")
        self.btn_run.clicked.connect(self.run_command)
        command_layout.addWidget(self.btn_run)

        self.btn_stop = QPushButton("停止")
        self.btn_stop.setObjectName("clear_button")
        self.btn_stop.setEnabled(False)
        self.btn_stop.clicked.connect(self.stop_current)
        command_layout.addWidget(self.btn_stop)

        self.btn_clear = QPushButton("清空输出")
        self.btn_clear.setObjectName("btn_tool")
        self.btn_clear.clicked.connect(self.clear_output)
        command_layout.addWidget(self.btn_clear)

        layout.addWidget(command_group)

        # 命令提示
        hint_group = QGroupBox("命令提示")
        hint_layout = QVBoxLayout(hint_group)
        self.hint_text = QTextEdit()
        self.hint_text.setReadOnly(True)
        self.hint_text.setPlainText(CMD_HINTS)
        self.hint_text.setMaximumHeight(130)
        self.hint_text.setStyleSheet(
            "QTextEdit { background-color: #F8FAFC; color: #475569;"
            " border: 1px solid #E2E8F0; border-radius: 6px; font-size: 12px; }"
        )
        hint_layout.addWidget(self.hint_text)
        layout.addWidget(hint_group)

        # 输出
        output_group = QGroupBox("执行输出")
        output_layout = QVBoxLayout(output_group)
        self.output_text = QTextEdit()
        self.output_text.setReadOnly(True)
        self.output_text.setFont(QFont("Consolas", 10))
        self.output_text.setMinimumHeight(180)
        output_layout.addWidget(self.output_text)
        layout.addWidget(output_group, 1)

    def _quick_command(self, prefix: str):
        target = self.target_edit.text().strip()
        if not target:
            QMessageBox.warning(self, "缺少目标", "请先填写目标 IP 或域名")
            return
        command = f"{prefix} {target}"
        self.command_edit.setText(command)
        self.run_command(command)

    def run_command(self, command: str = None):
        if command is None:
            command = self.command_edit.text().strip()
        if not command:
            QMessageBox.warning(self, "无命令", "请输入要执行的命令")
            return
        if self._worker and self._worker.isRunning():
            QMessageBox.warning(self, "命令正在执行", "请等待当前命令完成，或先点击停止")
            return

        self._append_output(f"> {command}\n")
        self._worker = CmdWorker(command, timeout=60)
        self._worker.output_signal.connect(self._append_output)
        self._worker.finished_signal.connect(self._on_finished)
        self._set_running(True)
        self._worker.start()

    def _on_finished(self, ok: bool, message: str):
        self._set_running(False)
        self._append_output(message)

    def _set_running(self, running: bool):
        self.btn_ping.setEnabled(not running)
        self.btn_ping_t.setEnabled(not running)
        self.btn_tracert.setEnabled(not running)
        self.btn_run.setEnabled(not running)
        self.btn_stop.setEnabled(running)

    def stop_current(self):
        if self._worker and self._worker.isRunning():
            self._worker.stop()

    def clear_output(self):
        self.output_text.clear()

    def _append_output(self, message: str):
        self.output_text.append(message)
        scrollbar = self.output_text.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def shutdown(self):
        if self._worker and self._worker.isRunning():
            self._worker.stop()
            self._worker.wait(3000)
