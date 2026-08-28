"""Glue between Character Brain state and pixel providers.

Provider choice is capability-aware and permits bounded cross-provider help without
ever letting a provider own character truth or reference trust.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from ..engine import build_context, render_generation_prompt
from ..intent import DISALLOWED, classify_explicitness
from ..selector import infer_tags
from ..storage import get_backend_preference, load_profile
from .base import GenerationRequest, GenerationResult, ProgressCallback, ReferenceInput
from .codex_builtin import CodexBuiltinProvider
from .planner import build_plan
from .router import comfy_ready
from .ux import backend_dialog, safe_comfy_probe


_REFUSAL_TEXT = (
    "I can't generate this image. AI Character Engine is limited to adult synthetic "
    "or user-authorized characters and never produces sexual content involving minors, "
    "incest, non-consent, sexual violence, real-person sexual deepfakes, or "
    "hidden-camera scenarios."
)


def _refused_result(verdict: Any) -> GenerationResult:
    return GenerationResult(
        backend="",
        status="refused",
        error=_REFUSAL_TEXT,
        handoff={"policy": "adult synthetic / user-authorized characters only",
                 "matched": list(getattr(verdict, "matched", ()))},
    )


def _aspect_from_tags(tags: set[str]) -> str:
    if {"full_body", "legs"} & tags:
        return "full_body"
    if "profile_picture" in tags:
        return "square"
    return "portrait"


def _preference_mode(preference: str, dialog: dict[str, Any]) -> str | None:
    if dialog.get("needs_user_choice"):
        return None
    if preference in {"auto", "hybrid", "comfyui", "codex_builtin"}:
        return preference
    return str(dialog.get("effective") or "codex_builtin")


def _reference_origin(row: dict[str, Any]) -> str:
    explicit = str(row.get("origin_provider", "")).strip()
    if explicit:
        return explicit
    source = str(row.get("source", ""))
    return "user" if source == "user_uploaded" else "unknown"


def _request_from_context(
    context: dict[str, Any],
    request_text: str,
    *,
    budget: str,
    seed: int | None,
    out_dir: Path | None,
    operation: str,
    repair_of: Path | None,
    explicit: str = "normal",
) -> GenerationRequest:
    tags = infer_tags(request_text)
    ref_rows = context.get("references", [])
    refs = tuple(ReferenceInput(
        id=str(row.get("id", "")),
        path=Path(row["path"]),
        role=str(row.get("role", "")),
        tier=str(row.get("tier", "")),
        origin_provider=_reference_origin(row),
        tags=tuple(str(x) for x in row.get("tags", [])),
    ) for row in ref_rows)
    details = tuple(
        f"{d.get('kind', 'feature')} at {d.get('location', '')}: {d.get('description', '')}"
        for d in context.get("visible_permanent_details", [])
    )
    return GenerationRequest(
        character=context["character"],
        prompt=render_generation_prompt(context),
        references=refs,
        visible_permanent_details=details,
        scene_tags=tuple(sorted(tags)),
        aspect=_aspect_from_tags(tags),
        budget=budget,
        operation=operation,
        explicit=explicit,
        seed=seed,
        repair_of=repair_of,
        out_dir=out_dir,
    )


def _seed_request(
    character: str,
    description: str,
    *,
    budget: str,
    seed: int | None,
    out_dir: Path | None,
) -> GenerationRequest:
    prompt = "\n".join([
        "Use case: photorealistic-natural identity seed for a persistent virtual creator.",
        f"Character description: {description.strip()}",
        "Create one original adult synthetic person from scratch. Establish a clear, recognizable, realistic identity that can be reused as a future reference.",
        "Natural skin texture and anatomy; neutral-to-relaxed expression; uncluttered photography; no celebrity likeness, no text, no watermark.",
        "Do not invent permanent tattoos, scars, jewelry, or marks unless the description explicitly requests them.",
    ])
    tags = infer_tags(description)
    return GenerationRequest(
        character=character,
        prompt=prompt,
        references=(),
        scene_tags=tuple(sorted(tags)),
        aspect=_aspect_from_tags(tags),
        budget=budget,
        operation="bootstrap",
        seed=seed,
        out_dir=out_dir,
    )


def _execute(
    req: GenerationRequest,
    *,
    preference: str,
    mode: str,
    probe: Any,
    provider: Any | None,
    report,
) -> GenerationResult:
    builtin = CodexBuiltinProvider()
    normal_local_ready, _ = comfy_ready(probe)
    normal_local_ready = bool(normal_local_ready and provider is not None)

    # Operation-specific readiness is authoritative for the current request. This is
    # intentionally independent from the identity probe: adult/bootstrap capabilities
    # carry their own smoke-validation state in v0.5.1.
    local_request_ready = False
    local_caps = provider.capabilities() if provider is not None else None
    if provider is not None:
        local_request_ready = bool(provider.available_for(req)[0])
    if local_caps is None:
        from .base import ProviderCapabilities
        local_caps = ProviderCapabilities(provider="comfyui", local=True, privacy="localhost_only")

    plan = build_plan(
        mode,
        req,
        local_ready=normal_local_ready,
        local_request_ready=local_request_ready,
        local_caps=local_caps,
        builtin_caps=builtin.capabilities(),
    )
    chosen = plan.primary_provider
    report({
        "stage": "plan_resolved",
        "strategy": plan.strategy,
        "operation": req.operation,
        "backend": chosen,
        "hybrid": plan.allow_cross_provider_repair or len(plan.stages) > 1,
    })
    report({"stage": "backend_selected", "requested": mode, "backend": chosen})

    explicit_adult = getattr(req, "explicit", "normal") == "explicit"

    if chosen == "comfyui":
        if provider is None or not local_request_ready:
            if explicit_adult:
                why = provider.adult_available()[1] if provider is not None else "local backend not installed"
                report({"stage": "backend_setup_required", "backend": "comfyui",
                        "capability": "adult_explicit", "reason": why})
                result = GenerationResult(
                    backend="comfyui",
                    status="local_adult_unavailable",
                    error=(
                        "The local adult image backend (LUSTIFY SDXL) is not ready yet "
                        f"({why}), so this explicit request was not generated. Explicit "
                        "adult content is never sent to the built-in cloud generator."
                    ),
                    handoff={
                        "setup": "aice comfy setup --capabilities adult_explicit",
                        "then": "aice comfy doctor --smoke",
                        "reason": why,
                        "non_explicit_alternative": (
                            "Ask for a non-explicit version of this image and the "
                            "standard profile can generate it now."
                        ),
                    },
                )
            else:
                result = GenerationResult(
                    backend="comfyui",
                    status="failed",
                    error="Local ComfyUI was selected but is not ready for this operation.",
                )
        else:
            result = provider.generate(req, progress=report)
        if result.status == "failed" and mode in {"auto", "hybrid"} and not explicit_adult:
            report({"stage": "fallback_planned", "from": "comfyui", "to": "codex_builtin"})
            fallback = builtin.generate(req, progress=report)
            fallback.warnings.insert(0, f"comfyui failed ({result.error}); planned built-in fallback")
            result = fallback
    else:
        result = builtin.generate(req, progress=report)

    result.plan = plan.as_dict()
    result.reproducibility.setdefault("strategy", plan.strategy)
    result.reproducibility.setdefault("requested_mode", mode)
    result.reproducibility.setdefault("saved_preference", preference)
    return result


def plan_and_generate(
    home: Path,
    character: str,
    request_text: str,
    *,
    budget: str = "balanced",
    backend: str | None = None,
    seed: int | None = None,
    out_dir: Path | None = None,
    operation: str = "generate",
    repair_of: Path | None = None,
    progress: ProgressCallback | None = None,
) -> dict[str, Any]:
    trace: list[dict[str, Any]] = []

    def report(event: dict[str, Any]) -> None:
        trace.append(dict(event))
        if progress is not None:
            progress(dict(event))

    verdict = classify_explicitness(request_text)
    report({"stage": "intent_classified", "level": verdict.level,
            "matched": list(verdict.matched), "wants_local_adult": verdict.wants_local_adult})
    if verdict.level == DISALLOWED:
        report({"stage": "request_refused", "reason": verdict.reason})
        return {"result": _refused_result(verdict), "context": None, "backend_selected": None,
                "backend_effective": None, "backend_dialog": None, "trace": trace}

    explicit_level = "explicit" if (verdict.is_explicit or verdict.wants_local_adult) else verdict.level

    context = build_context(home, character, request_text, budget)
    report({"stage": "context_compiled", "reference_count": len(context.get("references", []))})
    req = _request_from_context(
        context,
        request_text,
        budget=budget,
        seed=seed,
        out_dir=out_dir,
        operation=operation,
        repair_of=repair_of,
        explicit=explicit_level,
    )
    probe, provider = safe_comfy_probe()
    _, profile = load_profile(home, character)
    preference = get_backend_preference(profile)
    dialog = backend_dialog(preference, probe)

    if req.explicit == "explicit":
        report({"stage": "adult_routing",
                "reason": "explicit adult synthetic content -> local ComfyUI LUSTIFY profile only",
                "wants_local_adult": verdict.wants_local_adult})
        mode = "comfyui"
    elif backend is None:
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

    result = _execute(
        req,
        preference=preference,
        mode=mode,
        probe=probe,
        provider=provider,
        report=report,
    )
    return {
        "result": result,
        "context": context,
        "backend_selected": result.plan.get("primary_provider"),
        "backend_effective": result.backend,
        "backend_dialog": dialog,
        "trace": trace,
    }


def plan_seed_generation(
    home: Path,
    character: str,
    description: str,
    *,
    budget: str = "balanced",
    backend: str | None = None,
    seed: int | None = None,
    out_dir: Path | None = None,
    progress: ProgressCallback | None = None,
) -> dict[str, Any]:
    """Plan/create the first identity seed without requiring a trusted reference."""
    trace: list[dict[str, Any]] = []

    def report(event: dict[str, Any]) -> None:
        trace.append(dict(event))
        if progress is not None:
            progress(dict(event))

    verdict = classify_explicitness(description)
    report({"stage": "intent_classified", "level": verdict.level,
            "matched": list(verdict.matched), "wants_local_adult": verdict.wants_local_adult})
    if verdict.level == DISALLOWED:
        report({"stage": "request_refused", "reason": verdict.reason})
        return {"result": _refused_result(verdict), "context": None, "backend_selected": None,
                "backend_effective": None, "backend_dialog": None, "trace": trace}

    # The adult LUSTIFY workflow is reference-driven. A scratch request that is
    # already explicit must never leak to built-in image_gen or unrelated Qwen T2I.
    # Establish/approve the identity neutrally first, then the explicit request can
    # use that trusted seed locally.
    if verdict.is_explicit or verdict.wants_local_adult:
        report({"stage": "adult_identity_required",
                "reason": "explicit local generation requires an approved identity seed"})
        result = GenerationResult(
            backend="comfyui",
            status="adult_identity_required",
            error=(
                "Explicit local generation needs an approved identity reference first. "
                "Create and approve a non-explicit identity seed, then retry the explicit request; "
                "the explicit image will stay on the local adult backend."
            ),
            handoff={
                "next": "create_and_approve_non_explicit_seed",
                "then": "retry_original_explicit_request",
                "cloud_explicit_generation": False,
            },
        )
        return {"result": result, "context": None, "backend_selected": "comfyui",
                "backend_effective": None, "backend_dialog": None, "trace": trace}

    _, profile = load_profile(home, character)
    req = _seed_request(profile["id"], description, budget=budget, seed=seed, out_dir=out_dir)
    report({"stage": "seed_contract_compiled", "reference_count": 0})
    probe, provider = safe_comfy_probe()
    preference = get_backend_preference(profile)
    local_bootstrap = bool(provider is not None and provider.available_for(req)[0])

    if backend is not None:
        mode = backend
    elif preference in {"auto", "hybrid", "comfyui", "codex_builtin"}:
        mode = preference
    elif local_bootstrap:
        dialog = {
            "stage": "choose_backend",
            "needs_user_choice": True,
            "user_message": "Both engines can create the first character seed. Do you want local ComfyUI, Codex image generation, hybrid/automatic planning, or should I ask each time?",
            "choices": ["comfyui", "codex_builtin", "hybrid", "auto"],
        }
        report({"stage": "backend_choice_required", "preference": preference, "operation": "bootstrap"})
        result = GenerationResult(backend="", status="needs_backend_choice",
                                  error="Seed backend choice is required before generation.")
        return {"result": result, "context": None, "backend_selected": None,
                "backend_effective": None, "backend_dialog": dialog, "trace": trace}
    else:
        mode = "codex_builtin"

    if mode == "comfyui" and not local_bootstrap:
        result = GenerationResult(
            backend="comfyui",
            status="needs_backend_setup",
            error="Local text-to-image bootstrap is not installed/ready/validated.",
            handoff={
                "setup": "aice comfy setup --capabilities bootstrap",
                "then": "aice comfy doctor --smoke",
                "alternative": "codex_builtin",
            },
        )
        report({"stage": "backend_setup_required", "backend": "comfyui", "operation": "bootstrap"})
        return {"result": result, "context": None, "backend_selected": "comfyui",
                "backend_effective": None, "backend_dialog": None, "trace": trace}

    result = _execute(
        req,
        preference=preference,
        mode=mode,
        probe=probe,
        provider=provider,
        report=report,
    )
    return {"result": result, "context": None,
            "backend_selected": result.plan.get("primary_provider"),
            "backend_effective": result.backend, "backend_dialog": None, "trace": trace}


def result_ledger_row(result: GenerationResult) -> dict[str, Any]:
    return {
        "backend": result.backend,
        "model_id": result.model_id,
        "workflow_version": result.workflow_version,
        "seed": result.seed,
        "duration_s": round(result.duration_s, 2),
        "effective_settings": result.effective_settings,
        "reproducibility": result.reproducibility,
        "plan": result.plan,
        "handoff": result.handoff,
        "warnings": result.warnings,
    }
