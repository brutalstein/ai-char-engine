from __future__ import annotations

from .base import GenerationRequest, GenerationResult, ImageProvider, ProgressCallback, emit_progress


class CodexBuiltinProvider(ImageProvider):
    """Codex reads the compiled prompt + selected references and calls its built-in
    ``image_gen``. This provider packages the request; it never touches pixels itself.
    """

    name = "codex_builtin"

    def available(self) -> tuple[bool, str]:
        return True, "Codex built-in image_gen is available in the Codex host"

    def generate(self, req: GenerationRequest, *, progress: ProgressCallback | None = None) -> GenerationResult:
        emit_progress(progress, "builtin_planned", backend=self.name)
        refs = [str(p) for p in req.capped_references()]
        metadata = req.capped_reference_metadata()
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
                "repair": req.repair_of is not None,
            },
            reproducibility={
                "backend": self.name,
                "reference_ids": [row["id"] for row in metadata],
                "reference_roles": [row["role"] for row in metadata],
                "reference_names": [p.name for p in req.capped_references()],
            },
        )
