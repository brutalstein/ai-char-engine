"""Glue between the Character Brain (engine/selector) and the image providers.

Keeps all ComfyUI specifics out of cli.py: the CLI calls one of these functions.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from ..engine import build_context, render_generation_prompt
from ..selector import infer_tags
from .base import GenerationRequest, GenerationResult
from .codex_builtin import CodexBuiltinProvider
from .router import BackendProbe, select_backend


def _aspect_from_tags(tags: set[str]) -> str:
    if {"full_body", "legs"} & tags:
        return "full_body"
    return "portrait"


def _safe_comfy_probe() -> tuple[BackendProbe, Any]:
    """Never let an un-installed/broken local backend raise into the Brain path."""
    try:
        from .comfyui import ComfyUIProvider

        provider = ComfyUIProvider()
        return provider.probe(), provider
    except Exception:  # noqa: BLE001 - missing config/runtime must degrade, not crash
        return BackendProbe(installed=False), None


def plan_and_generate(
    home: Path,
    character: str,
    request_text: str,
    *,
    budget: str = "balanced",
    backend: str = "auto",
    seed: int | None = None,
    out_dir: Path | None = None,
) -> dict[str, Any]:
    context = build_context(home, character, request_text, budget)
    prompt = render_generation_prompt(context)
    tags = infer_tags(request_text)
    refs = tuple(Path(r["path"]) for r in context.get("references", []))
    details = tuple(
        f"{d.get('kind', 'feature')} at {d.get('location', '')}: {d.get('description', '')}"
        for d in context.get("visible_permanent_details", [])
    )
    req = GenerationRequest(
        character=context["character"],
        prompt=prompt,
        reference_paths=refs,
        visible_permanent_details=details,
        scene_tags=tuple(sorted(tags)),
        aspect=_aspect_from_tags(tags),
        budget=budget,
        seed=seed,
        out_dir=out_dir,
    )

    probe, provider = _safe_comfy_probe()
    chosen, warnings = select_backend(backend, req, probe)

    if chosen == "comfyui" and provider is not None:
        result = provider.generate(req)
        if result.status == "failed" and backend == "auto":
            warnings.append(f"comfyui failed ({result.error}); fell back to Codex image_gen")
            result = CodexBuiltinProvider().generate(req)
    else:
        if chosen == "comfyui":
            warnings.append("comfyui selected but provider unavailable; using Codex image_gen")
        result = CodexBuiltinProvider().generate(req)

    result.warnings = list(warnings) + list(result.warnings)
    return {
        "result": result,
        "context": context,
        "backend_selected": chosen,
        "backend_effective": result.backend,
    }


def result_ledger_row(result: GenerationResult) -> dict[str, Any]:
    """Reproducibility payload for the existing `aice record --validation` slot."""
    return {
        "backend": result.backend,
        "model_id": result.model_id,
        "workflow_version": result.workflow_version,
        "seed": result.seed,
        "duration_s": round(result.duration_s, 2),
        "effective_settings": result.effective_settings,
        "reproducibility": result.reproducibility,
        "warnings": result.warnings,
    }
