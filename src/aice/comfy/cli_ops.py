"""Thin operations behind `aice comfy <action>` and the doctor backend section.

Codex invokes these; end users never type them.
"""
from __future__ import annotations

import sys
from typing import Any

from . import config as cfgmod
from . import hardware as hwmod
from . import models as modelmod
from . import policy as policymod
from .installer import ComfyInstaller, InstallError
from .runtime import ComfyRuntime
from .workflow import WorkflowAdapter, WorkflowError


def _hw() -> hwmod.HardwareProfile:
    return hwmod.load_cached() or hwmod.detect()


def backend_health() -> dict[str, Any]:
    """Non-fatal local-image-backend section for `aice doctor`."""
    cfg = cfgmod.load_config()
    rt = ComfyRuntime(cfg)
    hw = _hw()
    profile = policymod.profile_for(hw)
    installed = rt.is_installed()
    missing = modelmod.missing_required(rt.models_dir) if installed else None
    if not installed:
        state = "unavailable"
    elif missing or not cfg.get("validated"):
        state = "degraded"
    else:
        state = "available"
    return {
        "state": state,
        "installed": installed,
        "validated": bool(cfg.get("validated")),
        "gpu": hw.gpu_name or None,
        "vram_total_mb": hw.vram_total_mb or None,
        "is_blackwell": hw.is_blackwell,
        "hardware_profile": profile.name,
        "default_model": profile.default_model,
        "missing_models": missing,
        "runtime_dir": str(rt.runtime_dir),
        "url": rt.base_url,
    }


def status() -> dict[str, Any]:
    cfg = cfgmod.load_config()
    rt = ComfyRuntime(cfg)
    return {"config": cfgmod.config_path().as_posix(), "pins": cfg.get("pins", {}),
            "profile": cfg.get("profile"), "validated": cfg.get("validated", False),
            **rt.status()}


def start() -> dict[str, Any]:
    rt = ComfyRuntime()
    return rt.start(policymod.server_args(_hw()), wait=True)


def stop() -> dict[str, Any]:
    return {"stopped": ComfyRuntime().stop()}


def setup(*, model_keys: list[str] | None = None, verbose: bool = True) -> dict[str, Any]:
    log = (lambda m: print(m, file=sys.stderr)) if verbose else None

    def mp(key: str, done: int, total: int) -> None:
        if total and (done == total or done % (256 * 1024 * 1024) < 4 * 1024 * 1024):
            pct = 100 * done // total if total else 0
            print(f"  {key}: {pct}% ({done // (1024*1024)}/{total // (1024*1024)} MB)", file=sys.stderr)

    try:
        return ComfyInstaller().setup(model_keys=model_keys, log=log, model_progress=mp)
    except InstallError as exc:
        return {"ok": False, "error": str(exc)}


def doctor(*, smoke: bool = False) -> dict[str, Any]:
    """Strict backend diagnostics; optional real GPU smoke test."""
    cfg = cfgmod.load_config()
    rt = ComfyRuntime(cfg)
    hw = _hw()
    report: dict[str, Any] = {
        "backend": backend_health(),
        "hardware": hw.as_dict(),
        "runtime": rt.status(),
    }
    checks: list[dict[str, Any]] = []

    def check(name: str, ok: bool, detail: str = "") -> None:
        checks.append({"check": name, "ok": bool(ok), "detail": detail})

    check("gpu_detected", hw.has_gpu, hw.gpu_name)
    check("blackwell", hw.is_blackwell, hw.driver)
    check("runtime_installed", rt.is_installed(), str(rt.runtime_dir))
    inst = ComfyInstaller(cfg)
    ts = inst.torch_status()
    check("torch_cuda", bool(ts.get("cuda")), f"{ts.get('v', '?')} cuda={ts.get('cuda', '?')} avail={ts.get('avail')}")
    missing = modelmod.missing_required(rt.models_dir) if rt.is_installed() else ["*"]
    check("required_models", not missing, ", ".join(missing) if missing else "present")
    check("localhost_only", rt.host == "127.0.0.1", rt.base_url)

    if rt.is_installed() and rt.health(timeout=3):
        try:
            keys = rt.client().object_info_keys()
            wf = WorkflowAdapter("qwen_edit_identity")
            wf.validate(keys)
            check("workflow_nodes", True, f"v{wf.version}")
        except (WorkflowError, Exception) as exc:  # noqa: BLE001
            check("workflow_nodes", False, str(exc))

    if smoke:
        report["smoke"] = _smoke_test(rt, hw)
        cfg["validated"] = bool(report["smoke"].get("ok"))
        cfg["smoke"] = report["smoke"]
        winner = report["smoke"].get("winner")
        if winner:
            cfg["tuned"] = {"default_model": winner,
                            "measured_at": report["smoke"].get("at")}
        cfgmod.save_config(cfg)

    report["checks"] = checks
    report["ok"] = all(c["ok"] for c in checks)
    return report


# Cold-start ceiling: first gen pays model load + CPU-offload staging. Warm gens
# on a kept-alive server are far quicker; past this the default is not viable here.
_SMOKE_LATENCY_CEILING_S = 420.0


def _smoke_test(rt: ComfyRuntime, hw: hwmod.HardwareProfile) -> dict[str, Any]:
    """Real GPU generation + a bounded auto-tune: run the profile default, and if
    it fails or is too slow, try the tight-VRAM model. Records both, picks a winner."""
    import tempfile
    import time
    from pathlib import Path

    from ..providers.base import GenerationRequest
    from ..providers.comfyui import ComfyUIProvider

    profile = policymod.profile_for(hw)
    candidates: list[str] = [profile.default_model]
    if profile.low_vram_model != profile.default_model:
        candidates.append(profile.low_vram_model)

    attempts: dict[str, Any] = {}
    winner: str | None = None

    specs = modelmod.model_specs()
    with tempfile.TemporaryDirectory() as td:
        ref = Path(td) / "smoke_ref.png"
        ref.write_bytes(_tiny_png())
        for key in candidates:
            spec = specs.get(key)
            if not spec or not modelmod.verify(spec.dest(rt.models_dir), spec)[0]:
                attempts[key] = {"ok": False, "status": "absent",
                                 "error": f"{key} not downloaded (run `aice comfy setup`)"}
                continue
            out = Path(td) / f"out_{key}"
            req = GenerationRequest(
                character="smoke", prompt="a natural candid photo of a person, soft daylight",
                reference_paths=(ref,), aspect="portrait", budget="balanced", seed=1234,
                out_dir=out,
            )
            t0 = time.monotonic()
            try:
                cfg = cfgmod.load_config()
                cfg["tuned"] = {"default_model": key}  # force this candidate for the run
                result = ComfyUIProvider(config=cfg, hardware=hw).generate(req)
                dt = round(time.monotonic() - t0, 1)
                ok = result.status == "ok" and result.output_path is not None
                attempts[key] = {
                    "ok": ok, "status": result.status, "error": result.error,
                    "duration_s": dt,
                    "resolution": [result.effective_settings.get("width"),
                                   result.effective_settings.get("height")],
                    "output_bytes": (result.output_path.stat().st_size
                                     if result.output_path and result.output_path.exists() else 0),
                }
            except Exception as exc:  # noqa: BLE001
                attempts[key] = {"ok": False, "status": "crash", "error": repr(exc),
                                 "duration_s": round(time.monotonic() - t0, 1)}
            finally:
                try:
                    rt.client().free()
                    time.sleep(3)
                except Exception:  # noqa: BLE001
                    pass
            a = attempts[key]
            if a["ok"] and a["duration_s"] <= _SMOKE_LATENCY_CEILING_S:
                winner = key
                break  # default (or first) is good enough; no need to try smaller

    if winner is None:  # nothing beat the ceiling; take the fastest that made an image
        made = [(a["duration_s"], k) for k, a in attempts.items() if a["ok"]]
        winner = min(made)[1] if made else None

    best = attempts.get(winner, {}) if winner else {}
    return {
        "ok": winner is not None,
        "winner": winner,
        "gpu": hw.gpu_name,
        "vram_total_mb": hw.vram_total_mb,
        "status": best.get("status", "failed"),
        "error": best.get("error", "") or "; ".join(
            f"{k}: {a.get('error')}" for k, a in attempts.items() if a.get("error")),
        "model_id": winner or "",
        "seed": 1234,
        "resolution": best.get("resolution"),
        "duration_s": best.get("duration_s"),
        "output_bytes": best.get("output_bytes", 0),
        "attempts": attempts,
        "at": _utc(),
    }


def _utc() -> str:
    import time
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _tiny_png(size: int = 64, grey: int = 127) -> bytes:
    """A small valid RGB PNG, built with stdlib only (aice core has no Pillow),
    used as the throwaway reference for the smoke generation."""
    import struct
    import zlib

    def chunk(tag: bytes, data: bytes) -> bytes:
        return (struct.pack(">I", len(data)) + tag + data
                + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF))

    ihdr = struct.pack(">IIBBBBB", size, size, 8, 2, 0, 0, 0)  # 8-bit truecolour
    row = b"\x00" + bytes((grey, grey, grey)) * size
    return (b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", ihdr)
            + chunk(b"IDAT", zlib.compress(row * size, 9))
            + chunk(b"IEND", b""))
