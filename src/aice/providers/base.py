from __future__ import annotations

import abc
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

MAX_PROVIDER_REFERENCES = 3
VALID_OPERATIONS = {"generate", "bootstrap", "reference_expand", "repair"}
# Content explicitness, decided by aice.intent before the request is built. Only
# ``explicit`` changes routing (forces the local ComfyUI adult profile); the
# ``disallowed`` bucket is refused by the orchestrator and never reaches a request.
VALID_EXPLICITNESS = {"normal", "suggestive", "explicit"}
ProgressCallback = Callable[[dict[str, Any]], None]


def emit_progress(callback: ProgressCallback | None, stage: str, **details: Any) -> None:
    """Emit a factual coarse-grained generation event; never invent percentages."""
    if callback is not None:
        callback({"stage": stage, **details})


@dataclass(frozen=True)
class ReferenceInput:
    """Provider-neutral reference asset.

    Trust is decided by AICE before this object is created. Providers may use the
    metadata for conditioning/reproducibility, but never promote or reinterpret it.
    """

    id: str
    path: Path
    role: str = ""
    tier: str = ""
    origin_provider: str = "unknown"
    tags: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "path": str(self.path),
            "role": self.role,
            "tier": self.tier,
            "origin_provider": self.origin_provider,
            "tags": list(self.tags),
        }


@dataclass(frozen=True)
class ProviderCapabilities:
    """Declarative capability contract used by the planner, not marketing flags."""

    provider: str
    bootstrap_without_reference: bool = False
    identity_generation: bool = True
    reference_expansion: bool = True
    targeted_repair: bool = False
    multi_reference: bool = False
    max_references: int | None = None
    local: bool = False
    privacy: str = "host"
    # True only for a provider that can run the local explicit-adult profile
    # (LUSTIFY SDXL). Built-in cloud image generation is never adult_explicit.
    adult_explicit_generation: bool = False

    def supports(self, operation: str, reference_count: int = 0) -> bool:
        if operation == "bootstrap":
            return self.bootstrap_without_reference
        if operation == "reference_expand":
            return self.reference_expansion and (reference_count > 0 or self.bootstrap_without_reference)
        if operation == "repair":
            return self.targeted_repair
        return self.identity_generation and (reference_count > 0 or self.bootstrap_without_reference)

    def as_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "bootstrap_without_reference": self.bootstrap_without_reference,
            "identity_generation": self.identity_generation,
            "reference_expansion": self.reference_expansion,
            "targeted_repair": self.targeted_repair,
            "multi_reference": self.multi_reference,
            "max_references": self.max_references,
            "local": self.local,
            "privacy": self.privacy,
            "adult_explicit_generation": self.adult_explicit_generation,
        }


@dataclass(frozen=True)
class PlanStage:
    name: str
    provider: str
    operation: str
    required: bool = True
    reason: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "provider": self.provider,
            "operation": self.operation,
            "required": self.required,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class GenerationPlan:
    """Small deterministic plan. Optional stages are permissions, not forced calls."""

    strategy: str
    primary_provider: str
    stages: tuple[PlanStage, ...]
    allow_cross_provider_repair: bool = False
    allow_cross_provider_reference_reuse: bool = True
    reason: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "strategy": self.strategy,
            "primary_provider": self.primary_provider,
            "stages": [stage.as_dict() for stage in self.stages],
            "allow_cross_provider_repair": self.allow_cross_provider_repair,
            "allow_cross_provider_reference_reuse": self.allow_cross_provider_reference_reuse,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class GenerationRequest:
    """A fully compiled, backend-agnostic image request.

    ``references`` is the canonical v0.4 reference fabric. The parallel legacy fields
    remain for v0.3 callers and are normalized automatically, so existing characters
    and scripts keep working through the migration.
    """

    character: str
    prompt: str
    references: tuple[ReferenceInput, ...] = ()
    reference_paths: tuple[Path, ...] = ()
    reference_ids: tuple[str, ...] = ()
    reference_roles: tuple[str, ...] = ()
    reference_tiers: tuple[str, ...] = ()
    reference_origins: tuple[str, ...] = ()
    visible_permanent_details: tuple[str, ...] = ()
    scene_tags: tuple[str, ...] = ()
    aspect: str = "portrait"
    budget: str = "balanced"
    operation: str = "generate"
    explicit: str = "normal"  # normal | suggestive | explicit (see aice.intent)
    seed: int | None = None
    repair_of: Path | None = None
    out_dir: Path | None = None
    negative: str = ""

    def __post_init__(self) -> None:
        if self.operation not in VALID_OPERATIONS:
            raise ValueError(f"operation must be one of: {', '.join(sorted(VALID_OPERATIONS))}")
        if self.explicit not in VALID_EXPLICITNESS:
            raise ValueError(f"explicit must be one of: {', '.join(sorted(VALID_EXPLICITNESS))}")

    def normalized_references(self) -> tuple[ReferenceInput, ...]:
        if self.references:
            return self.references
        rows: list[ReferenceInput] = []
        for index, path in enumerate(self.reference_paths):
            rows.append(ReferenceInput(
                id=self.reference_ids[index] if index < len(self.reference_ids) else path.name,
                path=Path(path),
                role=self.reference_roles[index] if index < len(self.reference_roles) else "",
                tier=self.reference_tiers[index] if index < len(self.reference_tiers) else "",
                origin_provider=(self.reference_origins[index]
                                 if index < len(self.reference_origins) else "unknown"),
            ))
        return tuple(rows)

    def capped_reference_inputs(self, limit: int = MAX_PROVIDER_REFERENCES) -> tuple[ReferenceInput, ...]:
        return self.normalized_references()[:limit]

    def capped_references(self, limit: int = MAX_PROVIDER_REFERENCES) -> tuple[Path, ...]:
        return tuple(ref.path for ref in self.capped_reference_inputs(limit))

    def capped_reference_metadata(self, limit: int = MAX_PROVIDER_REFERENCES) -> list[dict[str, Any]]:
        return [ref.as_dict() for ref in self.capped_reference_inputs(limit)]


@dataclass(frozen=True)
class EffectiveSettings:
    model_id: str
    steps: int
    cfg: float
    sampler: str
    scheduler: str
    width: int
    height: int
    batch_size: int = 1
    upscale: bool = False
    vram_flags: tuple[str, ...] = ()
    # Identity-adapter strength for SDXL adult profiles (IP-Adapter); 0.0 for the
    # Qwen identity path, which conditions natively and ignores this.
    ipadapter_weight: float = 0.0

    def as_dict(self) -> dict[str, Any]:
        return {
            "model_id": self.model_id,
            "steps": self.steps,
            "cfg": self.cfg,
            "sampler": self.sampler,
            "scheduler": self.scheduler,
            "width": self.width,
            "height": self.height,
            "batch_size": self.batch_size,
            "upscale": self.upscale,
            "vram_flags": list(self.vram_flags),
            "ipadapter_weight": self.ipadapter_weight,
        }


@dataclass
class GenerationResult:
    backend: str
    output_path: Path | None = None
    model_id: str = ""
    workflow_version: str = ""
    seed: int | None = None
    duration_s: float = 0.0
    effective_settings: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    reproducibility: dict[str, Any] = field(default_factory=dict)
    plan: dict[str, Any] = field(default_factory=dict)
    handoff: dict[str, Any] = field(default_factory=dict)
    status: str = "ok"
    error: str = ""

    def to_json(self) -> dict[str, Any]:
        return {
            "backend": self.backend,
            "status": self.status,
            "output_path": str(self.output_path) if self.output_path else None,
            "model_id": self.model_id,
            "workflow_version": self.workflow_version,
            "seed": self.seed,
            "duration_s": round(self.duration_s, 2),
            "effective_settings": self.effective_settings,
            "warnings": self.warnings,
            "reproducibility": self.reproducibility,
            "plan": self.plan,
            "handoff": self.handoff,
            "error": self.error,
        }


class ImageProvider(abc.ABC):
    name: str = "provider"

    @abc.abstractmethod
    def available(self) -> tuple[bool, str]:
        """(usable_now, human-readable reason)."""

    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(provider=self.name)

    def available_for(self, req: GenerationRequest) -> tuple[bool, str]:
        ok, reason = self.available()
        if not ok:
            return ok, reason
        caps = self.capabilities()
        if not caps.supports(req.operation, len(req.normalized_references())):
            return False, f"{self.name} does not support operation {req.operation} for this request"
        return True, reason

    @abc.abstractmethod
    def generate(self, req: GenerationRequest, *, progress: ProgressCallback | None = None) -> GenerationResult: ...
