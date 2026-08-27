from __future__ import annotations

from .base import GenerationRequest, GenerationResult, ImageProvider


class CodexBuiltinProvider(ImageProvider):
    """The original path: Codex reads the compiled prompt + selected references and
    calls its built-in ``image_gen``. This provider only packages the request; it
    never touches pixels itself, so behaviour is identical to v0.2.0.
    """

    name = "codex_builtin"

    def available(self) -> tuple[bool, str]:
        return True, "Codex built-in image_gen is always available"

    def generate(self, req: GenerationRequest) -> GenerationResult:
        refs = [str(p) for p in req.reference_paths]
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
                "reference_names": [p.name for p in req.reference_paths],
            },
        )
