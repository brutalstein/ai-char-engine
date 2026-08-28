from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from aice.comfy import installer as inst
from aice.comfy import models as modelmod


def _cfg(root: Path) -> dict:
    return {
        "schema_version": 1,
        "runtime_dir": str(root / "ComfyUI"),
        "venv_dir": str(root / "venv"),
        "models_dir": str(root / "models"),
        "log_dir": str(root / "logs"),
        "host": "127.0.0.1", "port": 8188, "profile": "rtx_generic",
        "validated": False, "pins": {}, "smoke": {},
    }


class InstallerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.inst = inst.ComfyInstaller(_cfg(self.root))

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_extra_model_paths_yaml_content(self) -> None:
        text = inst.extra_model_paths_yaml(self.root / "models")
        self.assertIn("base_path:", text)
        self.assertIn("diffusion_models: diffusion_models", text)
        self.assertIn("text_encoders: text_encoders", text)
        self.assertIn("vae: vae", text)

    def test_venv_base_python_is_a_list(self) -> None:
        base = inst._venv_base_python()
        self.assertIsInstance(base, list)
        self.assertTrue(base)

    def test_preflight_rejects_low_disk(self) -> None:
        orig = modelmod.free_disk_bytes
        modelmod.free_disk_bytes = lambda _p: 5 * 10**9
        try:
            with self.assertRaises(inst.InstallError):
                self.inst.preflight()
        finally:
            modelmod.free_disk_bytes = orig

    def test_preflight_passes_with_space(self) -> None:
        orig = modelmod.free_disk_bytes
        modelmod.free_disk_bytes = lambda _p: 200 * 10**9
        try:
            report = self.inst.preflight()
            self.assertTrue(report["fresh_install"])
            self.assertGreater(report["estimated_need_gb"], 20)
        finally:
            modelmod.free_disk_bytes = orig

    def test_ensure_extra_model_paths_is_idempotent(self) -> None:
        (self.root / "ComfyUI").mkdir(parents=True)
        self.inst.ensure_extra_model_paths()
        self.inst.ensure_extra_model_paths()
        yaml = self.root / "ComfyUI" / "extra_model_paths.yaml"
        self.assertTrue(yaml.is_file())
        self.assertTrue((self.root / "models" / "diffusion_models").is_dir())

    def test_ensure_models_skips_present_files(self) -> None:
        calls: list[str] = []
        orig_verify, orig_dl = modelmod.verify, modelmod.download
        modelmod.verify = lambda *_a, **_k: (True, "ok")
        modelmod.download = lambda spec, dest, **_k: calls.append(spec.key)
        try:
            fetched = self.inst.ensure_models()
            self.assertEqual(fetched, [])
            self.assertEqual(calls, [])
        finally:
            modelmod.verify, modelmod.download = orig_verify, orig_dl

    def test_ensure_models_downloads_missing(self) -> None:
        got: list[str] = []
        orig_verify, orig_dl = modelmod.verify, modelmod.download
        modelmod.verify = lambda *_a, **_k: (False, "missing")
        modelmod.download = lambda spec, dest, **_k: got.append(spec.key)
        try:
            self.inst.ensure_models(["qwen_image_vae"])
            self.assertEqual(got, ["qwen_image_vae"])
        finally:
            modelmod.verify, modelmod.download = orig_verify, orig_dl

    def test_venv_python_path_under_venv_dir(self) -> None:
        self.assertTrue(str(self.inst.venv_python).startswith(str(self.root / "venv")))

    def test_registry_runtime_pins_are_exact_shas(self) -> None:
        comfy_pin = self.inst.registry["comfyui"]["pin"]
        node_pin = self.inst.registry["custom_nodes"][0]["pin"]
        self.assertEqual(len(comfy_pin), 40)
        self.assertEqual(len(node_pin), 40)
        int(comfy_pin, 16)
        int(node_pin, 16)

    def test_exact_pinned_checkout_is_network_noop(self) -> None:
        target = self.root / "repo"
        (target / ".git").mkdir(parents=True)
        calls: list[list[str]] = []
        orig_sha, orig_run = inst._git_sha, inst._run
        inst._git_sha = lambda _p: "a" * 40
        inst._run = lambda cmd, **_kw: calls.append(cmd) or ""
        try:
            got = inst._ensure_pinned_repo("https://example.invalid/repo.git", target, "a" * 40)
            self.assertEqual(got, "a" * 40)
            self.assertEqual(calls, [])
        finally:
            inst._git_sha, inst._run = orig_sha, orig_run

    def test_mismatched_checkout_fetches_and_detaches_exact_pin(self) -> None:
        target = self.root / "repo"
        (target / ".git").mkdir(parents=True)
        calls: list[list[str]] = []
        shas = iter(["b" * 40, "a" * 40])
        orig_sha, orig_run = inst._git_sha, inst._run
        inst._git_sha = lambda _p: next(shas)
        inst._run = lambda cmd, **_kw: calls.append(cmd) or ""
        try:
            got = inst._ensure_pinned_repo("https://example.invalid/repo.git", target, "a" * 40)
            self.assertEqual(got, "a" * 40)
            self.assertTrue(any("fetch" in cmd for cmd in calls))
            self.assertTrue(any("checkout" in cmd for cmd in calls))
        finally:
            inst._git_sha, inst._run = orig_sha, orig_run


if __name__ == "__main__":
    unittest.main()
