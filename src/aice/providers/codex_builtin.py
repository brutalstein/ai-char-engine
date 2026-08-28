from __future__ import annotations

from .base import (
    GenerationRequest,
    GenerationResult,
    ImageProvider,
    ProgressCallback,
    ProviderCapabilities,
    emit_progress,
)


class CodexBuiltinProvider(ImageProvider):
    """Host-mediated OpenAI image generation.

    AICE packages the exact prompt/reference contract; Codex invokes its built-in
    ``image_gen``. This provider intentionally never owns character truth or pixels.
    """

    name = "codex_builtin"

    def available(self) -> tuple[bool, str]:
        return True, "Codex built-in image_gen is available in the Codex host"

    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            provider=self.name,
            bootstrap_without_reference=True,
            identity_generation=True,
            reference_expansion=True,
            targeted_repair=True,
            multi_reference=True,
            max_references=None,
            local=False,
            privacy="codex_host",
        )

    def generate(self, req: GenerationRequest, *, progress: ProgressCallback | None = None) -> GenerationResult:
        emit_progress(progress, "builtin_planned", backend=self.name, operation=req.operation)
        refs = [str(ref.path) for ref in req.normalized_references()]
        metadata = req.capped_reference_metadata(limit=len(req.normalized_references()))
        edit_target = str(req.repair_of) if req.repair_of else None
        return GenerationResult(
            backend=self.name,
            output_path=None,
            model_id="codex:image_gen",
            status="planned",
            seed=req.seed,
            effective_settings={
                "prompt": req.prompt,
                "negative": req.negative,
                "references": refs,
                "aspect": req.aspect,
                "operation": req.operation,
                "repair": req.repair_of is not None,
                "edit_target": edit_target,
            },
            reproducibility={
                "backend": self.name,
                "operation": req.operation,
                "reference_ids": [row["id"] for row in metadata],
                "reference_roles": [row["role"] for row in metadata],
                "reference_origins": [row.get("origin_provider", "unknown") for row in metadata],
                "reference_names": [ref.path.name for ref in req.normalized_references()],
            },
            handoff={
                "tool": "image_gen",
                "operation": req.operation,
                "use_reference_images": refs,
                "edit_target": edit_target,
                "after_generation": "validate_then_record",
            },
        )
