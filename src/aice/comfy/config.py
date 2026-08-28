from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from ..utils import atomic_write_json, read_json, utc_now

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8188
SCHEMA_VERSION = 2
KNOWN_CAPABILITIES = ("identity", "bootstrap", "adult_explicit")


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
        # Legacy compatibility: this mirrors identity validation only. New code
        # must use validated_capabilities so optional model stacks cannot inherit
        # an unrelated smoke result.
        "validated": False,
        "validated_capabilities": {},
        "pins": {},
        "smoke": {},
    }


def _migrate_validation(stored: dict[str, Any]) -> dict[str, Any]:
    """Return a capability validation ledger for legacy config files.

    v1 had one global ``validated`` bit. Treat it only as evidence for the base
    identity capability. Optional bootstrap/adult stacks require their own smoke.
    If an old smoke record already contains a successful adult run, preserve it.
    """

    existing = stored.get("validated_capabilities")
    if isinstance(existing, dict):
        return {str(k): dict(v) for k, v in existing.items() if isinstance(v, dict)}

    ledger: dict[str, Any] = {}
    smoke = stored.get("smoke") if isinstance(stored.get("smoke"), dict) else {}
    if bool(stored.get("validated")):
        ledger["identity"] = {
            "ok": True,
            "source": "legacy-global-validation",
            "validated_at": str(smoke.get("at") or utc_now()),
        }
    adult = smoke.get("adult") if isinstance(smoke, dict) else None
    if isinstance(adult, dict) and adult.get("ok") is True:
        ledger["adult_explicit"] = {
            "ok": True,
            "source": "legacy-adult-smoke",
            "validated_at": str(smoke.get("at") or utc_now()),
            "report": dict(adult),
        }
    return ledger


def capability_validation(cfg: dict[str, Any], capability: str) -> dict[str, Any]:
    row = cfg.get("validated_capabilities", {}).get(capability, {})
    return dict(row) if isinstance(row, dict) else {}


def capability_validated(cfg: dict[str, Any], capability: str) -> bool:
    return capability_validation(cfg, capability).get("ok") is True


def set_capability_validation(
    cfg: dict[str, Any], capability: str, report: dict[str, Any], *, source: str = "smoke",
) -> None:
    if capability not in KNOWN_CAPABILITIES:
        raise ValueError(f"unknown ComfyUI capability: {capability}")
    ledger = cfg.setdefault("validated_capabilities", {})
    ledger[capability] = {
        "ok": bool(report.get("ok")),
        "source": source,
        "validated_at": utc_now(),
        "report": dict(report),
    }
    cfg["validated"] = capability_validated(cfg, "identity")


def invalidate_capabilities(cfg: dict[str, Any], capabilities: list[str] | tuple[str, ...], reason: str) -> None:
    ledger = cfg.setdefault("validated_capabilities", {})
    for capability in capabilities:
        if capability not in KNOWN_CAPABILITIES:
            continue
        old = ledger.get(capability, {})
        ledger[capability] = {
            "ok": False,
            "source": "invalidated",
            "invalidated_at": utc_now(),
            "reason": reason,
            **({"previous_validated_at": old.get("validated_at")} if isinstance(old, dict) and old.get("validated_at") else {}),
        }
    cfg["validated"] = capability_validated(cfg, "identity")


def load_config() -> dict[str, Any]:
    cfg = _defaults()
    stored = read_json(config_path())
    if isinstance(stored, dict):
        cfg.update(stored)
        cfg["validated_capabilities"] = _migrate_validation(stored)
        cfg["schema_version"] = SCHEMA_VERSION
        cfg["validated"] = capability_validated(cfg, "identity")
        # env override always wins for the network binding
        if "AICE_COMFY_PORT" in os.environ:
            cfg["port"] = int(os.environ["AICE_COMFY_PORT"])
    cfg["host"] = DEFAULT_HOST  # never allow a persisted non-local host
    return cfg


def save_config(cfg: dict[str, Any]) -> None:
    cfg = dict(cfg)
    cfg["schema_version"] = SCHEMA_VERSION
    cfg["host"] = DEFAULT_HOST
    cfg.setdefault("validated_capabilities", {})
    cfg["validated"] = capability_validated(cfg, "identity")
    atomic_write_json(config_path(), cfg)


def base_url(cfg: dict[str, Any] | None = None) -> str:
    cfg = cfg or load_config()
    return f"http://{cfg['host']}:{int(cfg['port'])}"
