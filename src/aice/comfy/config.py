from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from ..utils import atomic_write_json, read_json

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8188
SCHEMA_VERSION = 1


def comfy_home() -> Path:
    """Root for the AICE-managed ComfyUI runtime, venv, models and logs.

    Kept separate from the character-state ``.aice/`` (which is cwd-relative) so the
    heavy runtime lives at a stable per-user path, outside any synced folder.
    """

    raw = os.environ.get("AICE_COMFY_HOME")
    if raw:
        return Path(raw).expanduser().resolve()
    return (Path.home() / ".aice" / "runtime").resolve()


def config_path() -> Path:
    return comfy_home() / "comfy.json"


def _defaults() -> dict[str, Any]:
    home = comfy_home()
    port = int(os.environ.get("AICE_COMFY_PORT", DEFAULT_PORT))
    return {
        "schema_version": SCHEMA_VERSION,
        "runtime_dir": str(home / "ComfyUI"),
        "venv_dir": str(home / "venv"),
        "models_dir": str(home / "models"),
        "log_dir": str(home / "logs"),
        "host": DEFAULT_HOST,
        "port": port,
        "profile": "rtx_generic",
        "validated": False,
        "pins": {},
        "smoke": {},
    }


def load_config() -> dict[str, Any]:
    cfg = _defaults()
    stored = read_json(config_path())
    if isinstance(stored, dict):
        cfg.update(stored)
        # env override always wins for the network binding
        if "AICE_COMFY_PORT" in os.environ:
            cfg["port"] = int(os.environ["AICE_COMFY_PORT"])
    cfg["host"] = DEFAULT_HOST  # never allow a persisted non-local host
    return cfg


def save_config(cfg: dict[str, Any]) -> None:
    cfg = dict(cfg)
    cfg["schema_version"] = SCHEMA_VERSION
    cfg["host"] = DEFAULT_HOST
    atomic_write_json(config_path(), cfg)


def base_url(cfg: dict[str, Any] | None = None) -> str:
    cfg = cfg or load_config()
    return f"http://{cfg['host']}:{int(cfg['port'])}"
