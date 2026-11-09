"""Background worker for saving running configurations from network devices."""
import re
from datetime import datetime
from pathlib import Path

from netmiko import ConnectHandler, NetMikoAuthenticationException, NetMikoTimeoutException
from PySide6.QtCore import QThread, Signal

from core.netmiko_utils import disable_terminal_paging


class ConfigBackupWorker(QThread):
    """Save selected Huawei, H3C, or Cisco configurations one by one."""

    device_started = Signal(str, int, int)
    device_finished = Signal(str, bool, str, str)
    progress_signal = Signal(int, int)
    finished_signal = Signal(bool, str)

    def __init__(self, devices: list, backup_dir: Path, parent=None):
        super().__init__(parent)
        self.devices = devices
        self.backup_dir = Path(backup_dir)
        self._is_running = True
        self._connection = None

    def stop(self):
        self._is_running = False
        if self._connection:
            try:
                self._connection.disconnect()
            except Exception:
                pass
            self._connection = None

    def _save_one(self, device_config: dict) -> Path:
        device_type = str(device_config.get("device_type", ""))
        command = "show running-config" if device_type.startswith("cisco") else "display current-configuration"
        output = self._connection.send_command(command, read_timeout=120)
        if not output.strip():
            raise ValueError("设备返回的配置内容为空")
        lowered = output.lower()
        error_markers = (
            "% invalid input",
            "% incomplete command",
            "error:",
            "unrecognized command",
        )
        if any(marker in lowered for marker in error_markers):
            raise ValueError("设备返回命令错误，未保存配置")

        host = str(device_config.get("host", "unknown"))
        safe_host = re.sub(r'[<>:"/\\|?*]+', "_", host)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        file_path = self.backup_dir / f"{safe_host}_{timestamp}.cfg"
        file_path.write_text(output.rstrip() + "\n", encoding="utf-8", newline="\n")
        return file_path

    def run(self):
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        total = len(self.devices)
        success_count = 0

        for index, device_config in enumerate(self.devices, 1):
            if not self._is_running:
                break

            host = str(device_config.get("host", "unknown"))
            self.device_started.emit(host, index, total)
            self._connection = None

            try:
                self._connection = ConnectHandler(**device_config)
                disable_terminal_paging(self._connection, device_config)
                file_path = self._save_one(device_config)
                success_count += 1
                self.device_finished.emit(
                    host,
                    True,
                    f"已保存: {file_path.name}",
                    str(file_path),
                )
            except NetMikoAuthenticationException:
                self.device_finished.emit(host, False, "认证失败，请检查用户名和密码", "")
            except NetMikoTimeoutException:
                self.device_finished.emit(host, False, "连接超时，请检查 IP 地址和端口", "")
            except Exception as exc:
                if self._is_running:
                    self.device_finished.emit(host, False, f"保存失败: {exc}", "")
            finally:
                if self._connection:
                    try:
                        self._connection.disconnect()
                    except Exception:
                        pass
                    self._connection = None
                self.progress_signal.emit(index, total)

        if not self._is_running:
            summary = f"配置保存已停止，成功 {success_count}/{total}"
            self.finished_signal.emit(False, summary)
            return

        failed_count = total - success_count
        summary = f"配置保存完成：成功 {success_count} 台，失败 {failed_count} 台"
        self.finished_signal.emit(failed_count == 0, summary)
