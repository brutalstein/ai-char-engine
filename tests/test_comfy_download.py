from __future__ import annotations

import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from tempfile import TemporaryDirectory

from aice.comfy.models import ModelSpec, download

_PAYLOAD = bytes(range(256)) * 400  # 102_400 bytes, deterministic


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, *_a):  # quiet
        pass

    def do_GET(self):  # noqa: N802
        s = self.server
        start = 0
        rng = self.headers.get("Range")
        if rng and rng.startswith("bytes="):
            start = int(rng.split("=")[1].split("-")[0])
        s.calls += 1
        body = _PAYLOAD[start:]
        # First response for a fresh (non-range) pull is truncated then cut off.
        if s.calls == 1 and start == 0:
            body = body[: len(_PAYLOAD) // 3]
        if start:
            self.send_response(206)
            self.send_header("Content-Range", f"bytes {start}-{len(_PAYLOAD)-1}/{len(_PAYLOAD)}")
        else:
            self.send_response(200)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class _Server(ThreadingHTTPServer):
    def __init__(self):
        super().__init__(("127.0.0.1", 0), _Handler)
        self.calls = 0


class DownloadResumeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.srv = _Server()
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.port = self.srv.server_address[1]

    def tearDown(self) -> None:
        self.srv.shutdown()
        self.srv.server_close()

    def _spec(self) -> ModelSpec:
        return ModelSpec(
            key="t", filename="t.bin", dest_subdir=".",
            url=f"http://127.0.0.1:{self.port}/t.bin",
            size_bytes=len(_PAYLOAD), sha256=None, license="Apache-2.0", required=True,
        )

    def test_resumes_after_early_stream_close(self) -> None:
        with TemporaryDirectory() as td:
            dest = Path(td) / "t.bin"
            out = download(self._spec(), dest, check_hash=False)
            self.assertEqual(out.read_bytes(), _PAYLOAD)
            self.assertFalse(dest.with_suffix(".bin.part").exists())
            self.assertGreaterEqual(self.srv.calls, 2)  # needed a resume

    def test_noop_when_already_complete(self) -> None:
        with TemporaryDirectory() as td:
            dest = Path(td) / "t.bin"
            dest.write_bytes(_PAYLOAD)
            download(self._spec(), dest, check_hash=False)
            self.assertEqual(self.srv.calls, 0)


if __name__ == "__main__":
    unittest.main()
