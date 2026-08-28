from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from aice.providers.base import GenerationRequest, ProviderCapabilities, ReferenceInput
from aice.providers.planner import build_plan


LOCAL = ProviderCapabilities(
    provider="comfyui",
    bootstrap_without_reference=True,
    identity_generation=True,
    reference_expansion=True,
    targeted_repair=True,
    multi_reference=True,
    max_references=3,
    local=True,
)
BUILTIN = ProviderCapabilities(
    provider="codex_builtin",
    bootstrap_without_reference=True,
    identity_generation=True,
    reference_expansion=True,
    targeted_repair=True,
    multi_reference=True,
)


class ReferenceFabricTests(unittest.TestCase):
    def test_structured_reference_is_canonical(self) -> None:
        ref = ReferenceInput(id="g1", path=Path("golden.png"), role="face_front",
                             tier="golden", origin_provider="codex_builtin", tags=("face", "front"))
        req = GenerationRequest(character="maya", prompt="portrait", references=(ref,))
        got = req.capped_reference_metadata()
        self.assertEqual(got[0]["id"], "g1")
        self.assertEqual(got[0]["origin_provider"], "codex_builtin")
        self.assertEqual(req.capped_references(), (Path("golden.png"),))

    def test_legacy_reference_fields_still_normalize(self) -> None:
        req = GenerationRequest(
            character="maya", prompt="portrait",
            reference_paths=(Path("old.png"),), reference_ids=("old1",),
            reference_roles=("seed",), reference_tiers=("golden",),
            reference_origins=("comfyui",),
        )
        ref = req.normalized_references()[0]
        self.assertEqual(ref.id, "old1")
        self.assertEqual(ref.origin_provider, "comfyui")

    def test_operation_validation(self) -> None:
        with self.assertRaises(ValueError):
            GenerationRequest(character="maya", prompt="x", operation="video")


class HybridPlannerTests(unittest.TestCase):
    def _identity_req(self) -> GenerationRequest:
        return GenerationRequest(
            character="maya", prompt="candid portrait",
            references=(ReferenceInput(id="g", path=Path("g.png"), tier="golden"),),
        )

    def test_auto_uses_local_for_identity_when_ready(self) -> None:
        plan = build_plan("auto", self._identity_req(), local_ready=True,
                          local_request_ready=True, local_caps=LOCAL, builtin_caps=BUILTIN)
        self.assertEqual(plan.primary_provider, "comfyui")
        self.assertEqual(plan.strategy, "local-first")
        self.assertTrue(plan.allow_cross_provider_repair)
        self.assertEqual(plan.stages[-1].provider, "codex_builtin")
        self.assertFalse(plan.stages[-1].required)

    def test_auto_uses_builtin_when_local_operation_is_not_ready(self) -> None:
        plan = build_plan("auto", self._identity_req(), local_ready=True,
                          local_request_ready=False, local_caps=LOCAL, builtin_caps=BUILTIN)
        self.assertEqual(plan.primary_provider, "codex_builtin")

    def test_hybrid_is_permission_not_double_generation(self) -> None:
        plan = build_plan("hybrid", self._identity_req(), local_ready=True,
                          local_request_ready=True, local_caps=LOCAL, builtin_caps=BUILTIN)
        self.assertEqual(plan.stages[0].name, "primary")
        self.assertTrue(plan.stages[0].required)
        self.assertEqual(sum(1 for s in plan.stages if s.required), 1)
        self.assertTrue(any(not s.required for s in plan.stages))

    def test_forced_local_never_silently_changes_provider(self) -> None:
        plan = build_plan("comfyui", self._identity_req(), local_ready=False,
                          local_request_ready=False, local_caps=LOCAL, builtin_caps=BUILTIN)
        self.assertEqual(plan.primary_provider, "comfyui")
        self.assertFalse(plan.allow_cross_provider_repair)

    def test_bootstrap_prefers_validated_local_when_available(self) -> None:
        req = GenerationRequest(character="maya", prompt="new person", operation="bootstrap")
        plan = build_plan("auto", req, local_ready=True, local_request_ready=True,
                          local_caps=LOCAL, builtin_caps=BUILTIN)
        self.assertEqual(plan.primary_provider, "comfyui")
        self.assertEqual(plan.stages[0].operation, "bootstrap")

    def test_bootstrap_uses_builtin_then_can_expand_locally(self) -> None:
        local_no_seed = ProviderCapabilities(
            provider="comfyui", bootstrap_without_reference=False,
            identity_generation=True, reference_expansion=True, targeted_repair=True,
            multi_reference=True, max_references=3, local=True,
        )
        req = GenerationRequest(character="maya", prompt="new person", operation="bootstrap")
        plan = build_plan("auto", req, local_ready=True, local_request_ready=False,
                          local_caps=local_no_seed, builtin_caps=BUILTIN)
        self.assertEqual(plan.primary_provider, "codex_builtin")
        self.assertTrue(any(s.name == "expand_after_approval" and s.provider == "comfyui"
                            for s in plan.stages))

    def test_capabilities_reject_reference_less_identity_when_needed(self) -> None:
        local = ProviderCapabilities(provider="comfyui", bootstrap_without_reference=False)
        self.assertFalse(local.supports("generate", reference_count=0))
        self.assertTrue(local.supports("generate", reference_count=1))


if __name__ == "__main__":
    unittest.main()
