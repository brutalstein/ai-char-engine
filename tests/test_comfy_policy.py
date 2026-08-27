from __future__ import annotations

import unittest

from aice.comfy.hardware import HardwareProfile, is_blackwell, parse_smi_csv
from aice.comfy import policy


def _hw(**kw) -> HardwareProfile:
    base = dict(gpu_name="NVIDIA GeForce RTX 5070 Laptop GPU", vram_total_mb=8151,
                vram_free_mb=5800, ram_total_mb=32000, driver="610.74",
                is_blackwell=True, has_gpu=True, probed_at="2026-08-28T00:00:00+00:00")
    base.update(kw)
    return HardwareProfile(**base)


class HardwareParseTests(unittest.TestCase):
    def test_parse_smi_csv(self) -> None:
        row = parse_smi_csv("NVIDIA GeForce RTX 5070 Laptop GPU, 8151, 5763, 610.74\n")
        self.assertEqual(row["gpu_name"], "NVIDIA GeForce RTX 5070 Laptop GPU")
        self.assertEqual(row["vram_total_mb"], 8151)
        self.assertEqual(row["vram_free_mb"], 5763)

    def test_parse_smi_csv_garbage(self) -> None:
        self.assertIsNone(parse_smi_csv("no gpu here"))

    def test_is_blackwell(self) -> None:
        self.assertTrue(is_blackwell("NVIDIA GeForce RTX 5070 Laptop GPU"))
        self.assertTrue(is_blackwell("NVIDIA RTX PRO 6000 Blackwell"))
        self.assertFalse(is_blackwell("NVIDIA GeForce RTX 4070 Laptop GPU"))


class PolicyTests(unittest.TestCase):
    def test_classifies_target_machine(self) -> None:
        self.assertEqual(policy.classify(_hw()), "rtx_5070_laptop_8gb")

    def test_classifies_generic_blackwell_8gb(self) -> None:
        self.assertEqual(policy.classify(_hw(gpu_name="NVIDIA GeForce RTX 5060 Laptop GPU")),
                         "blackwell_8gb")

    def test_classifies_big_blackwell(self) -> None:
        self.assertEqual(policy.classify(_hw(gpu_name="NVIDIA GeForce RTX 5090", vram_total_mb=32000)),
                         "blackwell_12gb_plus")

    def test_non_blackwell_uses_int4(self) -> None:
        hw = _hw(gpu_name="NVIDIA GeForce RTX 4070", is_blackwell=False)
        self.assertEqual(policy.classify(hw), "nvidia_generic")
        s = policy.resolve_settings(hw, budget="balanced")
        self.assertIn("int4", s.model_id)

    def test_no_gpu_is_unusable(self) -> None:
        hw = _hw(gpu_name="", has_gpu=False, is_blackwell=False)
        self.assertFalse(policy.PROFILES[policy.classify(hw)].usable)

    def test_8gb_balanced_uses_r128_8step(self) -> None:
        s = policy.resolve_settings(_hw(), budget="balanced", aspect="portrait", free_vram_mb=6000)
        self.assertEqual(s.model_id, policy.QWEN_EDIT_2509_FP4_R128_8STEP)
        self.assertEqual(s.steps, 8)
        self.assertEqual(s.cfg, 1.0)
        self.assertEqual(s.batch_size, 1)
        self.assertLessEqual(s.width * s.height, 1_115_000)

    def test_economy_or_tight_vram_drops_to_low_model(self) -> None:
        eco = policy.resolve_settings(_hw(), budget="economy", free_vram_mb=6000)
        self.assertEqual(eco.model_id, policy.QWEN_EDIT_2509_FP4_R32_4STEP)
        tight = policy.resolve_settings(_hw(), budget="balanced", free_vram_mb=3800)
        self.assertEqual(tight.model_id, policy.QWEN_EDIT_2509_FP4_R32_4STEP)

    def test_full_body_scene_changes_bucket(self) -> None:
        portrait = policy.resolve_settings(_hw(), aspect="portrait", scene_tags=("face",))
        body = policy.resolve_settings(_hw(), aspect="portrait", scene_tags=("full_body", "legs"))
        self.assertNotEqual((portrait.width, portrait.height), (body.width, body.height))
        self.assertGreater(body.height, body.width)

    def test_upscale_only_in_quality_on_8gb(self) -> None:
        self.assertFalse(policy.resolve_settings(_hw(), budget="balanced").upscale)
        self.assertTrue(policy.resolve_settings(_hw(), budget="quality", free_vram_mb=6000).upscale)

    def test_server_args_are_lowvram_on_8gb(self) -> None:
        self.assertIn("--lowvram", policy.server_args(_hw()))

    def test_resolution_multiple_of_32(self) -> None:
        s = policy.resolve_settings(_hw(), aspect="portrait")
        self.assertEqual(s.width % 32, 0)
        self.assertEqual(s.height % 32, 0)


if __name__ == "__main__":
    unittest.main()
