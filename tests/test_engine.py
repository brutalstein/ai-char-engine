from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from aice.brain import add_observations, brain_summary, lock_fact
from aice.engine import bootstrap_plan, build_context, render_generation_prompt
from aice.providers import ux as provider_ux
from aice.providers.router import BackendProbe
from aice.selector import BUDGETS, infer_tags, recent_avoidance, select_references
from aice.storage import (
    create_character,
    get_cached_analysis,
    load_brain,
    load_manifest,
    load_onboarding,
    promote_reference,
    register_reference,
    set_cached_analysis,
)
from aice.utils import compact_json, slugify
from aice.wizard import guide


class EngineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name) / ".aice"
        self.char_dir, _ = create_character(self.home, "Maya Test", origin="references")
        self.seed = Path(self.tmp.name) / "seed.png"
        self.seed.write_bytes(b"fake-png-seed")
        self.seed_ref = register_reference(
            self.char_dir,
            self.seed,
            role="seed",
            source="user_uploaded",
            tier="golden",
            tags=["face", "front", "upper_body"],
        )
        # Unit tests must not change behavior just because the developer has a real
        # validated ComfyUI installation in ~/.aice/runtime.
        self._orig_comfy_probe = provider_ux.safe_comfy_probe
        provider_ux.safe_comfy_probe = lambda: (BackendProbe(installed=False), None)

    def tearDown(self) -> None:
        provider_ux.safe_comfy_probe = self._orig_comfy_probe
        self.tmp.cleanup()

    def _observe(self, path: str, value, ref_id: str | None = None) -> None:
        add_observations(self.char_dir, [{
            "path": path,
            "value": value,
            "source_kind": "visual" if ref_id else "user_asserted",
            "source_ref": ref_id,
        }])

    def test_slugify(self) -> None:
        self.assertEqual(slugify("  Maya Test!! "), "maya-test")

    def test_generated_reference_requires_trusted_parent(self) -> None:
        image = Path(self.tmp.name) / "generated.png"
        image.write_bytes(b"generated")
        with self.assertRaises(ValueError):
            register_reference(self.char_dir, image, role="face_3q_left", source="generated", tier="candidate")

    def test_generated_reference_cannot_enter_trusted_directly(self) -> None:
        image = Path(self.tmp.name) / "generated.png"
        image.write_bytes(b"generated2")
        with self.assertRaises(ValueError):
            register_reference(
                self.char_dir, image, role="face_3q_left", source="generated", tier="trusted",
                parent_ids=[self.seed_ref["id"]],
            )

    def test_promotion_requires_all_checks(self) -> None:
        image = Path(self.tmp.name) / "candidate.png"
        image.write_bytes(b"candidate")
        ref = register_reference(
            self.char_dir, image, role="face_3q_left", source="generated", tier="candidate",
            parent_ids=[self.seed_ref["id"]], tags=["face", "side"],
        )
        with self.assertRaises(ValueError):
            promote_reference(self.char_dir, ref["id"], {"identity": "pass", "anatomy": "fail", "stable_traits": "pass"})

    def test_generated_golden_requires_user_approval(self) -> None:
        image = Path(self.tmp.name) / "body.png"
        image.write_bytes(b"body")
        ref = register_reference(
            self.char_dir, image, role="full_body_front", source="generated", tier="candidate",
            parent_ids=[self.seed_ref["id"]], tags=["full_body", "front"],
        )
        checks = {"identity": "pass", "anatomy": "pass", "stable_traits": "pass"}
        with self.assertRaises(ValueError):
            promote_reference(self.char_dir, ref["id"], checks, golden=True)
        promoted = promote_reference(self.char_dir, ref["id"], checks, golden=True, user_approved=True)
        self.assertEqual(promoted["tier"], "golden")

    def test_brain_visual_evidence_resolves(self) -> None:
        self._observe("identity.hair.color", "jet black", self.seed_ref["id"])
        summary = brain_summary(load_brain(self.char_dir))
        self.assertEqual(summary["resolved"]["identity"]["hair"]["color"], "jet black")
        self.assertIn(self.seed_ref["id"], summary["evidence"]["identity.hair.color"]["sources"])

    def test_brain_near_tie_surfaces_conflict(self) -> None:
        image = Path(self.tmp.name) / "other.png"
        image.write_bytes(b"other")
        other = register_reference(self.char_dir, image, role="face_front", source="user_uploaded", tier="golden", tags=["face", "front"])
        self._observe("identity.eyes.color", "brown", self.seed_ref["id"])
        self._observe("identity.eyes.color", "hazel", other["id"])
        summary = brain_summary(load_brain(self.char_dir))
        self.assertIn("identity.eyes.color", summary["conflicts"])

    def test_user_lock_overrides_conflict(self) -> None:
        image = Path(self.tmp.name) / "other.png"
        image.write_bytes(b"other-lock")
        other = register_reference(self.char_dir, image, role="face_front", source="user_uploaded", tier="golden", tags=["face", "front"])
        self._observe("identity.eyes.color", "brown", self.seed_ref["id"])
        self._observe("identity.eyes.color", "hazel", other["id"])
        lock_fact(self.char_dir, "identity.eyes.color", "dark brown")
        summary = brain_summary(load_brain(self.char_dir))
        self.assertEqual(summary["resolved"]["identity"]["eyes"]["color"], "dark brown")
        self.assertTrue(summary["evidence"]["identity.eyes.color"]["locked"])

    def test_duplicate_observation_does_not_inflate_consensus(self) -> None:
        payload = [{"path": "identity.skin.tone", "value": "fair", "source_kind": "visual", "source_ref": self.seed_ref["id"]}]
        add_observations(self.char_dir, payload)
        add_observations(self.char_dir, payload)
        fact = load_brain(self.char_dir)["facts"]["identity.skin.tone"]
        self.assertEqual(len(fact["observations"]), 1)

    def test_analysis_cache_is_sha_keyed(self) -> None:
        set_cached_analysis(self.char_dir, self.seed_ref["id"], {"summary": "front portrait"})
        hit = get_cached_analysis(self.char_dir, self.seed_ref["id"])
        self.assertEqual(hit["analysis"]["summary"], "front portrait")

    def test_selector_uses_only_trusted_and_budget(self) -> None:
        image = Path(self.tmp.name) / "candidate.png"
        image.write_bytes(b"candidate-selector")
        register_reference(
            self.char_dir, image, role="face_3q_left", source="generated", tier="candidate",
            parent_ids=[self.seed_ref["id"]], tags=["face", "side"],
        )
        refs = select_references(load_manifest(self.char_dir), "natural portrait", "economy")
        self.assertLessEqual(len(refs), BUDGETS["economy"]["max_refs"])
        self.assertTrue(all(r["tier"] in {"golden", "trusted"} for r in refs))

    def test_selector_single_word_geometry_uses_boundaries(self) -> None:
        warm = infer_tags("warm portrait in a cafe")
        elegant = infer_tags("elegant portrait, editorial lighting")
        handbag = infer_tags("portrait with a handbag")
        self.assertNotIn("arms", warm)      # arm must not match warm
        self.assertNotIn("legs", elegant)  # leg must not match elegant
        self.assertNotIn("hands", handbag) # hand must not match handbag

    def test_profile_picture_not_side_profile(self) -> None:
        tags = infer_tags("Instagram profile picture, natural outdoor portrait")
        self.assertIn("face", tags)
        self.assertNotIn("side", tags)

    def test_bootstrap_is_lazy_for_unanchored_body(self) -> None:
        plan = bootstrap_plan(self.home, "maya-test")
        proposal = next(x for x in plan["missing"] if x["role"] == "full_body_front")
        self.assertEqual(proposal["risk"], "high-extrapolation")
        self.assertTrue(proposal["requires_user_approval"])
        blocked = {x["role"] for x in plan["blocked"]}
        self.assertIn("full_body_side", blocked)
        self.assertIn("full_body_back", blocked)

    def test_context_is_token_bounded_and_provenance_grounded(self) -> None:
        self._observe("identity.hair.color", "black", self.seed_ref["id"])
        self._observe("identity.skin.tone", "fair", self.seed_ref["id"])
        self._observe("permanent.wrist_tattoo", {
            "kind": "tattoo", "location": "left_wrist", "description": "small crescent", "visibility_tags": ["hands", "arms"]
        }, self.seed_ref["id"])
        context = build_context(self.home, "maya-test", "selfie holding a drink", "balanced")
        self.assertLessEqual(len(json.dumps(context, ensure_ascii=False, separators=(",", ":"))), BUDGETS["balanced"]["context_chars"])
        prompt = render_generation_prompt(context)
        self.assertIn("small crescent", prompt)
        self.assertIn("exact same adult synthetic character", prompt)

    def test_recent_avoidance_uses_approved_only(self) -> None:
        history = [
            {"status": "approved", "fingerprint": {"pose": "standing"}},
            {"status": "draft", "fingerprint": {"pose": "walking"}},
            {"status": "approved", "fingerprint": {"pose": "standing"}},
        ]
        self.assertIn("avoid repeating pose=standing", recent_avoidance(history, 8))

    def test_wizard_collects_unlimited_refs_until_done(self) -> None:
        state = load_onboarding(self.char_dir)
        self.assertFalse(state["references_closed"])
        result = guide(self.home, "maya-test")
        self.assertEqual(result["stage"], "collect_references")
        for i in range(5):
            image = Path(self.tmp.name) / f"ref-{i}.png"
            image.write_bytes(f"ref-{i}".encode())
            register_reference(self.char_dir, image, role=f"user_{i}", source="user_uploaded", tier="golden", tags=["face"])
        result = guide(self.home, "maya-test")
        self.assertEqual(result["stage"], "collect_references")
        self.assertEqual(result["accepted_count"], 6)

    def test_wizard_from_scratch_requests_seed_description(self) -> None:
        other_home = Path(self.tmp.name) / "scratch-home"
        create_character(other_home, "Nova", origin="scratch")
        result = guide(other_home, "nova")
        self.assertEqual(result["stage"], "describe_seed")

    def test_user_asserted_fact_outweighs_single_golden_observation(self) -> None:
        self._observe("identity.hair.color", "brown", self.seed_ref["id"])
        add_observations(self.char_dir, [{"path": "identity.hair.color", "value": "black", "source_kind": "user_asserted", "source_ref": None}])
        summary = brain_summary(load_brain(self.char_dir))
        self.assertEqual(summary["resolved"]["identity"]["hair"]["color"], "black")

    def test_permanent_detail_omitted_when_region_not_visible(self) -> None:
        self._observe("permanent.left_wrist_tattoo", {
            "kind": "tattoo", "location": "left_wrist", "description": "crescent", "visibility_tags": ["hands", "arms"]
        }, self.seed_ref["id"])
        context = build_context(self.home, "maya-test", "tight face portrait", "balanced")
        self.assertEqual(context["visible_permanent_details"], [])

    def test_rear_scene_does_not_force_front_face_reference(self) -> None:
        rear_path = Path(self.tmp.name) / "rear.png"
        rear_path.write_bytes(b"rear")
        rear = register_reference(self.char_dir, rear_path, role="full_body_back", source="user_uploaded", tier="golden", tags=["full_body", "back", "legs", "arms"])
        refs = select_references(load_manifest(self.char_dir), "full body back view from behind", "economy")
        self.assertEqual(refs[0]["id"], rear["id"])

    def test_mutable_state_is_in_generation_context(self) -> None:
        from aice.storage import load_profile, save_profile
        char_dir, profile = load_profile(self.home, "maya-test")
        profile["mutable_state"] = {"hair_style": "shoulder-length bob"}
        save_profile(char_dir, profile)
        context = build_context(self.home, "maya-test", "natural portrait", "balanced")
        self.assertEqual(context["identity"]["current"]["hair_style"], "shoulder-length bob")

    def test_ready_state_skips_repeated_optional_anchor_question(self) -> None:
        from aice.storage import load_onboarding, save_onboarding
        self._observe("identity.hair.color", "black", self.seed_ref["id"])
        state = load_onboarding(self.char_dir)
        state["references_closed"] = True
        state["ready"] = True
        save_onboarding(self.char_dir, state)
        result = guide(self.home, "maya-test")
        self.assertEqual(result["stage"], "ready")

    def test_wizard_surfaces_brain_conflict(self) -> None:
        from aice.storage import load_onboarding, save_onboarding
        other_path = Path(self.tmp.name) / "conflict.png"
        other_path.write_bytes(b"conflict")
        other = register_reference(self.char_dir, other_path, role="face_front_2", source="user_uploaded", tier="golden", tags=["face", "front"])
        self._observe("identity.eyes.color", "brown", self.seed_ref["id"])
        self._observe("identity.eyes.color", "hazel", other["id"])
        state = load_onboarding(self.char_dir)
        state["references_closed"] = True
        save_onboarding(self.char_dir, state)
        result = guide(self.home, "maya-test")
        self.assertEqual(result["stage"], "resolve_conflicts")
        self.assertIn("identity.eyes.color", result["conflicts"])

    def test_generated_parent_must_not_be_candidate(self) -> None:
        first_path = Path(self.tmp.name) / "first-candidate.png"
        first_path.write_bytes(b"candidate-parent")
        first = register_reference(self.char_dir, first_path, role="face_side", source="generated", tier="candidate", parent_ids=[self.seed_ref["id"]], tags=["face", "side"])
        second_path = Path(self.tmp.name) / "child.png"
        second_path.write_bytes(b"child")
        with self.assertRaises(ValueError):
            register_reference(self.char_dir, second_path, role="face_other", source="generated", tier="candidate", parent_ids=[first["id"]])


if __name__ == "__main__":
    unittest.main()
