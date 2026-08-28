"""Image generation provider contracts.

AICE owns identity truth, trust and reference selection. Providers are interchangeable
workers. The capability planner may coordinate them, but no provider can promote its
own output or bypass Character Brain lineage rules.
"""

from .base import (
    EffectiveSettings,
    GenerationPlan,
    GenerationRequest,
    GenerationResult,
    ImageProvider,
    PlanStage,
    ProviderCapabilities,
    ReferenceInput,
)
from .codex_builtin import CodexBuiltinProvider
from .planner import build_plan
from .router import BackendProbe, select_backend

__all__ = [
    "EffectiveSettings",
    "GenerationPlan",
    "GenerationRequest",
    "GenerationResult",
    "ImageProvider",
    "PlanStage",
    "ProviderCapabilities",
    "ReferenceInput",
    "CodexBuiltinProvider",
    "BackendProbe",
    "build_plan",
    "select_backend",
]
