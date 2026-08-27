from __future__ import annotations

import socket
import tempfile
import unittest
from pathlib import Path

from aice.comfy import config as cfgmod
from aice.comfy.client import ComfyError
from aice.comfy.runtime import ComfyRuntime, _pid_alive, _port_open


def _cfg(root: Path) -> dict:
    return {
        "schema_version": 1,
        "runtime_dir": str(root / "ComfyUI"),
        "venv_dir": str(root / "venv"),
        "models_dir": str(root / "models"),
        "log_dir": str(root / "logs"),
        "host": "127.0.0.1",
        "port": 8188,
        "profile": "rtx_generic",
        "validated": False,
        "pins": {},
        "smoke": {},
    }


class RuntimeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.rt = ComfyRuntime(_cfg(self.root))

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_not_installed_by_default(self) -> None:
        self.assertFalse(self.rt.is_installed())

    def test_start_refuses_when_not_installed(self) -> None:
        with self.assertRaises(ComfyError):
            self.rt.start(wait=False)

    def test_stale_pid_is_recovered(self) -> None:
        self.rt.pid_file.parent.mkdir(parents=True, exist_ok=True)
        self.rt.pid_file.write_text("999999999")  # almost certainly dead
        self.assertIsNone(self.rt._read_pid())
        self.assertFalse(self.rt.pid_file.exists())

    def test_garbage_pid_file_is_ignored(self) -> None:
        self.rt.pid_file.parent.mkdir(parents=True, exist_ok=True)
        self.rt.pid_file.write_text("not-a-pid")
        self.assertIsNone(self.rt._read_pid())

    def test_stop_never_kills_unknown_process(self) -> None:
        self.assertFalse(self.rt.stop())

    def test_port_open_detection(self) -> None:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as srv:
            srv.bind(("127.0.0.1", 0))
            srv.listen(1)
            _, port = srv.getsockname()
            self.assertTrue(_port_open("127.0.0.1", port))
        self.assertFalse(_port_open("127.0.0.1", port))

    def test_pid_alive_current_process(self) -> None:
        import os

        self.assertTrue(_pid_alive(os.getpid()))
        self.assertFalse(_pid_alive(999999999))

    def test_start_is_idempotent_when_already_healthy(self) -> None:
        self.rt.health = lambda timeout=3.0: True  # type: ignore[assignment]
        self.rt.start(wait=False)
        self.assertIsNone(self.rt._proc)  # never spawned a process

    def test_status_shape(self) -> None:
        st = self.rt.status()
        for key in ("installed", "pid", "port", "port_open", "healthy", "url", "log"):
            self.assertIn(key, st)
        self.assertEqual(st["url"], "http://127.0.0.1:8188")

    def test_config_never_persists_non_local_host(self) -> None:
        import os

        os.environ["AICE_COMFY_HOME"] = str(self.root / "cfgtest")
        try:
            cfgmod.save_config({**_cfg(self.root), "host": "0.0.0.0"})
            self.assertEqual(cfgmod.load_config()["host"], "127.0.0.1")
        finally:
            os.environ.pop("AICE_COMFY_HOME", None)


if __name__ == "__main__":
    unittest.main()
