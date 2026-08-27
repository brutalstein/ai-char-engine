from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from aice.engine import bootstrap_plan, build_context, render_generation_prompt
from aice.selector import BUDGETS, recent_avoidance, select_references
from aice.storage import (
    create_character,
    load_manifest,
    load_profile,
    promote_reference,
    register_reference,
)
from aice.utils import append_jsonl, compact_json, slugify


class EngineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name) / ".aice"
        self.char_dir, _ = create_character(self.home, "Maya Test")
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

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_slugify(self) -> None:
        self.assertEqual(slugify("  Maya Test!! "), "maya-test")

    def test_initial_bootstrap_is_lazy_for_unanchored_body(self) -> None:
        plan = bootstrap_plan(self.home, "maya-test")
        roles = {x["role"] for x in plan["missing"]}
        self.assertIn("face_3q_left", roles)
        self.assertIn("full_body_front", roles)
        proposal = next(x for x in plan["missing"] if x["role"] == "full_body_front")
        self.assertTrue(proposal["requires_user_approval"])
        blocked = {x["role"] for x in plan["blocked"]}
        self.assertIn("full_body_side", blocked)
        self.assertIn("full_body_back", blocked)

    def test_promoted_body_anchor_unlocks_side_and_back(self) -> None:
        candidate_path = Path(self.tmp.name) / "body.png"
        candidate_path.write_bytes(b"fake-body")
        ref = register_reference(
            self.char_dir,
            candidate_path,
            role="full_body_front",
            source="generated",
            tier="candidate",
            tags=["full_body", "front", "legs", "arms"],
            parent_ids=[self.seed_ref["id"]],
        )
        promote_reference(
            self.char_dir,
            ref["id"],
            {"identity": "pass", "anatomy": "pass", "stable_traits": "pass"},
            golden=True,
        )
        plan = bootstrap_plan(self.home, "maya-test")
        roles = {x["role"] for x in plan["missing"]}
        self.assertIn("full_body_side", roles)
        self.assertIn("full_body_back", roles)
        side = next(x for x in plan["missing"] if x["role"] == "full_body_side")
        self.assertEqual(side["risk"], "derived")
        self.assertIn("full_body_front", side["anchor_id"])

    def test_promotion_requires_all_pass(self) -> None:
        candidate_path = Path(self.tmp.name) / "candidate.png"
        candidate_path.write_bytes(b"candidate")
        ref = register_reference(
            self.char_dir,
            candidate_path,
            role="face_3q_left",
            source="generated",
            tier="candidate",
            tags=["face", "side"],
        )
        with self.assertRaises(ValueError):
            promote_reference(
                self.char_dir,
                ref["id"],
                {"identity": "pass", "anatomy": "fail", "stable_traits": "pass"},
            )

    def test_selector_uses_only_trusted_and_respects_budget(self) -> None:
        trusted_path = Path(self.tmp.name) / "face-side.png"
        trusted_path.write_bytes(b"trusted")
        candidate_path = Path(self.tmp.name) / "candidate-side.png"
        candidate_path.write_bytes(b"candidate")
        register_reference(
            self.char_dir,
            trusted_path,
            role="face_3q_left",
            source="generated",
            tier="trusted",
            tags=["face", "side", "upper_body"],
        )
        register_reference(
            self.char_dir,
            candidate_path,
            role="face_3q_right",
            source="generated",
            tier="candidate",
            tags=["face", "side", "upper_body"],
        )
        refs = select_references(load_manifest(self.char_dir), "natural side profile portrait", "economy")
        self.assertLessEqual(len(refs), BUDGETS["economy"]["max_refs"])
        self.assertTrue(all(r["tier"] in {"golden", "trusted"} for r in refs))
        self.assertFalse(any(r["role"] == "face_3q_right" for r in refs))

    def test_context_reports_geometry_coverage_gap(self) -> None:
        context = build_context(self.home, "maya-test", "full body photo from behind", "balanced")
        self.assertIn("full_body", context["coverage_gaps"])
        self.assertIn("back", context["coverage_gaps"])

    def test_context_is_bounded_and_visibility_aware(self) -> None:
        char_dir, profile = load_profile(self.home, "maya-test")
        profile["identity"]["age_range"] = "28-32"
        profile["identity"]["hair"] = {"color": "black", "length": "long"}
        profile["permanent_features"] = [
            {
                "id": "tattoo-1",
                "kind": "tattoo",
                "location": "left_wrist",
                "description": "small crescent",
                "visibility_tags": ["hands", "arms"],
            }
        ]
        from aice.storage import save_profile
        save_profile(char_dir, profile)

        context = build_context(self.home, "maya-test", "selfie holding a lemonade in one hand", "balanced")
        self.assertLessEqual(len(compact_json(context)), BUDGETS["balanced"]["context_chars"])
        self.assertEqual(context["visible_permanent_details"][0]["id"], "tattoo-1")
        prompt = render_generation_prompt(context)
        self.assertIn("same adult synthetic character", prompt)
        self.assertIn("small crescent", prompt)

    def test_long_inline_json_is_not_treated_as_a_path(self) -> None:
        from aice.utils import parse_json_arg
        payload = {"identity": {"adult": True, "notes": "x" * 500}}
        parsed = parse_json_arg(json.dumps(payload))
        self.assertEqual(parsed["identity"]["notes"], "x" * 500)

    def test_recent_avoidance_uses_fingerprints_not_images(self) -> None:
        history = [
            {"status": "approved", "fingerprint": {"pose": "standing", "gaze": "camera"}},
            {"status": "approved", "fingerprint": {"pose": "standing", "gaze": "camera"}},
            {"status": "approved", "fingerprint": {"pose": "walking", "gaze": "away"}},
        ]
        notes = recent_avoidance(history, 8)
        self.assertIn("avoid repeating pose=standing", notes)
        self.assertIn("avoid repeating gaze=camera", notes)


if __name__ == "__main__":
    unittest.main()
