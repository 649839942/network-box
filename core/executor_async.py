# core/executor_async.py
"""
基于 QThread 的命令执行器，避免界面卡顿
"""
import time
from typing import Dict, List

from PySide6.QtCore import QThread, Signal
from netmiko import (
    ConnectHandler,
    NetMikoAuthenticationException,
    NetMikoTimeoutException,
    SSHDetect,
)

from core.netmiko_utils import (
    VENDOR_NAMES,
    disable_terminal_paging,
    vendor_from_device_type,
)


AUTO_SSH = "autodetect"
AUTO_TELNET = "autodetect_telnet"
VENDOR_DRIVERS = {
    "huawei": {"ssh": "huawei", "telnet": "huawei_telnet"},
    "h3c": {"ssh": "h3c_comware", "telnet": "hp_comware_telnet"},
    "cisco": {"ssh": "cisco_ios", "telnet": "cisco_ios_telnet"},
}
TELNET_PROBE_DRIVERS = (
    ("huawei_telnet", "display version"),
    ("hp_comware_telnet", "display version"),
    ("cisco_ios_telnet", "show version"),
)


def _detect_vendor_from_version(output: str):
    lowered = str(output).lower()
    if any(marker in lowered for marker in ("h3c comware", "comware software", "h3c technologies")):
        return "h3c"
    if any(marker in lowered for marker in ("huawei technologies", "versatile routing platform")):
        return "huawei"
    if any(marker in lowered for marker in ("cisco ios software", "cisco internetwork operating system")):
        return "cisco"
    return None


class ConnectionTestWorker(QThread):
    """测试连接，并返回厂商识别结果。"""
    finished_signal = Signal(bool, str, str)

    def __init__(self, device_config: Dict, parent=None):
        super().__init__(parent)
        self.device_config = device_config
        self.connection = None

    def _config_for_driver(self, driver: str) -> Dict:
        config = self.device_config.copy()
        config["device_type"] = driver
        return config

    def _detect_ssh_vendor(self):
        config = self._config_for_driver(AUTO_SSH)
        detected_type = SSHDetect(**config).autodetect()
        vendor = vendor_from_device_type(detected_type)
        if vendor is None:
            raise ValueError("连接成功，但未能自动识别为华为、新华三或思科")
        return vendor

    def _detect_telnet_vendor(self):
        connected = False
        last_error = None
        for driver, version_command in TELNET_PROBE_DRIVERS:
            connection = None
            try:
                connection = ConnectHandler(**self._config_for_driver(driver))
                connected = True
                output = connection.send_command(version_command, read_timeout=30)
                vendor = _detect_vendor_from_version(output)
                if vendor:
                    return vendor
            except NetMikoAuthenticationException:
                raise
            except Exception as exc:
                last_error = exc
                continue
            finally:
                if connection:
                    try:
                        connection.disconnect()
                    except Exception:
                        pass
        if not connected and last_error:
            raise last_error
        raise ValueError("连接成功，但未能自动识别为华为、新华三或思科")

    def _connect_detected_vendor(self, vendor: str):
        driver = VENDOR_DRIVERS[vendor]["ssh"]
        self.connection = ConnectHandler(**self._config_for_driver(driver))
        disable_terminal_paging(self.connection, {"device_type": driver})

    def run(self):
        try:
            requested_type = str(self.device_config.get("device_type", ""))
            if requested_type == AUTO_SSH:
                vendor = self._detect_ssh_vendor()
                self._connect_detected_vendor(vendor)
                message = f"连接成功，自动识别为{VENDOR_NAMES[vendor]}"
            elif requested_type == AUTO_TELNET:
                vendor = self._detect_telnet_vendor()
                driver = VENDOR_DRIVERS[vendor]["telnet"]
                self.connection = ConnectHandler(**self._config_for_driver(driver))
                disable_terminal_paging(self.connection, {"device_type": driver})
                message = f"连接成功，自动识别为{VENDOR_NAMES[vendor]}"
            else:
                vendor = vendor_from_device_type(requested_type)
                self.connection = ConnectHandler(**self.device_config)
                disable_terminal_paging(self.connection, self.device_config)
                message = "连接成功" if vendor is None else f"连接成功（{VENDOR_NAMES[vendor]}）"
            self.finished_signal.emit(True, message, vendor or "")
        except NetMikoAuthenticationException:
            self.finished_signal.emit(False, "认证失败，请检查用户名和密码", "")
        except NetMikoTimeoutException:
            self.finished_signal.emit(False, "连接超时，请检查IP地址和端口", "")
        except Exception as e:
            message = str(e) if str(e).startswith("连接成功") else f"连接失败: {str(e)}"
            self.finished_signal.emit(False, message, "")
        finally:
            if self.connection:
                try:
                    self.connection.disconnect()
                except Exception:
                    pass
                self.connection = None


class BatchInspector(QThread):
    """多设备批量巡检执行器 — 逐台设备顺序执行"""

    # 信号
    current_device = Signal(str, int, int)    # device_ip, 当前第N台, 总设备数
    device_log = Signal(str)                   # 日志消息
    command_result = Signal(str, dict)         # device_ip, 命令结果字典
    progress_signal = Signal(int, int)         # 精确进度: 当前已完成步数, 总步数
    device_finished = Signal(str, bool)   # device_ip, 成功/失败
    batch_finished = Signal(bool, str)         # 全部完成: 是否全部成功, 汇总消息

    def __init__(self, devices: List[Dict], commands: List[Dict], parent=None):
        """
        Args:
            devices: 设备配置列表，每项为 get_device_config() 格式
            commands: 命令列表，每项含 group / command 字段
        """
        super().__init__(parent)
        self.devices = devices
        self.commands = commands
        self._is_running = True
        self._results = []
        self._total_steps = len(devices) * len(commands)  # 精确总步数
        self._connection = None  # 当前设备连接，用于 stop 时断开

    def stop(self):
        """停止全部巡检"""
        self._is_running = False
        if self._connection:
            try:
                self._connection.disconnect()
            except Exception:
                pass
            self._connection = None

    def _try_send_command(self, cmd_str: str) -> str:
        """发送命令，兼容 netmiko 3.x/4.x 的 read_timeout 参数"""
        try:
            return self._connection.send_command(
                command_string=cmd_str,
                delay_factor=1.5,
                max_loops=500,
                read_timeout=60
            )
        except TypeError:
            return self._connection.send_command(
                command_string=cmd_str,
                delay_factor=1.5,
                max_loops=500
            )

    def run(self):
        """执行入口—逐台巡检"""
        total_devices = len(self.devices)
        all_success = True
        completed_steps = 0

        for idx, device in enumerate(self.devices, 1):
            if not self._is_running:
                self.device_log.emit("[SYSTEM] 用户已取消操作")
                self.batch_finished.emit(False, "巡检已取消")
                return

            device_ip = device.get("host", "未知")
            self.current_device.emit(device_ip, idx, total_devices)
            self.device_log.emit(f"▶ 开始巡检 [{idx}/{total_devices}] {device_ip}")

            self._connection = None
            device_ok = True

            try:
                self.device_log.emit(f"正在连接 {device_ip}:{device.get('port', 22)}...")
                self._connection = ConnectHandler(**device)
                disable_terminal_paging(self._connection, device)
                self.device_log.emit("✓ 连接成功")

                for cmd in self.commands:
                    if not self._is_running:
                        break

                    try:
                        self.device_log.emit(f"  执行: {cmd['command']}")

                        output = self._try_send_command(cmd["command"])

                        result = {
                            **cmd,
                            "device_ip": device_ip,
                            "output": output,
                            "success": True,
                            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
                        }
                        self._results.append(result)
                        self.command_result.emit(device_ip, result)
                        completed_steps += 1
                        self.progress_signal.emit(completed_steps, self._total_steps)
                        self.device_log.emit(f"  ✓ {cmd['command']} — 成功")

                    except Exception as e:
                        if not self._is_running:
                            break
                        all_success = False
                        result = {
                            **cmd,
                            "device_ip": device_ip,
                            "output": str(e),
                            "success": False,
                            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
                        }
                        self._results.append(result)
                        self.command_result.emit(device_ip, result)
                        completed_steps += 1
                        self.progress_signal.emit(completed_steps, self._total_steps)
                        self.device_log.emit(f"  ✗ {cmd['command']} — 失败: {str(e)}")

            except NetMikoAuthenticationException:
                self.device_log.emit(f"✗ {device_ip} 认证失败，请检查用户名和密码")
                device_ok = False
                all_success = False
                self._total_steps -= len(self.commands)
            except NetMikoTimeoutException:
                self.device_log.emit(f"✗ {device_ip} 连接超时，请检查IP地址和端口")
                device_ok = False
                all_success = False
                self._total_steps -= len(self.commands)
            except Exception as e:
                self.device_log.emit(f"✗ {device_ip} 连接失败: {str(e)}")
                device_ok = False
                all_success = False
                self._total_steps -= len(self.commands)
            finally:
                if self._connection:
                    try:
                        self._connection.disconnect()
                    except Exception:
                        pass
                    self._connection = None

            self.device_finished.emit(device_ip, device_ok)

        total_cmds = len(self._results)
        success_cmds = sum(1 for r in self._results if r.get("success"))
        summary = (f"巡检完成: {total_devices} 台设备, "
                   f"{total_cmds} 条命令, "
                   f"成功 {success_cmds}, "
                   f"失败 {total_cmds - success_cmds}")
        self.batch_finished.emit(all_success, summary)


__all__ = ["BatchInspector", "ConnectionTestWorker"]
