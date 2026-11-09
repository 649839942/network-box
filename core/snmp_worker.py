# core/snmp_worker.py
"""
SNMP 连通性测试线程 - 支持 SNMPv1 / v2c / v3 及主流认证加密方式。
"""
import asyncio

from PySide6.QtCore import QThread, Signal

from pysnmp.hlapi.v1arch.asyncio.slim import Slim
from pysnmp.hlapi.v3arch.asyncio import (
    ContextData,
    SnmpEngine,
    UdpTransportTarget,
    UsmUserData,
    get_cmd,
)
from pysnmp.hlapi.v3arch.asyncio import (
    usm3DESEDEPrivProtocol,
    usmAesCfb128Protocol,
    usmAesCfb192Protocol,
    usmAesCfb256Protocol,
    usmDESPrivProtocol,
    usmHMAC128SHA224AuthProtocol,
    usmHMAC192SHA256AuthProtocol,
    usmHMAC256SHA384AuthProtocol,
    usmHMAC384SHA512AuthProtocol,
    usmHMACMD5AuthProtocol,
    usmHMACSHAAuthProtocol,
    usmNoAuthProtocol,
    usmNoPrivProtocol,
)
from pysnmp.smi.rfc1902 import ObjectIdentity, ObjectType

SYS_DESCR_OID = "1.3.6.1.2.1.1.1.0"

AUTH_PROTOCOL_OPTIONS = [
    ("无认证", None),
    ("MD5", usmHMACMD5AuthProtocol),
    ("SHA", usmHMACSHAAuthProtocol),
    ("SHA224", usmHMAC128SHA224AuthProtocol),
    ("SHA256", usmHMAC192SHA256AuthProtocol),
    ("SHA384", usmHMAC256SHA384AuthProtocol),
    ("SHA512", usmHMAC384SHA512AuthProtocol),
]

PRIV_PROTOCOL_OPTIONS = [
    ("无加密", None),
    ("DES", usmDESPrivProtocol),
    ("3DES", usm3DESEDEPrivProtocol),
    ("AES128", usmAesCfb128Protocol),
    ("AES192", usmAesCfb192Protocol),
    ("AES256", usmAesCfb256Protocol),
]


class SnmpTestWorker(QThread):
    """后台执行 SNMP GET 测试，避免阻塞界面。"""

    finished_signal = Signal(bool, str)

    def __init__(
        self,
        version: int,
        host: str,
        port: int = 161,
        community: str = "",
        username: str = "",
        auth_protocol=None,
        auth_password: str = "",
        priv_protocol=None,
        priv_password: str = "",
        timeout: int = 3,
        retries: int = 1,
        parent=None,
    ):
        super().__init__(parent)
        self.version = version
        self.host = host
        self.port = port
        self.community = community
        self.username = username
        self.auth_protocol = auth_protocol
        self.auth_password = auth_password
        self.priv_protocol = priv_protocol
        self.priv_password = priv_password
        self.timeout = timeout
        self.retries = retries

    def run(self):
        try:
            ok, detail = asyncio.run(self._run_test())
        except Exception as exc:
            ok, detail = False, f"SNMP 测试异常: {exc}"
        self.finished_signal.emit(ok, detail)

    async def _run_test(self):
        if not self.host or not self.host.strip():
            return False, "目标地址不能为空"
        if self.version not in (1, 2, 3):
            return False, f"不支持的 SNMP 版本: {self.version}"
        if not 1 <= self.port <= 65535:
            return False, f"SNMP 端口无效: {self.port}"
        if self.version == 3:
            return await self._test_v3()
        if not self.community or not self.community.strip():
            return False, "Community 不能为空"
        return await self._test_v1v2()

    async def _test_v1v2(self):
        with Slim(version=self.version) as slim:
            error_indication, error_status, error_index, var_binds = await slim.get(
                self.community,
                self.host,
                self.port,
                ObjectType(ObjectIdentity(SYS_DESCR_OID)),
                timeout=self.timeout,
                retries=self.retries,
            )
        return self._build_result(
            error_indication, error_status, error_index, var_binds
        )

    async def _test_v3(self):
        if not self.username:
            return False, "SNMPv3 用户名不能为空"
        if self.auth_protocol and not self.auth_password:
            return False, "SNMPv3 认证密码不能为空"
        if self.priv_protocol and not self.priv_password:
            return False, "SNMPv3 加密密码不能为空"
        if self.priv_protocol and not self.auth_protocol:
            return False, "SNMPv3 启用加密前需要先启用认证"

        engine = SnmpEngine()
        try:
            auth_data = UsmUserData(
                self.username,
                authKey=self.auth_password or None,
                privKey=self.priv_password or None,
                authProtocol=self.auth_protocol or usmNoAuthProtocol,
                privProtocol=self.priv_protocol or usmNoPrivProtocol,
            )
            transport = await UdpTransportTarget.create(
                (self.host, self.port), self.timeout, self.retries
            )
            error_indication, error_status, error_index, var_binds = await get_cmd(
                engine,
                auth_data,
                transport,
                ContextData(),
                ObjectType(ObjectIdentity(SYS_DESCR_OID)),
            )
            return self._build_result(
                error_indication, error_status, error_index, var_binds
            )
        finally:
            try:
                engine.close_dispatcher()
            except Exception:
                pass

    def _build_result(self, error_indication, error_status, error_index, var_binds):
        if error_indication:
            return False, f"SNMP 无响应/超时: {error_indication}"
        if error_status:
            return False, f"SNMP 返回错误: {error_status} (索引 {error_index})"
        if not var_binds:
            return False, "SNMP 响应成功，但未返回数据"

        lines = []
        for var_bind in var_binds:
            try:
                oid = var_bind[0].prettyPrint()
                value = var_bind[1].prettyPrint()
            except Exception:
                try:
                    text = str(var_bind)
                except Exception:
                    text = repr(var_bind)
                return True, text
            lines.append(f"{oid} = {value}")
        return True, "\n".join(lines)


__all__ = [
    "SnmpTestWorker",
    "AUTH_PROTOCOL_OPTIONS",
    "PRIV_PROTOCOL_OPTIONS",
]
