"""
CMD 命令执行线程，避免网络命令阻塞工具箱界面。
"""
import locale
import os
import subprocess
import threading

from PySide6.QtCore import QThread, Signal

CREATE_NO_WINDOW = 0x08000000


class CmdWorker(QThread):
    output_signal = Signal(str)
    finished_signal = Signal(bool, str)

    def __init__(self, command: str, timeout: int = 60, parent=None):
        super().__init__(parent)
        self.command = command
        self.timeout = timeout
        self._process = None
        self._reader = None
        self._stop_requested = False

    def stop(self):
        self._stop_requested = True
        if self._process and self._process.poll() is None:
            try:
                self._process.terminate()
            except Exception:
                pass
            try:
                self._process.kill()
            except Exception:
                pass

    def _read_stdout(self, stream):
        try:
            for line in stream:
                self.output_signal.emit(line)
        except Exception:
            pass
        finally:
            try:
                stream.close()
            except Exception:
                pass

    def run(self):
        encoding = locale.getpreferredencoding(False) or "gbk"
        creationflags = CREATE_NO_WINDOW if os.name == "nt" else 0
        try:
            self._process = subprocess.Popen(
                ["cmd", "/c", self.command],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding=encoding,
                errors="replace",
                creationflags=creationflags,
            )
            self._reader = threading.Thread(
                target=self._read_stdout,
                args=(self._process.stdout,),
                daemon=True,
            )
            self._reader.start()

            timed_out = False
            try:
                self._process.wait(timeout=self.timeout)
            except subprocess.TimeoutExpired:
                timed_out = True
                self.stop()
                try:
                    self._process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    self._process.kill()

            if self._reader:
                self._reader.join(timeout=5)

            code = self._process.returncode
            if timed_out:
                self.finished_signal.emit(False, f"命令执行超时（{self.timeout}秒）")
            elif self._stop_requested:
                self.finished_signal.emit(False, "命令已停止")
            else:
                self.finished_signal.emit(True, f"命令执行完成，退出码 {code}")
        except FileNotFoundError:
            self.finished_signal.emit(False, "无法启动 cmd，请检查系统环境")
        except Exception as exc:
            self.finished_signal.emit(False, f"命令执行失败: {exc}")
