from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path
from typing import Any, Callable

LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1", "[::1]"}


class ComfyError(RuntimeError):
    """Any ComfyUI API / workflow failure. Message is kept short and technical."""


class ComfyClient:
    """Minimal stdlib client for the local ComfyUI HTTP API.

    Completion is detected by polling ``/history/{prompt_id}`` rather than a
    websocket, so this stays dependency-free.
    """

    def __init__(self, base_url: str, *, client_id: str | None = None, timeout: float = 10.0):
        parsed = urllib.parse.urlparse(base_url)
        if parsed.scheme not in {"http", ""}:
            raise ValueError(f"ComfyUI URL must be plain http, got {parsed.scheme!r}")
        if (parsed.hostname or "") not in LOCAL_HOSTS:
            raise ValueError(
                f"refusing non-local ComfyUI URL {base_url!r}; only 127.0.0.1 is allowed"
            )
        self.base_url = base_url.rstrip("/")
        self.client_id = client_id or uuid.uuid4().hex
        self.timeout = timeout

    # -- low level --------------------------------------------------------
    def _request(self, method: str, path: str, *, data: bytes | None = None,
                 headers: dict[str, str] | None = None, timeout: float | None = None) -> bytes:
        req = urllib.request.Request(self.base_url + path, data=data, method=method,
                                     headers=headers or {})
        try:
            with urllib.request.urlopen(req, timeout=timeout or self.timeout) as resp:
                return resp.read()
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", "replace")[:400]
            raise ComfyError(f"{method} {path} -> HTTP {exc.code}: {body}") from None
        except (urllib.error.URLError, TimeoutError, ConnectionError, OSError) as exc:
            raise ComfyError(f"{method} {path} -> {exc}") from None

    def _get_json(self, path: str, timeout: float | None = None) -> Any:
        raw = self._request("GET", path, timeout=timeout)
        try:
            return json.loads(raw or b"null")
        except json.JSONDecodeError as exc:
            raise ComfyError(f"GET {path} returned non-JSON: {exc}") from None

    def _post_json(self, path: str, payload: dict[str, Any], timeout: float | None = None) -> Any:
        raw = self._request("POST", path, data=json.dumps(payload).encode("utf-8"),
                            headers={"Content-Type": "application/json"}, timeout=timeout)
        if not raw:
            return None
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return None

    # -- introspection ---------------------------------------------------
    def health(self, timeout: float = 3.0) -> bool:
        try:
            self._get_json("/system_stats", timeout=timeout)
            return True
        except ComfyError:
            return False

    def system_stats(self) -> dict[str, Any]:
        stats = self._get_json("/system_stats")
        return stats if isinstance(stats, dict) else {}

    def object_info_keys(self) -> set[str]:
        info = self._get_json("/object_info")
        return set(info) if isinstance(info, dict) else set()

    # -- generation ----------------------------------------------------
    def upload_image(self, path: Path, *, subfolder: str = "aice", overwrite: bool = True) -> dict[str, str]:
        path = Path(path)
        boundary = "----aice" + uuid.uuid4().hex
        parts: list[bytes] = []

        def field(name: str, value: str) -> None:
            parts.append(
                ("--" + boundary + "\r\nContent-Disposition: form-data; name=\""
                 + name + "\"\r\n\r\n" + value + "\r\n").encode()
            )

        field("type", "input")
        field("subfolder", subfolder)
        field("overwrite", "true" if overwrite else "false")
        parts.append(
            ("--" + boundary + "\r\nContent-Disposition: form-data; name=\"image\"; filename=\""
             + path.name + "\"\r\nContent-Type: application/octet-stream\r\n\r\n").encode()
        )
        parts.append(path.read_bytes())
        parts.append(("\r\n--" + boundary + "--\r\n").encode())
        body = b"".join(parts)
        raw = self._request("POST", "/upload/image", data=body,
                            headers={"Content-Type": "multipart/form-data; boundary=" + boundary},
                            timeout=60.0)
        try:
            info = json.loads(raw)
        except json.JSONDecodeError:
            raise ComfyError("upload/image returned non-JSON") from None
        return {
            "name": info.get("name") or path.name,
            "subfolder": info.get("subfolder", subfolder),
            "type": "input",
        }

    def submit(self, workflow: dict[str, Any]) -> str:
        result = self._post_json("/prompt", {"prompt": workflow, "client_id": self.client_id},
                                 timeout=30.0)
        if not isinstance(result, dict) or "prompt_id" not in result:
            node_errors = result.get("node_errors") if isinstance(result, dict) else None
            raise ComfyError(f"/prompt rejected the workflow: {node_errors or result}")
        return str(result["prompt_id"])

    def history(self, prompt_id: str) -> dict[str, Any] | None:
        data = self._get_json(f"/history/{prompt_id}")
        if isinstance(data, dict) and isinstance(data.get(prompt_id), dict):
            return data[prompt_id]
        return None

    def wait(self, prompt_id: str, *, timeout: float = 300.0, poll: float = 1.0,
             alive: Callable[[], bool] | None = None) -> dict[str, Any]:
        """Block until the prompt has output. ``alive`` optionally reports whether the
        server process is still running so a crash fails fast instead of timing out."""

        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if alive is not None and not alive():
                raise ComfyError("ComfyUI process exited before the job finished")
            entry = self.history(prompt_id)
            if entry is not None:
                status = entry.get("status", {}) or {}
                if status.get("status_str") == "error":
                    raise ComfyError(f"workflow error: {status.get('messages')}")
                if entry.get("outputs"):
                    return entry
            time.sleep(poll)
        raise ComfyError(f"timed out after {timeout:.0f}s waiting for prompt {prompt_id}")

    @staticmethod
    def image_outputs(history_entry: dict[str, Any]) -> list[dict[str, str]]:
        images: list[dict[str, str]] = []
        for node_output in (history_entry.get("outputs") or {}).values():
            for image in node_output.get("images", []) or []:
                if image.get("type") in {"output", "temp"} and image.get("filename"):
                    images.append(image)
        return images

    def fetch_image(self, filename: str, subfolder: str = "", folder_type: str = "output") -> bytes:
        q = urllib.parse.urlencode({"filename": filename, "subfolder": subfolder, "type": folder_type})
        return self._request("GET", f"/view?{q}", timeout=60.0)

    # -- memory / control ---------------------------------------------
    def free(self, *, unload_models: bool = True, free_memory: bool = True) -> None:
        try:
            self._post_json("/free", {"unload_models": unload_models, "free_memory": free_memory},
                            timeout=30.0)
        except ComfyError:
            pass  # best effort

    def interrupt(self) -> None:
        try:
            self._post_json("/interrupt", {}, timeout=10.0)
        except ComfyError:
            pass
