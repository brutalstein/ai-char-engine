from __future__ import annotations

import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from aice.comfy.client import ComfyClient, ComfyError


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):  # silence
        pass

    def _send(self, code: int, obj) -> None:
        body = obj if isinstance(obj, bytes) else json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        s = self.server
        if self.path == "/system_stats":
            return self._send(200, {"system": {"comfyui_version": "0.3.70"},
                                    "devices": [{"name": "cuda:0 NVIDIA GeForce RTX 5070 Laptop GPU",
                                                 "vram_total": 8531214336, "vram_free": 6012534784}]})
        if self.path.startswith("/history/"):
            pid = self.path.rsplit("/", 1)[-1]
            return self._send(200, {pid: s.history[pid]} if pid in s.history else {})
        if self.path.startswith("/view"):
            return self._send(200, b"\x89PNG\r\n\x1a\nFAKEIMAGE")
        if self.path == "/object_info":
            return self._send(200, {k: {} for k in s.nodes})
        if self.path == "/not-json":
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"<html>not json</html>")
            return
        return self._send(404, {"error": "nope"})

    def do_POST(self):
        s = self.server
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length)
        if self.path == "/prompt":
            if s.reject_prompt:
                return self._send(200, {"error": "bad", "node_errors": {"3": "missing input"}})
            pid = "pid-123"
            s.history[pid] = {"status": {"status_str": "success", "completed": True},
                              "outputs": {"60": {"images": [
                                  {"filename": "AICE_00001_.png", "subfolder": "", "type": "output"}]}}}
            return self._send(200, {"prompt_id": pid, "number": 1})
        if self.path == "/upload/image":
            text = raw.decode("latin-1")
            name = text.split('filename="', 1)[1].split('"', 1)[0]
            s.uploaded.append(name)
            return self._send(200, {"name": name, "subfolder": "aice", "type": "input"})
        if self.path == "/free":
            s.freed = True
            return self._send(200, {})
        if self.path == "/interrupt":
            return self._send(200, {})
        return self._send(404, {"error": "nope"})


class _Server(ThreadingHTTPServer):
    def __init__(self):
        super().__init__(("127.0.0.1", 0), _Handler)
        self.history: dict = {}
        self.uploaded: list[str] = []
        self.reject_prompt = False
        self.freed = False
        self.nodes = ["UnetLoaderGGUF", "CLIPLoader", "KSampler"]


class ClientTests(unittest.TestCase):
    def setUp(self) -> None:
        self.srv = _Server()
        self.t = threading.Thread(target=self.srv.serve_forever, daemon=True)
        self.t.start()
        _, port = self.srv.server_address
        self.url = f"http://127.0.0.1:{port}"
        self.c = ComfyClient(self.url, timeout=5.0)

    def tearDown(self) -> None:
        self.srv.shutdown()
        self.srv.server_close()

    def test_rejects_non_local_url(self) -> None:
        with self.assertRaises(ValueError):
            ComfyClient("http://10.0.0.5:8188")
        with self.assertRaises(ValueError):
            ComfyClient("https://127.0.0.1:8188")

    def test_health(self) -> None:
        self.assertTrue(self.c.health())
        dead = ComfyClient("http://127.0.0.1:1")
        self.assertFalse(dead.health(timeout=0.5))

    def test_system_stats_vram(self) -> None:
        self.assertIn("devices", self.c.system_stats())

    def test_submit_and_wait_happy_path(self) -> None:
        pid = self.c.submit({"3": {"class_type": "KSampler", "inputs": {}}})
        entry = self.c.wait(pid, timeout=5, poll=0.05)
        images = ComfyClient.image_outputs(entry)
        self.assertEqual(images[0]["filename"], "AICE_00001_.png")
        self.assertEqual(self.c.fetch_image(filename=images[0]["filename"])[:4], b"\x89PNG")

    def test_submit_rejected_raises(self) -> None:
        self.srv.reject_prompt = True
        with self.assertRaises(ComfyError):
            self.c.submit({"bad": {}})

    def test_wait_times_out(self) -> None:
        with self.assertRaises(ComfyError) as ctx:
            self.c.wait("missing-pid", timeout=0.4, poll=0.05)
        self.assertIn("timed out", str(ctx.exception))

    def test_wait_fails_fast_when_process_dead(self) -> None:
        with self.assertRaises(ComfyError) as ctx:
            self.c.wait("missing-pid", timeout=10, poll=0.05, alive=lambda: False)
        self.assertIn("exited", str(ctx.exception))

    def test_non_json_response_is_comfy_error(self) -> None:
        with self.assertRaises(ComfyError):
            self.c._get_json("/not-json")

    def test_upload_image_roundtrip(self) -> None:
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "ref.png"
            p.write_bytes(b"\x89PNG\r\n\x1a\n" + b"0" * 32)
            info = self.c.upload_image(p)
        self.assertEqual(info["name"], "ref.png")
        self.assertEqual(info["type"], "input")
        self.assertIn("ref.png", self.srv.uploaded)

    def test_free_is_best_effort(self) -> None:
        self.c.free()
        self.assertTrue(self.srv.freed)


if __name__ == "__main__":
    unittest.main()
