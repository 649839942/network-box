"""
独立 SNMP 连通性测试标签页 - 按版本动态切换认证信息表单。
"""
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QSizePolicy,
    QScrollArea,
    QStackedWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from core.snmp_worker import (
    AUTH_PROTOCOL_OPTIONS,
    PRIV_PROTOCOL_OPTIONS,
    SYS_DESCR_OID,
    SnmpTestWorker,
)


class SnmpPanel(QWidget):
    """SNMP 测试标签页。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._worker = None
        self._auth_options = dict(AUTH_PROTOCOL_OPTIONS)
        self._priv_options = dict(PRIV_PROTOCOL_OPTIONS)
        self.setObjectName("snmp_page")
        self.setStyleSheet("QWidget#snmp_page { background-color: #F8F9FB; }")
        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(8, 4, 8, 8)

        # ---------- 配置区（窗口过小时可滚动，避免输入框被挤压） ----------
        config_scroll = QScrollArea()
        config_scroll.setWidgetResizable(True)
        config_scroll.setFrameShape(QFrame.NoFrame)
        config_scroll.setStyleSheet(
            "QScrollArea { background-color: #F8F9FB; border: none; }"
            "QScrollArea > QWidget > QWidget { background-color: #F8F9FB; }"
        )

        config_container = QWidget()
        config_container.setObjectName("config_container")
        config_container.setStyleSheet(
            "QWidget#config_container { background-color: #F8F9FB; }"
        )
        config_layout = QVBoxLayout(config_container)
        config_layout.setSpacing(10)
        config_layout.setContentsMargins(0, 0, 0, 0)

        # ---------- 测试目标 ----------
        target_group = QGroupBox("测试目标")
        target_group.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)
        target_form = QFormLayout(target_group)
        target_form.setLabelAlignment(Qt.AlignRight)

        self.host_edit = QLineEdit()
        self.host_edit.setPlaceholderText("设备IP地址或主机名")

        self.version_combo = QComboBox()
        self.version_combo.addItems(["SNMPv1", "SNMPv2c", "SNMPv3"])
        self.version_combo.setCurrentIndex(1)

        self.port_spin = QSpinBox()
        self.port_spin.setRange(1, 65535)
        self.port_spin.setValue(161)

        self.timeout_spin = QSpinBox()
        self.timeout_spin.setRange(1, 30)
        self.timeout_spin.setValue(3)
        self.timeout_spin.setSuffix(" 秒")

        self.retry_spin = QSpinBox()
        self.retry_spin.setRange(0, 10)
        self.retry_spin.setValue(1)

        target_form.addRow("目标地址:", self.host_edit)
        target_form.addRow("SNMP版本:", self.version_combo)
        target_form.addRow("端口:", self.port_spin)
        target_form.addRow("超时时间:", self.timeout_spin)
        target_form.addRow("重试次数:", self.retry_spin)
        config_layout.addWidget(target_group)

        # ---------- 认证信息（按版本动态切换） ----------
        cred_group = QGroupBox("认证信息")
        cred_group.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)
        cred_layout = QVBoxLayout(cred_group)

        self.cred_stack = QStackedWidget()

        # v1 / v2c: 只填 community
        community_page = QWidget()
        community_form = QFormLayout(community_page)
        community_form.setLabelAlignment(Qt.AlignRight)
        self.community_edit = QLineEdit()
        self.community_edit.setPlaceholderText("请输入 Community")
        community_form.addRow("Community:", self.community_edit)
        self.cred_stack.addWidget(community_page)

        # v3: 用户名 + 认证 + 加密
        v3_page = QWidget()
        v3_form = QFormLayout(v3_page)
        v3_form.setLabelAlignment(Qt.AlignRight)

        self.username_edit = QLineEdit()
        self.username_edit.setPlaceholderText("SNMPv3 用户名")

        self.auth_combo = QComboBox()
        for label, _ in AUTH_PROTOCOL_OPTIONS:
            self.auth_combo.addItem(label)

        self.auth_pwd_edit = QLineEdit()
        self.auth_pwd_edit.setEchoMode(QLineEdit.Password)
        self.auth_pwd_edit.setPlaceholderText("认证密码")

        self.priv_combo = QComboBox()
        for label, _ in PRIV_PROTOCOL_OPTIONS:
            self.priv_combo.addItem(label)

        self.priv_pwd_edit = QLineEdit()
        self.priv_pwd_edit.setEchoMode(QLineEdit.Password)
        self.priv_pwd_edit.setPlaceholderText("加密密码")

        v3_form.addRow("用户名:", self.username_edit)
        v3_form.addRow("认证方式:", self.auth_combo)
        v3_form.addRow("认证密码:", self.auth_pwd_edit)
        v3_form.addRow("加密方式:", self.priv_combo)
        v3_form.addRow("加密密码:", self.priv_pwd_edit)
        self.cred_stack.addWidget(v3_page)

        cred_layout.addWidget(self.cred_stack)
        config_layout.addWidget(cred_group)

        config_scroll.setWidget(config_container)
        layout.addWidget(config_scroll, 1)

        # ---------- 测试结果 ----------
        result_group = QGroupBox("测试结果")
        result_layout = QVBoxLayout(result_group)

        self.result_label = QLabel("等待测试...")
        self.result_label.setObjectName("status_label")
        self.result_label.setWordWrap(True)
        result_layout.addWidget(self.result_label)

        self.result_text = QTextEdit()
        self.result_text.setReadOnly(True)
        self.result_text.setFont(QFont("Consolas", 10))
        self.result_text.setMaximumHeight(260)
        result_layout.addWidget(self.result_text)

        btn_row = QHBoxLayout()
        btn_row.addStretch()

        self.btn_start = QPushButton("▶ 开始测试")
        self.btn_start.setObjectName("connect_button")
        self.btn_start.setFixedSize(140, 40)
        self.btn_start.clicked.connect(self.start_test)
        btn_row.addWidget(self.btn_start)

        self.btn_clear = QPushButton("清空结果")
        self.btn_clear.setObjectName("btn_tool")
        self.btn_clear.setFixedSize(110, 40)
        self.btn_clear.clicked.connect(self.clear_result)
        btn_row.addWidget(self.btn_clear)

        result_layout.addLayout(btn_row)
        layout.addWidget(result_group)

        # ---------- 动态表单 ----------
        self.version_combo.currentIndexChanged.connect(self._on_version_changed)
        self.auth_combo.currentIndexChanged.connect(self._on_auth_changed)
        self.priv_combo.currentIndexChanged.connect(self._on_priv_changed)
        self._on_version_changed()
        self._on_auth_changed()

    def _version(self) -> int:
        return self.version_combo.currentIndex() + 1

    def _version_name(self) -> str:
        return self.version_combo.currentText()

    def _on_version_changed(self):
        is_v3 = self._version() == 3
        self.cred_stack.setCurrentIndex(1 if is_v3 else 0)

    def _on_auth_changed(self):
        auth_none = self.auth_combo.currentText() == "无认证"
        self.auth_pwd_edit.setEnabled(not auth_none)
        if auth_none:
            self.priv_combo.setCurrentText("无加密")
            self.priv_combo.setEnabled(False)
            self.priv_pwd_edit.clear()
            self.priv_pwd_edit.setEnabled(False)
        else:
            self.priv_combo.setEnabled(True)
            self._on_priv_changed()

    def _on_priv_changed(self):
        priv_none = self.priv_combo.currentText() == "无加密"
        self.priv_pwd_edit.setEnabled(not priv_none)
        if priv_none:
            self.priv_pwd_edit.clear()

    def start_test(self):
        host = self.host_edit.text().strip()
        if not host:
            QMessageBox.warning(self, "缺少目标", "请填写设备IP地址或主机名")
            self.host_edit.setFocus()
            return

        version = self._version()
        timeout = self.timeout_spin.value()
        retries = self.retry_spin.value()
        port = self.port_spin.value()

        if version == 3:
            username = self.username_edit.text().strip()
            if not username:
                QMessageBox.warning(self, "缺少用户名", "SNMPv3 测试需要填写用户名")
                self.username_edit.setFocus()
                return

            auth_label = self.auth_combo.currentText()
            priv_label = self.priv_combo.currentText()
            auth_password = self.auth_pwd_edit.text()
            priv_password = self.priv_pwd_edit.text()

            if auth_label != "无认证" and not auth_password:
                QMessageBox.warning(self, "缺少认证密码", "请填写认证密码")
                self.auth_pwd_edit.setFocus()
                return
            if priv_label != "无加密" and not priv_password:
                QMessageBox.warning(self, "缺少加密密码", "请填写加密密码")
                self.priv_pwd_edit.setFocus()
                return

            self._start_worker(
                SnmpTestWorker(
                    version,
                    host,
                    port=port,
                    username=username,
                    auth_protocol=self._auth_options[auth_label],
                    auth_password=auth_password,
                    priv_protocol=self._priv_options[priv_label],
                    priv_password=priv_password,
                    timeout=timeout,
                    retries=retries,
                )
            )
        else:
            community = self.community_edit.text().strip()
            if not community:
                QMessageBox.warning(self, "缺少 Community", "请填写 Community 字符串")
                self.community_edit.setFocus()
                return
            self._start_worker(
                SnmpTestWorker(
                    version,
                    host,
                    port=port,
                    community=community,
                    timeout=timeout,
                    retries=retries,
                )
            )

    def _start_worker(self, worker: SnmpTestWorker):
        self._worker = worker
        self._worker.finished_signal.connect(self._on_test_finished)
        self.btn_start.setEnabled(False)
        self.btn_start.setText("测试中...")
        self.result_label.setText("测试中...")
        self.result_label.setStyleSheet("color: #2563EB;")
        self._append_log(
            f"开始测试 {worker.host}:{worker.port} ({self._version_name()}) ..."
        )
        self._append_log(
            f"超时 {worker.timeout}s, 重试 {worker.retries} 次, OID {SYS_DESCR_OID}"
        )
        worker.start()

    def _on_test_finished(self, ok: bool, detail: str):
        self.btn_start.setEnabled(True)
        self.btn_start.setText("▶ 开始测试")

        if ok:
            self.result_label.setText("✅ SNMP 连通正常")
            self.result_label.setStyleSheet("color: #16A34A;")
            self._append_log("✅ SNMP 连通正常")
        else:
            self.result_label.setText("❌ SNMP 测试失败")
            self.result_label.setStyleSheet("color: #DC2626;")
            self._append_log("❌ SNMP 测试失败")

        if detail:
            self._append_log(detail)
        self._append_log("-" * 50)

    def _append_log(self, message: str):
        self.result_text.append(message)
        scrollbar = self.result_text.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def clear_result(self):
        self.result_text.clear()
        self.result_label.setText("等待测试...")
        self.result_label.setStyleSheet("color: #6B7280;")

    def shutdown(self):
        if self._worker and self._worker.isRunning():
            self._worker.terminate()
            self._worker.wait(3000)
