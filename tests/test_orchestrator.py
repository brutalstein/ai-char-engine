from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from aice.brain import add_observations
from aice.providers import base as pbase
from aice.providers import orchestrator as orch
from aice.providers.base import GenerationResult
from aice.storage import create_character, register_reference


class _FakeProvider:
    def __init__(self, *, ok=True):
        self.ok = ok
        self.seen: pbase.GenerationRequest | None = None

    def probe(self):
        from aice.providers.router import BackendProbe

        return BackendProbe(installed=True, configured=True, validated=True,
                            models_present=True, nodes_present=True, server_ok=True,
                            free_vram_mb=6000)

    def generate(self, req):
        self.seen = req
        if not self.ok:
            return GenerationResult(backend="comfyui", status="failed", error="boom")
        out = Path(tempfile.mkdtemp()) / "img.png"
        out.write_bytes(b"\x89PNG\r\n\x1a\n")
        return GenerationResult(backend="comfyui", status="ok", output_path=out,
                                model_id="qwen", seed=7)


class OrchestratorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name) / ".aice"
        self.char_dir, _ = create_character(self.home, "Maya Orch", origin="references")
        golden = Path(self.tmp.name) / "g.png"
        golden.write_bytes(b"golden-face")
        self.g = register_reference(self.char_dir, golden, role="seed", source="user_uploaded",
                                    tier="golden", tags=["face", "front", "upper_body"])
        cand = Path(self.tmp.name) / "c.png"
        cand.write_bytes(b"candidate-xyz")
        register_reference(self.char_dir, cand, role="face_3q_left", source="generated",
                           tier="candidate", parent_ids=[self.g["id"]], tags=["face", "side"])
        add_observations(self.char_dir, [{"path": "identity.hair.color", "value": "black",
                                          "source_kind": "visual", "source_ref": self.g["id"]}])

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _patch(self, provider):
        orig = orch._safe_comfy_probe
        orch._safe_comfy_probe = lambda: (provider.probe(), provider)
        self.addCleanup(lambda: setattr(orch, "_safe_comfy_probe", orig))

    def test_falls_back_to_codex_when_comfy_unavailable(self) -> None:
        out = orch.plan_and_generate(self.home, "maya-orch", "beach selfie at sunset")
        self.assertEqual(out["backend_effective"], "codex_builtin")
        self.assertEqual(out["result"].status, "planned")

    def test_uses_comfy_when_ready(self) -> None:
        fake = _FakeProvider(ok=True)
        self._patch(fake)
        out = orch.plan_and_generate(self.home, "maya-orch", "hotel lobby candid photo")
        self.assertEqual(out["backend_effective"], "comfyui")
        self.assertTrue(out["result"].output_path.exists())

    def test_auto_falls_back_when_comfy_generate_fails(self) -> None:
        fake = _FakeProvider(ok=False)
        self._patch(fake)
        out = orch.plan_and_generate(self.home, "maya-orch", "portrait", backend="auto")
        self.assertEqual(out["backend_effective"], "codex_builtin")
        self.assertTrue(any("fell back" in w for w in out["result"].warnings))

    def test_no_candidate_reference_leaks_into_request(self) -> None:
        fake = _FakeProvider(ok=True)
        self._patch(fake)
        orch.plan_and_generate(self.home, "maya-orch", "full body outfit photo, standing")
        names = [p.name for p in fake.seen.reference_paths]
        self.assertTrue(names)
        self.assertTrue(all("candidate" not in n and self.g["id"].split("-")[0] in n or "seed" in n
                            for n in names))
        # every path resolves under a golden/trusted bucket
        for p in fake.seen.reference_paths:
            self.assertNotIn("candidates", p.parts)
            self.assertNotIn("rejected", p.parts)

    def test_reference_budget_cap_respected(self) -> None:
        for i in range(4):
            extra = Path(self.tmp.name) / f"extra{i}.png"
            extra.write_bytes(f"extra-golden-{i}".encode())
            register_reference(self.char_dir, extra, role=f"user_{i}", source="user_uploaded",
                               tier="golden", tags=["face", "front"])
        fake = _FakeProvider(ok=True)
        self._patch(fake)
        orch.plan_and_generate(self.home, "maya-orch", "portrait", budget="economy")
        self.assertLessEqual(len(fake.seen.reference_paths), 2)  # economy max_refs


if __name__ == "__main__":
    unittest.main()
