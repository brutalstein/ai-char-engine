"""Image generation providers.

The Character Brain (brain.py / engine.py / selector.py) decides *what* to draw and
*which* references to use. A provider only turns an already-compiled request into an
image. ComfyUI is one provider; Codex built-in ``image_gen`` is the always-available
fallback.
"""

from .base import (
    EffectiveSettings,
    GenerationRequest,
    GenerationResult,
    ImageProvider,
)
from .codex_builtin import CodexBuiltinProvider
from .router import BackendProbe, select_backend

__all__ = [
    "EffectiveSettings",
    "GenerationRequest",
    "GenerationResult",
    "ImageProvider",
    "CodexBuiltinProvider",
    "BackendProbe",
    "select_backend",
]
