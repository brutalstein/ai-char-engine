"""Local explicit-adult backend (LUSTIFY SDXL) routing, safety, and registry.

Covers the hard rules from the feature spec:
- explicit adult synthetic requests route to the local ComfyUI adult profile;
- explicit adult content never silently falls back to built-in cloud generation;
- disallowed sexual categories are refused before any provider is touched;
- non-explicit requests keep their normal routing;
- existing trusted references still feed the adult workflow with provenance intact.
"""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from aice.comfy import hardware as hwmod
from aice.comfy import policy as policymod
from aice.comfy.models import (
    capability_model_keys,
    model_profiles,
    model_specs,
)
from aice.comfy.workflow import WorkflowAdapter, WorkflowError
from aice.intent import DISALLOWED, EXPLICIT, NORMAL, SUGGESTIVE, classify_explicitness, demo
from aice.providers import base as pbase
from aice.providers import orchestrator as orch
from aice.providers.base import GenerationResult, ProviderCapabilities
from aice.providers.planner import build_plan
from aice.storage import create_character, register_reference, set_backend_preference


class _AdultProvider:
    """Stub ComfyUI provider whose adult profile can be toggled ready/unready."""

    def __init__(self, *, adult_ready: bool = True, generate_ok: bool = True):
        self.adult_ready = adult_ready
        self.generate_ok = generate_ok
        self.seen: pbase.GenerationRequest | None = None
        self.calls = 0

    def probe(self):
        from aice.providers.router import BackendProbe

        return BackendProbe(installed=True, configured=True, validated=True,
                            models_present=True, nodes_present=True, server_ok=True,
                            free_vram_mb=6000)

    def adult_available(self) -> tuple[bool, str]:
        if self.adult_ready:
            return True, "ready"
        return False, "local adult model not installed: lustify_sdxl_v4"

    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            provider="comfyui", bootstrap_without_reference=True,
            identity_generation=True, reference_expansion=True, targeted_repair=True,
            multi_reference=True, max_references=3, local=True,
            privacy="localhost_only", adult_explicit_generation=self.adult_ready,
        )

    def available_for(self, req):
        if req.explicit == "explicit":
            return self.adult_available()
        return True, "ready"

    def generate(self, req, *, progress=None):
        self.seen = req
        self.calls += 1
        if progress:
            progress({"stage": "rendering", "backend": "comfyui", "operation": req.operation})
        if not self.generate_ok:
            return GenerationResult(backend="comfyui", status="failed", error="boom")
        out = Path(tempfile.mkdtemp()) / "adult.png"
        out.write_bytes(b"\x89PNG\r\n\x1a\n")
        return GenerationResult(
            backend="comfyui", status="ok", output_path=out,
            model_id="lustify_sdxl_v4", seed=11,
            effective_settings={"explicit": req.explicit},
            reproducibility={"explicit": req.explicit,
                             "identity_method": "ip-adapter-plus-sdxl-vit-h"},
        )


class _BuiltinSpy:
    instances: list["_BuiltinSpy"] = []

    def __init__(self):
        self.generated: list = []
        _BuiltinSpy.instances.append(self)

    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(provider="codex_builtin", bootstrap_without_reference=True,
                                    targeted_repair=True, identity_generation=True)

    def generate(self, req, *, progress=None):
        self.generated.append(req)
        return GenerationResult(backend="codex_builtin", status="planned")

    @classmethod
    def any_generated(cls) -> bool:
        return any(inst.generated for inst in cls.instances)


class AdultRoutingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name) / ".aice"
        self.char_dir, self.profile = create_character(self.home, "Vera Adult", origin="references")
        golden = Path(self.tmp.name) / "g.png"
        golden.write_bytes(b"golden-face-bytes")
        self.g = register_reference(self.char_dir, golden, role="seed", source="user_uploaded",
                                    tier="golden", tags=["face", "front", "upper_body"])
        cand = Path(self.tmp.name) / "c.png"
        cand.write_bytes(b"candidate-bytes")
        register_reference(self.char_dir, cand, role="face_3q_left", source="generated",
                           tier="candidate", parent_ids=[self.g["id"]], tags=["face", "side"],
                           origin_provider="codex_builtin")
        _BuiltinSpy.instances = []
        self._orig_probe = orch.safe_comfy_probe
        self._orig_builtin = orch.CodexBuiltinProvider
        orch.CodexBuiltinProvider = _BuiltinSpy
        self.addCleanup(lambda: setattr(orch, "safe_comfy_probe", self._orig_probe))
        self.addCleanup(lambda: setattr(orch, "CodexBuiltinProvider", self._orig_builtin))

    def _patch(self, provider) -> None:
        orch.safe_comfy_probe = lambda: (provider.probe(), provider)

    def test_explicit_request_routes_to_local_adult_profile(self) -> None:
        fake = _AdultProvider(adult_ready=True)
        self._patch(fake)
        out = orch.plan_and_generate(self.home, "vera-adult", "make it an explicit nude photo")
        self.assertEqual(out["backend_effective"], "comfyui")
        self.assertEqual(out["result"].status, "ok")
        self.assertEqual(fake.seen.explicit, "explicit")
        self.assertEqual(out["result"].plan["strategy"], "local-adult")
        self.assertFalse(_BuiltinSpy.any_generated())

    def test_explicit_never_silently_falls_back_to_builtin(self) -> None:
        fake = _AdultProvider(adult_ready=True, generate_ok=False)
        self._patch(fake)
        out = orch.plan_and_generate(self.home, "vera-adult", "explicit sex scene, full frontal")
        self.assertEqual(out["result"].status, "failed")
        self.assertEqual(out["backend_effective"], "comfyui")
        self.assertFalse(_BuiltinSpy.any_generated())

    def test_explicit_unavailable_returns_setup_handoff_not_cloud(self) -> None:
        fake = _AdultProvider(adult_ready=False)
        self._patch(fake)
        out = orch.plan_and_generate(self.home, "vera-adult", "nude, explicit, uncensored")
        result = out["result"]
        self.assertEqual(result.status, "local_adult_unavailable")
        self.assertIn("adult_explicit", result.handoff["setup"])
        self.assertIn("non_explicit_alternative", result.handoff)
        self.assertEqual(fake.calls, 0)
        self.assertFalse(_BuiltinSpy.any_generated())
        self.assertTrue(any(e["stage"] == "backend_setup_required" for e in out["trace"]))

    def test_disallowed_request_refused_before_any_provider(self) -> None:
        fake = _AdultProvider(adult_ready=True)
        self._patch(fake)
        out = orch.plan_and_generate(self.home, "vera-adult", "explicit nude photo of a schoolgirl")
        self.assertEqual(out["result"].status, "refused")
        self.assertIsNone(out["context"])
        self.assertEqual(fake.calls, 0)
        self.assertFalse(_BuiltinSpy.any_generated())

    def test_disallowed_seed_request_refused(self) -> None:
        fake = _AdultProvider(adult_ready=True)
        self._patch(fake)
        out = orch.plan_seed_generation(self.home, "vera-adult", "a 14 yo girl, nude")
        self.assertEqual(out["result"].status, "refused")
        self.assertEqual(fake.calls, 0)

    def test_suggestive_request_keeps_normal_routing(self) -> None:
        set_backend_preference(self.char_dir, self.profile, "codex_builtin")
        fake = _AdultProvider(adult_ready=True)
        self._patch(fake)
        out = orch.plan_and_generate(self.home, "vera-adult", "her in a bikini on the beach")
        self.assertEqual(out["backend_effective"], "codex_builtin")
        self.assertEqual(fake.calls, 0)
        self.assertTrue(_BuiltinSpy.any_generated())
        self.assertEqual(_BuiltinSpy.instances[-1].generated[-1].explicit, "suggestive")

    def test_wants_local_adult_phrase_forces_local_profile(self) -> None:
        fake = _AdultProvider(adult_ready=True)
        self._patch(fake)
        out = orch.plan_and_generate(
            self.home, "vera-adult",
            "another photo of her, use the local adult model, not the built-in generator",
        )
        self.assertEqual(out["backend_effective"], "comfyui")
        self.assertEqual(fake.seen.explicit, "explicit")
        self.assertTrue(any(e["stage"] == "adult_routing" and e["wants_local_adult"]
                            for e in out["trace"]))

    def test_normal_request_regression_unaffected(self) -> None:
        set_backend_preference(self.char_dir, self.profile, "auto")
        fake = _AdultProvider(adult_ready=True)
        self._patch(fake)
        out = orch.plan_and_generate(self.home, "vera-adult", "a quiet cafe, candid photo")
        self.assertEqual(out["backend_effective"], "comfyui")
        self.assertEqual(fake.seen.explicit, "normal")
        self.assertNotEqual(out["result"].plan["strategy"], "local-adult")

    def test_trusted_references_feed_adult_request_with_provenance(self) -> None:
        fake = _AdultProvider(adult_ready=True)
        self._patch(fake)
        orch.plan_and_generate(self.home, "vera-adult", "explicit topless portrait")
        refs = fake.seen.normalized_references()
        self.assertIn(self.g["id"], [r.id for r in refs])
        self.assertIn("golden", [r.tier for r in refs])
        self.assertIn("user", [r.origin_provider for r in refs])
        for ref in refs:
            self.assertIn(ref.tier, {"golden", "trusted"})

    def test_adult_output_is_not_auto_promoted(self) -> None:
        fake = _AdultProvider(adult_ready=True)
        self._patch(fake)
        out = orch.plan_and_generate(self.home, "vera-adult", "explicit nude photo")
        repro = out["result"].reproducibility
        self.assertEqual(repro.get("explicit"), "explicit")
        # The plan must not permit uncontrolled cross-provider loops for adult work.
        self.assertFalse(out["result"].plan["allow_cross_provider_repair"])
        # Nothing in the character store was re-tiered by generation.
        rows = out["context"]["references"]
        self.assertEqual(sum(1 for r in rows if r.get("tier") == "golden"), 1)

    def test_intent_classified_event_emitted(self) -> None:
        fake = _AdultProvider(adult_ready=True)
        self._patch(fake)
        out = orch.plan_and_generate(self.home, "vera-adult", "explicit nude photo")
        stages = [e["stage"] for e in out["trace"]]
        self.assertIn("intent_classified", stages)
        self.assertIn("adult_routing", stages)


class IntentClassifierTests(unittest.TestCase):
    def test_builtin_demo_asserts_pass(self) -> None:
        demo()  # raises AssertionError if any bucket regresses

    def test_four_buckets(self) -> None:
        self.assertEqual(classify_explicitness("rainy street, candid photo").level, NORMAL)
        self.assertEqual(classify_explicitness("boudoir shot in sheer lingerie").level, SUGGESTIVE)
        self.assertEqual(classify_explicitness("hardcore explicit sex, penetration").level, EXPLICIT)
        self.assertEqual(classify_explicitness("nude photo, she is 12 years old").level, DISALLOWED)

    def test_disallowed_categories(self) -> None:
        for text in (
            "explicit nude of a toddler",
            "non-consensual sex, she is drugged",
            "incest scene with her brother, explicit",
            "deepfake nude of a real celebrity",
            "hidden camera nude in a locker room",
        ):
            self.assertEqual(classify_explicitness(text).level, DISALLOWED, text)


class AdultPlannerTests(unittest.TestCase):
    def _req(self, **kw):
        return pbase.GenerationRequest(character="x", prompt="p", explicit="explicit", **kw)

    def _caps(self, provider):
        return ProviderCapabilities(provider=provider, targeted_repair=True)

    def test_explicit_plan_is_local_only_even_when_builtin_forced(self) -> None:
        plan = build_plan("codex_builtin", self._req(),
                          local_ready=True, local_request_ready=True,
                          local_caps=self._caps("comfyui"), builtin_caps=self._caps("codex_builtin"))
        self.assertEqual(plan.primary_provider, "comfyui")
        self.assertEqual(plan.strategy, "local-adult")
        self.assertFalse(plan.allow_cross_provider_repair)

    def test_explicit_plan_when_local_unavailable_still_refuses_cloud(self) -> None:
        plan = build_plan("auto", self._req(),
                          local_ready=False, local_request_ready=False,
                          local_caps=self._caps("comfyui"), builtin_caps=self._caps("codex_builtin"))
        self.assertEqual(plan.primary_provider, "comfyui")
        self.assertIn("not downgraded to cloud", plan.reason)


class AdultRegistryTests(unittest.TestCase):
    def test_lustify_spec_optional_and_openrail_licensed(self) -> None:
        spec = model_specs()["lustify_sdxl_v4"]
        self.assertFalse(spec.required)
        self.assertEqual(spec.license, "CreativeML-OpenRAIL-M")
        self.assertTrue(spec.url.startswith("https://huggingface.co/"))

    def test_adult_capability_bundles_checkpoint_and_identity_models(self) -> None:
        keys = capability_model_keys("adult_explicit")
        self.assertEqual(
            set(keys),
            {"lustify_sdxl_v4", "ip_adapter_plus_sdxl_vith", "clip_vision_vith"},
        )

    def test_model_profile_marks_explicit_adult(self) -> None:
        profile = model_profiles()["lustify_sdxl_v4"]
        self.assertIs(profile["explicit_adult_profile"], True)
        self.assertIs(profile["adult_capable"], True)
        self.assertEqual(profile["workflow_profile"], "lustify_sdxl_adult")
        self.assertEqual(profile["architecture"], "sdxl")

    def test_adult_workflow_renders_all_slots(self) -> None:
        wf = WorkflowAdapter("lustify_sdxl_adult")
        self.assertTrue(wf.requires_references)
        self.assertTrue(wf.profile.get("adult_explicit"))
        graph = wf.render(
            positive="a portrait", negative="cartoon",
            model_path="lustifySDXLNSFWSFW_v40.safetensors",
            width=832, height=1216, seed=1, steps=30, cfg=5.0,
            sampler="dpmpp_2m", scheduler="karras",
            reference_names=["ref_a.png", "ref_b.png"],
            ipadapter_weight=0.75,
            ipadapter_file="ip-adapter-plus_sdxl_vit-h.safetensors",
            clip_vision_file="CLIP-ViT-H-14-laion2B-s32B-b79K.safetensors",
        )
        slots = wf.profile["slots"]
        ip_node = graph[slots["ipadapter_weight"]["node"]]
        self.assertEqual(ip_node["inputs"][slots["ipadapter_weight"]["input"]], 0.75)
        seed_node = graph[slots["seed"]["node"]]
        self.assertEqual(seed_node["inputs"][slots["seed"]["input"]], 1)

    def test_adult_workflow_validate_detects_missing_nodes(self) -> None:
        wf = WorkflowAdapter("lustify_sdxl_adult")
        full = set(wf.profile["required_class_types"]) | {
            n["class_type"] for n in wf.graph.values()
        }
        wf.validate(full)  # no raise
        with self.assertRaises(WorkflowError):
            wf.validate({"CheckpointLoaderSimple"})

    def test_resolve_adult_settings_deterministic(self) -> None:
        hw = hwmod.load_cached() or hwmod.detect()
        s = policymod.resolve_adult_settings(hw, aspect="portrait")
        self.assertEqual(s.model_id, "lustify_sdxl_v4")
        self.assertEqual(s.steps, 30)
        self.assertEqual(s.cfg, 5.0)
        self.assertEqual(s.sampler, "dpmpp_2m")
        self.assertEqual(s.scheduler, "karras")
        self.assertEqual(s.batch_size, 1)
        self.assertEqual(s.ipadapter_weight, 0.75)
        self.assertAlmostEqual(s.width / s.height, 832 / 1216, delta=0.05)
        full = policymod.resolve_adult_settings(hw, aspect="full_body")
        self.assertEqual(full.ipadapter_weight, 0.55)


if __name__ == "__main__":
    unittest.main()
