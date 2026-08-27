from __future__ import annotations

import os
import signal
import socket
import subprocess
import time
from pathlib import Path
from typing import Any

from . import config as cfgmod
from .client import ComfyClient, ComfyError

_WINDOWS = os.name == "nt"


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if _WINDOWS:
        out = subprocess.run(
            ["tasklist", "/FI", f"PID eq {pid}", "/NH", "/FO", "CSV"],
            capture_output=True, text=True,
        )
        return f'"{pid}"' in out.stdout
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _port_open(host: str, port: int, timeout: float = 0.5) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(timeout)
        return sock.connect_ex((host, port)) == 0


class ComfyRuntime:
    """Owns exactly one AICE-managed ComfyUI server process.

    Never touches a process it did not start (PID is tracked in a file); never kills
    by image name; localhost only.
    """

    def __init__(self, config: dict[str, Any] | None = None):
        self.cfg = config or cfgmod.load_config()
        self.home = cfgmod.comfy_home()
        self.runtime_dir = Path(self.cfg["runtime_dir"])
        self.venv_dir = Path(self.cfg["venv_dir"])
        self.models_dir = Path(self.cfg["models_dir"])
        self.log_dir = Path(self.cfg["log_dir"])
        self.host = cfgmod.DEFAULT_HOST
        self.port = int(self.cfg["port"])
        self.pid_file = self.home / "comfy.pid"
        self.log_file = self.log_dir / "comfy-server.log"
        self._proc: subprocess.Popen | None = None

    # -- paths / state -------------------------------------------------
    @property
    def base_url(self) -> str:
        return f"http://{self.host}:{self.port}"

    @property
    def main_py(self) -> Path:
        return self.runtime_dir / "main.py"

    @property
    def server_python(self) -> Path:
        return self.venv_dir / ("Scripts/python.exe" if _WINDOWS else "bin/python")

    def is_installed(self) -> bool:
        return self.main_py.is_file() and self.server_python.is_file()

    def client(self) -> ComfyClient:
        return ComfyClient(self.base_url)

    def health(self, timeout: float = 3.0) -> bool:
        try:
            return self.client().health(timeout=timeout)
        except ValueError:
            return False

    def _read_pid(self) -> int | None:
        try:
            pid = int(self.pid_file.read_text().strip())
        except (FileNotFoundError, ValueError):
            return None
        if _pid_alive(pid):
            return pid
        self.pid_file.unlink(missing_ok=True)  # stale pid recovery
        return None

    def _write_pid(self, pid: int) -> None:
        self.pid_file.parent.mkdir(parents=True, exist_ok=True)
        self.pid_file.write_text(str(pid))

    def status(self) -> dict[str, Any]:
        pid = self._read_pid()
        port_open = _port_open(self.host, self.port)
        return {
            "installed": self.is_installed(),
            "pid": pid,
            "port": self.port,
            "port_open": port_open,
            "healthy": self.health(timeout=2.0) if port_open else False,
            "url": self.base_url,
            "log": str(self.log_file),
        }

    # -- lifecycle ----------------------------------------------------
    def start(self, policy_args: tuple[str, ...] = (), *, wait: bool = True,
              timeout: float = 240.0) -> dict[str, Any]:
        if self.health(timeout=2.0):
            return self.status()  # idempotent: already up
        if not self.is_installed():
            raise ComfyError(
                f"ComfyUI runtime is not installed at {self.runtime_dir} (run `aice comfy setup`)"
            )
        if self._read_pid() is not None:
            if wait:
                self._wait_ready(timeout)
            return self.status()
        if _port_open(self.host, self.port):
            raise ComfyError(
                f"port {self.port} is already in use by another process; set AICE_COMFY_PORT"
            )

        self.log_dir.mkdir(parents=True, exist_ok=True)
        args = [
            str(self.server_python), "-s", str(self.main_py),
            "--listen", self.host, "--port", str(self.port),
            "--disable-auto-launch",
            "--output-directory", str(self.home / "output"),
            "--temp-directory", str(self.home / "temp"),
            *policy_args,
        ]
        kwargs: dict[str, Any] = {"cwd": str(self.runtime_dir)}
        if _WINDOWS:
            kwargs["creationflags"] = 0x00000008 | 0x00000200  # DETACHED_PROCESS | NEW_PROCESS_GROUP
        else:
            kwargs["start_new_session"] = True
        log = open(self.log_file, "ab", buffering=0)
        log.write(f"\n=== aice start {time.strftime('%Y-%m-%dT%H:%M:%S')} ===\n".encode())
        self._proc = subprocess.Popen(args, stdout=log, stderr=subprocess.STDOUT, **kwargs)
        self._write_pid(self._proc.pid)
        if wait:
            self._wait_ready(timeout)
        return self.status()

    def _wait_ready(self, timeout: float) -> None:
        deadline = time.monotonic() + timeout
        proc = self._proc
        while time.monotonic() < deadline:
            if proc is not None and proc.poll() is not None:
                raise ComfyError(
                    f"ComfyUI exited during startup (code {proc.returncode}).\n{self.log_tail()}"
                )
            if self.health(timeout=2.0):
                return
            time.sleep(1.5)
        raise ComfyError(f"ComfyUI did not become healthy within {timeout:.0f}s.\n{self.log_tail()}")

    def stop(self, timeout: float = 15.0) -> bool:
        pid = self._read_pid()
        if pid is None:
            return False  # nothing we own; never kill a process we did not start
        try:
            if _WINDOWS:
                subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"],
                               capture_output=True, text=True)
            else:
                try:
                    os.killpg(os.getpgid(pid), signal.SIGTERM)
                except ProcessLookupError:
                    pass
                end = time.monotonic() + timeout
                while _pid_alive(pid) and time.monotonic() < end:
                    time.sleep(0.3)
                if _pid_alive(pid):
                    os.killpg(os.getpgid(pid), signal.SIGKILL)
        finally:
            self.pid_file.unlink(missing_ok=True)
            self._proc = None
        return True

    def restart(self, policy_args: tuple[str, ...] = (), *, timeout: float = 240.0) -> dict[str, Any]:
        self.stop()
        time.sleep(1.0)
        return self.start(policy_args, wait=True, timeout=timeout)

    def system_stats(self) -> dict[str, Any]:
        return self.client().system_stats()

    def alive(self) -> bool:
        if self._proc is not None:
            return self._proc.poll() is None
        return self._read_pid() is not None

    def log_tail(self, lines: int = 40) -> str:
        try:
            data = self.log_file.read_text("utf-8", "replace").splitlines()
        except FileNotFoundError:
            return "(no log yet)"
        return "\n".join(data[-lines:])


def default_runtime() -> ComfyRuntime:
    return ComfyRuntime()


__all__ = ["ComfyRuntime", "default_runtime", "_pid_alive", "_port_open"]
