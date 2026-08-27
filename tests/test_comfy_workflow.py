from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from aice.comfy.models import load_registry, missing_required, model_specs, verify
from aice.comfy.workflow import WorkflowAdapter, WorkflowError

_ALL_NODES = {
    "NunchakuQwenImageDiTLoader", "CLIPLoader", "VAELoader", "ModelSamplingAuraFlow",
    "CFGNorm", "TextEncodeQwenImageEditPlus", "EmptySD3LatentImage", "KSampler",
    "VAEDecode", "SaveImage", "LoadImage", "ImageScaleToTotalPixels",
}


class RegistryTests(unittest.TestCase):
    def test_registry_has_required_models(self) -> None:
        req = [k for k, s in model_specs().items() if s.required]
        self.assertIn("qwen_image_edit_2509_fp4_r128_lightning8", req)
        self.assertIn("qwen_2.5_vl_7b_fp8_scaled", req)
        self.assertIn("qwen_image_vae", req)

    def test_all_model_urls_https_huggingface(self) -> None:
        for spec in model_specs().values():
            self.assertTrue(spec.url.startswith("https://huggingface.co/"), spec.url)

    def test_all_models_apache_licensed(self) -> None:
        for spec in model_specs().values():
            self.assertEqual(spec.license, "Apache-2.0")

    def test_missing_required_detects_absent_files(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            self.assertTrue(missing_required(Path(td)))

    def test_verify_reports_size_mismatch(self) -> None:
        spec = next(iter(model_specs().values()))
        with tempfile.TemporaryDirectory() as td:
            f = Path(td) / spec.filename
            f.write_bytes(b"x" * 10)
            ok, why = verify(f, spec)
            self.assertFalse(ok)
            self.assertIn("size", why)

    def test_comfyui_and_torch_pins(self) -> None:
        reg = load_registry()
        self.assertEqual(reg["comfyui"]["min_version"], "0.3.60")
        self.assertEqual(reg["torch"]["index_url"], "https://download.pytorch.org/whl/cu130")


class WorkflowAdapterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.wf = WorkflowAdapter("qwen_edit_identity")

    def _render(self, refs):
        return self.wf.render(
            positive="candid photo in Milan", negative="", model_path="model.safetensors",
            width=896, height=1216, seed=42, steps=8, cfg=1.0, sampler="euler",
            scheduler="simple", reference_names=refs,
        )

    def test_validate_passes_with_all_nodes(self) -> None:
        self.wf.validate(_ALL_NODES)

    def test_validate_fails_with_missing_node(self) -> None:
        with self.assertRaises(WorkflowError) as ctx:
            self.wf.validate(_ALL_NODES - {"NunchakuQwenImageDiTLoader"})
        self.assertIn("NunchakuQwenImageDiTLoader", str(ctx.exception))

    def test_render_patches_only_semantic_slots(self) -> None:
        g = self._render(["r1.png"])
        self.assertEqual(g["3"]["inputs"]["seed"], 42)
        self.assertEqual(g["3"]["inputs"]["steps"], 8)
        self.assertEqual(g["112"]["inputs"]["width"], 896)
        self.assertEqual(g["115"]["inputs"]["model_path"], "model.safetensors")
        self.assertEqual(g["111"]["inputs"]["prompt"], "candid photo in Milan")
        self.assertEqual(g["60"]["inputs"]["filename_prefix"], "AICE")

    def test_render_one_reference_prunes_other_slots(self) -> None:
        g = self._render(["only.png"])
        self.assertEqual(g["78"]["inputs"]["image"], "only.png")
        self.assertNotIn("106", g)
        self.assertNotIn("107", g)
        self.assertNotIn("image2", g["111"]["inputs"])
        self.assertNotIn("image3", g["110"]["inputs"])

    def test_render_three_references_keeps_all(self) -> None:
        g = self._render(["a.png", "b.png", "c.png"])
        self.assertEqual(g["106"]["inputs"]["image"], "b.png")
        self.assertEqual(g["108"]["inputs"]["image"], "c.png")
        self.assertIn("image3", g["111"]["inputs"])

    def test_render_requires_a_reference(self) -> None:
        with self.assertRaises(WorkflowError):
            self._render([])

    def test_workflow_hash_stable(self) -> None:
        self.assertEqual(self.wf.workflow_hash(), self.wf.workflow_hash())
        self.assertRegex(self.wf.workflow_hash(), r"^[0-9a-f]{16}$")

    def test_extra_references_ignored(self) -> None:
        g = self._render(["a.png", "b.png", "c.png", "d.png"])
        self.assertEqual(g["108"]["inputs"]["image"], "c.png")


if __name__ == "__main__":
    unittest.main()
