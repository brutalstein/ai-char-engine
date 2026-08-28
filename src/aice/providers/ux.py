from __future__ import annotations

from pathlib import Path
from typing import Any

from ..storage import get_backend_preference, load_profile
from .router import BackendProbe, comfy_ready


BACKEND_LABELS = {
    "auto": "Choose and combine intelligently",
    "comfyui": "Local ComfyUI",
    "codex_builtin": "Codex image generation",
    "ask_each_time": "Ask me each time",
}


def safe_comfy_probe() -> tuple[BackendProbe, Any | None]:
    """Probe the optional local backend without letting it break conversation flow."""
    try:
        from .comfyui import ComfyUIProvider

        provider = ComfyUIProvider()
        return provider.probe(), provider
    except Exception:  # noqa: BLE001 - optional backend must degrade cleanly
        return BackendProbe(installed=False), None


def backend_dialog(preference: str, probe: BackendProbe) -> dict[str, Any]:
    """Pure conversational backend decision.

    `auto` is intentionally more than fallback routing: AICE chooses the best primary
    engine for the operation and may permit the other engine for one justified repair
    or reference-expansion stage after validation. It never spends an extra call just
    because two engines exist.
    """
    preference = preference if preference in BACKEND_LABELS or preference == "unset" else "unset"
    local_ready, local_reason = comfy_ready(probe)
    available = ["codex_builtin"]
    if local_ready:
        available.insert(0, "comfyui")

    base: dict[str, Any] = {
        "preference": preference,
        "local_ready": local_ready,
        "local_reason": local_reason,
        "available": available,
        "recommended": "auto" if local_ready else "codex_builtin",
        "auto_is_capability_aware": True,
        "needs_user_choice": False,
    }

    if preference in {"unset", "ask_each_time"} and local_ready:
        return {
            **base,
            "stage": "choose_backend",
            "needs_user_choice": True,
            "user_message": (
                "Both image engines are ready. Do you want local ComfyUI, Codex image generation, "
                "or should I choose and combine them intelligently when useful? I can also ask each time."
            ),
            "choices": [
                {"value": "auto", "label": BACKEND_LABELS["auto"]},
                {"value": "comfyui", "label": BACKEND_LABELS["comfyui"]},
                {"value": "codex_builtin", "label": BACKEND_LABELS["codex_builtin"]},
                {"value": "ask_each_time", "label": BACKEND_LABELS["ask_each_time"]},
            ],
        }

    if preference == "comfyui" and not local_ready:
        return {
            **base,
            "stage": "backend_attention",
            "needs_user_choice": True,
            "user_message": (
                "Your saved preference is local ComfyUI, but the local image backend is not ready right now. "
                "I can set up or repair local generation, or use Codex image generation for this request if you prefer."
            ),
            "choices": [
                {"value": "repair_comfyui", "label": "Set up / repair local ComfyUI"},
                {"value": "codex_builtin_once", "label": "Use Codex image generation this time"},
                {"value": "codex_builtin", "label": "Switch to Codex image generation"},
                {"value": "auto", "label": "Switch to intelligent automatic mode"},
            ],
        }

    effective = preference
    if preference in {"unset", "ask_each_time"}:
        effective = "codex_builtin"
    elif preference == "auto":
        effective = "auto" if local_ready else "codex_builtin"

    return {
        **base,
        "stage": "ready",
        "effective": effective,
        "user_message": "Character is ready. Tell me the photo you want in ordinary language.",
        "choices": [],
    }


def backend_status(home: Path, character: str, *, probe: BackendProbe | None = None) -> dict[str, Any]:
    _, profile = load_profile(home, character)
    if probe is None:
        probe, _ = safe_comfy_probe()
    return backend_dialog(get_backend_preference(profile), probe)
