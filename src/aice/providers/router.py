from __future__ import annotations

from dataclasses import dataclass

from .base import GenerationRequest

VALID_MODES = ("auto", "comfyui", "codex_builtin")


@dataclass(frozen=True)
class BackendProbe:
    """Raw facts about the local backend. Gathered by comfy.runtime / comfy.models;
    the router turns them into a decision without any I/O of its own."""

    installed: bool = False
    configured: bool = False
    validated: bool = False  # a real GPU smoke test has passed at least once
    models_present: bool = False
    nodes_present: bool = False
    server_ok: bool = False  # server answers /system_stats right now
    can_start: bool = True  # runtime believes a lazy start would succeed
    free_vram_mb: int | None = None  # None = unknown (server down); checked post-start
    vram_floor_mb: int = 3500


def comfy_ready(p: BackendProbe) -> tuple[bool, str]:
    if not p.installed:
        return False, "not installed"
    if not p.configured:
        return False, "not configured"
    if not p.validated:
        return False, "not validated (local smoke test has not passed)"
    if not p.models_present:
        return False, "required model files missing"
    if not p.nodes_present:
        return False, "required custom node missing"
    if not (p.server_ok or p.can_start):
        return False, "server unhealthy and cannot start"
    if p.free_vram_mb is not None and p.free_vram_mb < p.vram_floor_mb:
        return False, f"insufficient free VRAM ({p.free_vram_mb}MB < {p.vram_floor_mb}MB)"
    return True, "ready"


def select_backend(
    mode: str, req: GenerationRequest, probe: BackendProbe
) -> tuple[str, list[str]]:
    """Return (backend_name, warnings). Never raises for a bad mode -> defaults to auto.

    The caller (cli `comfy generate`) is responsible for the runtime fallback: if the
    chosen backend is comfyui and it errors at generation time, retry codex_builtin
    unless the user explicitly forced comfyui.
    """

    mode = mode if mode in VALID_MODES else "auto"
    ready, why = comfy_ready(probe)

    if mode == "codex_builtin":
        return "codex_builtin", []
    if mode == "comfyui":
        if ready:
            return "comfyui", []
        return "comfyui", [f"comfyui forced but {why}"]
    # auto
    if ready:
        return "comfyui", []
    return "codex_builtin", [f"local backend unavailable ({why}); using Codex built-in image_gen"]
