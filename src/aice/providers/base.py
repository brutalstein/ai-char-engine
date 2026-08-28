from __future__ import annotations

import abc
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

# The model-native hard cap on identity reference images (Qwen-Image-Edit-2509 takes
# image1/image2/image3). Budget caps (economy=2, balanced=3, quality=4) are applied
# upstream in selector.py; a provider still clamps to what its backend accepts.
MAX_PROVIDER_REFERENCES = 3
ProgressCallback = Callable[[dict[str, Any]], None]


def emit_progress(callback: ProgressCallback | None, stage: str, **details: Any) -> None:
    """Emit a factual coarse-grained generation event; never invent percentages."""
    if callback is not None:
        callback({"stage": stage, **details})


@dataclass(frozen=True)
class GenerationRequest:
    """A fully compiled, backend-agnostic image request.

    Everything identity-related is already resolved: ``prompt`` is the compiled
    generation contract (see engine.render_generation_prompt) and ``reference_paths``
    are already-selected golden/trusted images. Parallel reference metadata preserves
    AICE provenance without making providers responsible for trust decisions.
    """

    character: str
    prompt: str
    reference_paths: tuple[Path, ...] = ()
    reference_ids: tuple[str, ...] = ()
    reference_roles: tuple[str, ...] = ()
    reference_tiers: tuple[str, ...] = ()
    visible_permanent_details: tuple[str, ...] = ()
    scene_tags: tuple[str, ...] = ()
    aspect: str = "portrait"  # portrait | square | full_body
    budget: str = "balanced"  # economy | balanced | quality
    seed: int | None = None  # None -> provider chooses and records it
    repair_of: Path | None = None  # set only for the single bounded repair pass
    out_dir: Path | None = None
    negative: str = ""

    def capped_references(self, limit: int = MAX_PROVIDER_REFERENCES) -> tuple[Path, ...]:
        return tuple(self.reference_paths[:limit])

    def capped_reference_metadata(self, limit: int = MAX_PROVIDER_REFERENCES) -> list[dict[str, str]]:
        paths = self.capped_references(limit)
        rows: list[dict[str, str]] = []
        for index, path in enumerate(paths):
            rows.append({
                "id": self.reference_ids[index] if index < len(self.reference_ids) else path.name,
                "role": self.reference_roles[index] if index < len(self.reference_roles) else "",
                "tier": self.reference_tiers[index] if index < len(self.reference_tiers) else "",
                "path": str(path),
            })
        return rows


@dataclass(frozen=True)
class EffectiveSettings:
    """Concrete parameters a hardware/scene policy resolved for one generation."""

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
    # ok       -> output_path holds a finished image
    # planned  -> caller (Codex) must still run built-in image_gen from this payload
    # failed   -> error is set; caller may fall back
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
            "error": self.error,
        }


class ImageProvider(abc.ABC):
    """Backend contract. Implementations must be deterministic about process and I/O;
    only semantic/visual judgement belongs to the Codex layer, never here."""

    name: str = "provider"

    @abc.abstractmethod
    def available(self) -> tuple[bool, str]:
        """(usable_now, human-readable reason)."""

    @abc.abstractmethod
    def generate(self, req: GenerationRequest, *, progress: ProgressCallback | None = None) -> GenerationResult: ...
