from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from aice.comfy.models import (
    capability_model_keys,
    capability_ready,
    load_registry,
    missing_required,
    model_specs,
    verify,
)
from aice.comfy.workflow import WorkflowAdapter, WorkflowError

_EDIT_NODES = {
    "UnetLoaderGGUF", "LoraLoaderModelOnly", "CLIPLoader", "VAELoader",
    "ModelSamplingAuraFlow", "CFGNorm", "TextEncodeQwenImageEditPlus",
    "EmptySD3LatentImage", "KSampler", "VAEDecode", "SaveImage",
    "LoadImage", "ImageScaleToTotalPixels",
}
_T2I_NODES = {
    "UnetLoaderGGUF", "LoraLoaderModelOnly", "CLIPLoader", "VAELoader",
    "ModelSamplingAuraFlow", "CFGNorm", "CLIPTextEncode",
    "EmptySD3LatentImage", "KSampler", "VAEDecode", "SaveImage",
}


class RegistryTests(unittest.TestCase):
    def test_registry_has_required_identity_models(self) -> None:
        req = [k for k, s in model_specs().items() if s.required]
        self.assertIn("qwen_image_edit_2509_gguf_q3km", req)
        self.assertIn("qwen_image_edit_2509_lightning_8step", req)
        self.assertIn("qwen_2.5_vl_7b_fp8_scaled", req)
        self.assertIn("qwen_image_vae", req)

    def test_bootstrap_models_are_optional_and_capability_scoped(self) -> None:
        keys = capability_model_keys("bootstrap")
        self.assertIn("qwen_image_t2i_gguf_q3km", keys)
        self.assertIn("qwen_image_t2i_lightning_8step", keys)
        specs = model_specs()
        self.assertFalse(specs["qwen_image_t2i_gguf_q3km"].required)
        self.assertFalse(specs["qwen_image_t2i_lightning_8step"].required)

    def test_bootstrap_exact_file_metadata(self) -> None:
        specs = model_specs()
        model = specs["qwen_image_t2i_gguf_q3km"]
        lora = specs["qwen_image_t2i_lightning_8step"]
        self.assertEqual(model.size_bytes, 9679567392)
        self.assertEqual(model.sha256, "ff96f80b90f8234e498c803965857d7850f89011dde805f83f1e80aa741bcdfb")
        self.assertEqual(lora.size_bytes, 1698951104)
        self.assertEqual(lora.sha256, "07b5a999881437f63124979844ba1949ce2438f65b6220628a196a7d30a4fff9")

    def test_all_model_urls_https_huggingface(self) -> None:
        for spec in model_specs().values():
            self.assertTrue(spec.url.startswith("https://huggingface.co/"), spec.url)

    def test_all_models_have_known_license(self) -> None:
        # Identity/bootstrap stack is Apache-2.0; the adult SDXL checkpoint ships
        # under CreativeML-OpenRAIL-M.
        allowed = {"Apache-2.0", "CreativeML-OpenRAIL-M"}
        for spec in model_specs().values():
            self.assertIn(spec.license, allowed, spec.filename)

    def test_missing_required_detects_absent_files(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            self.assertTrue(missing_required(Path(td)))
            self.assertFalse(capability_ready(Path(td), "bootstrap"))

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
        self.assertEqual(reg["schema_version"], 2)
        self.assertEqual(reg["comfyui"]["version"], "0.34.0")
        self.assertEqual(reg["comfyui"]["pin"], "12d5279438bfefc058a269eae805ceab6047777f")
        self.assertEqual(reg["custom_nodes"][0]["pin"], "6ea2651e7df66d7585f6ffee804b20e92fb38b8a")
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
        self.wf.validate(_EDIT_NODES)

    def test_validate_fails_with_missing_node(self) -> None:
        with self.assertRaises(WorkflowError) as ctx:
            self.wf.validate(_EDIT_NODES - {"UnetLoaderGGUF"})
        self.assertIn("UnetLoaderGGUF", str(ctx.exception))

    def test_render_patches_only_semantic_slots(self) -> None:
        g = self._render(["r1.png"])
        self.assertEqual(g["3"]["inputs"]["seed"], 42)
        self.assertEqual(g["3"]["inputs"]["steps"], 8)
        self.assertEqual(g["112"]["inputs"]["width"], 896)
        self.assertEqual(g["115"]["inputs"]["unet_name"], "model.safetensors")
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

    def test_text_to_image_bootstrap_needs_no_reference(self) -> None:
        wf = WorkflowAdapter("qwen_text_to_image")
        self.assertFalse(wf.requires_references)
        wf.validate(_T2I_NODES)
        graph = wf.render(
            positive="original adult synthetic woman, natural portrait", negative="",
            model_path="qwen-image-Q3_K_M.gguf", lora_name="lightning.safetensors",
            width=896, height=1216, seed=99, steps=8, cfg=1.0,
            sampler="euler", scheduler="simple", reference_names=[],
            output_prefix="AICE_BOOTSTRAP",
        )
        self.assertEqual(graph["37"]["inputs"]["unet_name"], "qwen-image-Q3_K_M.gguf")
        self.assertEqual(graph["73"]["inputs"]["lora_name"], "lightning.safetensors")
        self.assertEqual(graph["6"]["inputs"]["text"], "original adult synthetic woman, natural portrait")
        self.assertEqual(graph["58"]["inputs"]["width"], 896)
        self.assertEqual(graph["3"]["inputs"]["seed"], 99)


if __name__ == "__main__":
    unittest.main()
