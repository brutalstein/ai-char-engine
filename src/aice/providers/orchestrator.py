"""Glue between the Character Brain (engine/selector) and image providers.

The orchestrator owns backend choice/fallback semantics, but never visual judgement.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from ..engine import build_context, render_generation_prompt
from ..selector import infer_tags
from ..storage import get_backend_preference, load_profile
from .base import GenerationRequest, GenerationResult, ProgressCallback
from .codex_builtin import CodexBuiltinProvider
from .router import select_backend
from .ux import backend_dialog, safe_comfy_probe


def _aspect_from_tags(tags: set[str]) -> str:
    if {"full_body", "legs"} & tags:
        return "full_body"
    return "portrait"


def _preference_mode(preference: str, dialog: dict[str, Any]) -> str | None:
    if dialog.get("needs_user_choice"):
        return None
    if preference == "auto":
        return "auto"
    if preference in {"comfyui", "codex_builtin"}:
        return preference
    return str(dialog.get("effective") or "codex_builtin")


def plan_and_generate(
    home: Path,
    character: str,
    request_text: str,
    *,
    budget: str = "balanced",
    backend: str | None = None,
    seed: int | None = None,
    out_dir: Path | None = None,
    progress: ProgressCallback | None = None,
) -> dict[str, Any]:
    trace: list[dict[str, Any]] = []

    def report(event: dict[str, Any]) -> None:
        trace.append(dict(event))
        if progress is not None:
            progress(dict(event))

    context = build_context(home, character, request_text, budget)
    report({"stage": "context_compiled", "reference_count": len(context.get("references", []))})
    prompt = render_generation_prompt(context)
    tags = infer_tags(request_text)
    ref_rows = context.get("references", [])
    refs = tuple(Path(r["path"]) for r in ref_rows)
    details = tuple(
        f"{d.get('kind', 'feature')} at {d.get('location', '')}: {d.get('description', '')}"
        for d in context.get("visible_permanent_details", [])
    )
    req = GenerationRequest(
        character=context["character"],
        prompt=prompt,
        reference_paths=refs,
        reference_ids=tuple(str(r.get("id", "")) for r in ref_rows),
        reference_roles=tuple(str(r.get("role", "")) for r in ref_rows),
        reference_tiers=tuple(str(r.get("tier", "")) for r in ref_rows),
        visible_permanent_details=details,
        scene_tags=tuple(sorted(tags)),
        aspect=_aspect_from_tags(tags),
        budget=budget,
        seed=seed,
        out_dir=out_dir,
    )

    probe, provider = safe_comfy_probe()
    _, profile = load_profile(home, character)
    preference = get_backend_preference(profile)
    dialog = backend_dialog(preference, probe)

    if backend is None:
        mode = _preference_mode(preference, dialog)
        if mode is None:
            report({"stage": "backend_choice_required", "preference": preference})
            result = GenerationResult(
                backend="",
                status="needs_backend_choice",
                error="Image backend choice is required before generation.",
            )
            return {
                "result": result,
                "context": context,
                "backend_selected": None,
                "backend_effective": None,
                "backend_dialog": dialog,
                "trace": trace,
            }
    else:
        mode = backend

    chosen, warnings = select_backend(mode, req, probe)
    report({"stage": "backend_selected", "requested": mode, "backend": chosen})

    if chosen == "comfyui" and provider is not None:
        result = provider.generate(req, progress=report)
        if result.status == "failed" and mode == "auto":
            warnings.append(f"comfyui failed ({result.error}); fell back to Codex image_gen")
            report({"stage": "fallback_planned", "from": "comfyui", "to": "codex_builtin"})
            result = CodexBuiltinProvider().generate(req, progress=report)
    else:
        if chosen == "comfyui":
            warnings.append("comfyui selected but provider unavailable")
            if mode != "auto":
                report({"stage": "provider_failed", "backend": "comfyui", "error": "provider unavailable"})
                result = GenerationResult(
                    backend="comfyui",
                    status="failed",
                    error="Local ComfyUI was explicitly selected but is unavailable.",
                )
            else:
                report({"stage": "fallback_planned", "from": "comfyui", "to": "codex_builtin"})
                result = CodexBuiltinProvider().generate(req, progress=report)
        else:
            result = CodexBuiltinProvider().generate(req, progress=report)

    result.warnings = list(warnings) + list(result.warnings)
    return {
        "result": result,
        "context": context,
        "backend_selected": chosen,
        "backend_effective": result.backend,
        "backend_dialog": dialog,
        "trace": trace,
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
