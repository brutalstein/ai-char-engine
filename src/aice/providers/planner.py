"""Capability-aware cross-provider planning.

The planner never judges pixels and never changes reference trust. It answers a much
smaller question: which validated engine should do each *kind* of work, and where may
another engine assist after Codex visual validation? Optional stages are permissions,
not mandatory extra model calls.
"""
from __future__ import annotations

from .base import GenerationPlan, GenerationRequest, PlanStage, ProviderCapabilities

VALID_STRATEGIES = {"auto", "hybrid", "comfyui", "codex_builtin"}


def build_plan(
    mode: str,
    req: GenerationRequest,
    *,
    local_ready: bool,
    local_request_ready: bool,
    local_caps: ProviderCapabilities,
    builtin_caps: ProviderCapabilities,
) -> GenerationPlan:
    """Return a deterministic, auditable generation strategy.

    ``local_ready`` means ComfyUI can perform normal identity/reference work.
    ``local_request_ready`` is operation-specific; bootstrap may be unavailable until
    its optional text-to-image model has been installed and smoke-validated.
    """
    mode = mode if mode in VALID_STRATEGIES else "auto"
    ref_count = len(req.normalized_references())

    if getattr(req, "explicit", "normal") == "explicit":
        # Policy, not a capability trade-off: explicit adult synthetic content is
        # only ever produced by the local ComfyUI LUSTIFY profile. Never the
        # built-in cloud generator, and never a silent cross-provider fallback.
        return GenerationPlan(
            strategy="local-adult",
            primary_provider="comfyui",
            stages=(PlanStage("primary", "comfyui", req.operation, True,
                              "Explicit adult content uses the local adult profile only."),),
            allow_cross_provider_repair=False,
            allow_cross_provider_reference_reuse=True,
            reason=("Local adult profile ready." if local_request_ready else
                    "Explicit adult content must stay on the local adult backend; "
                    "if it is unavailable the request is not downgraded to cloud generation."),
        )

    if mode == "comfyui":
        return GenerationPlan(
            strategy="forced-local",
            primary_provider="comfyui",
            stages=(PlanStage("primary", "comfyui", req.operation, True,
                              "User explicitly selected local ComfyUI."),),
            allow_cross_provider_repair=False,
            reason=("Local provider supports this operation." if local_request_ready
                    else "Local provider was explicitly requested; do not silently switch providers."),
        )

    if mode == "codex_builtin":
        return GenerationPlan(
            strategy="forced-builtin",
            primary_provider="codex_builtin",
            stages=(PlanStage("primary", "codex_builtin", req.operation, True,
                              "User explicitly selected Codex image generation."),),
            allow_cross_provider_repair=False,
            reason="Explicit provider choice is authoritative for this request.",
        )

    if req.operation == "bootstrap":
        if local_request_ready:
            primary = "comfyui" if mode == "hybrid" else "comfyui"
            stages = [PlanStage("seed", primary, "bootstrap", True,
                                "Validated local text-to-image bootstrap is available.")]
            if mode == "hybrid" and builtin_caps.bootstrap_without_reference:
                stages.append(PlanStage(
                    "repair_if_needed", "codex_builtin", "repair", False,
                    "Use only if visual validation finds a localized seed defect.",
                ))
            return GenerationPlan(
                strategy="hybrid-bootstrap" if mode == "hybrid" else "local-bootstrap",
                primary_provider=primary,
                stages=tuple(stages),
                allow_cross_provider_repair=mode == "hybrid",
                reason="Bootstrap stays local because a validated no-reference workflow is present.",
            )

        stages = [PlanStage(
            "seed", "codex_builtin", "bootstrap", True,
            "Built-in generation can create an identity without a reference image.",
        )]
        if local_ready and local_caps.reference_expansion:
            stages.append(PlanStage(
                "expand_after_approval", "comfyui", "reference_expand", False,
                "After the seed is approved, local ComfyUI may derive useful identity views from it.",
            ))
        return GenerationPlan(
            strategy="hybrid-bootstrap" if local_ready else "builtin-bootstrap",
            primary_provider="codex_builtin",
            stages=tuple(stages),
            allow_cross_provider_repair=False,
            reason="No validated local no-reference workflow is available; create one seed, then reuse it across providers.",
        )

    # Identity generation / expansion / repair with an existing trusted reference fabric.
    primary = "comfyui" if local_request_ready else "codex_builtin"
    strategy = "hybrid" if mode == "hybrid" else ("local-first" if primary == "comfyui" else "builtin-first")
    stages: list[PlanStage] = [PlanStage(
        "primary", primary, req.operation, True,
        "Validated local provider matches this operation." if primary == "comfyui"
        else "Local provider is unavailable for this operation.",
    )]

    other = "codex_builtin" if primary == "comfyui" else "comfyui"
    other_caps = builtin_caps if other == "codex_builtin" else local_caps
    other_ready = True if other == "codex_builtin" else local_ready
    allow_repair = (
        mode in {"auto", "hybrid"}
        and other_ready
        and other_caps.targeted_repair
        and ref_count > 0
    )
    if allow_repair:
        stages.append(PlanStage(
            "repair_if_needed", other, "repair", False,
            "Cross-provider repair is allowed only after Codex visual validation reports a hard/localized failure.",
        ))

    return GenerationPlan(
        strategy=strategy,
        primary_provider=primary,
        stages=tuple(stages),
        allow_cross_provider_repair=allow_repair,
        allow_cross_provider_reference_reuse=True,
        reason="Provider choice is capability-aware; trusted references remain provider-neutral.",
    )
