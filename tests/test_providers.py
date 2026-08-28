from __future__ import annotations

import unittest
from pathlib import Path

from aice.providers import (
    BackendProbe,
    CodexBuiltinProvider,
    GenerationRequest,
    select_backend,
)
from aice.providers.base import MAX_PROVIDER_REFERENCES
from aice.providers.router import comfy_ready


def _req(**kw) -> GenerationRequest:
    base = dict(character="maya-test", prompt="a candid photo")
    base.update(kw)
    return GenerationRequest(**base)


def _ready_probe(**kw) -> BackendProbe:
    base = dict(
        installed=True,
        configured=True,
        validated=True,
        models_present=True,
        nodes_present=True,
        server_ok=True,
        free_vram_mb=6000,
    )
    base.update(kw)
    return BackendProbe(**base)


class RouterTests(unittest.TestCase):
    def test_auto_uses_comfyui_when_ready(self) -> None:
        backend, warnings = select_backend("auto", _req(), _ready_probe())
        self.assertEqual(backend, "comfyui")
        self.assertEqual(warnings, [])

    def test_auto_falls_back_when_not_installed(self) -> None:
        backend, warnings = select_backend("auto", _req(), BackendProbe(installed=False))
        self.assertEqual(backend, "codex_builtin")
        self.assertTrue(warnings and "not installed" in warnings[0])

    def test_auto_falls_back_when_not_validated(self) -> None:
        backend, _ = select_backend("auto", _req(), _ready_probe(validated=False))
        self.assertEqual(backend, "codex_builtin")

    def test_auto_falls_back_on_low_vram(self) -> None:
        backend, warnings = select_backend("auto", _req(), _ready_probe(free_vram_mb=1200))
        self.assertEqual(backend, "codex_builtin")
        self.assertIn("VRAM", warnings[0])

    def test_unknown_vram_does_not_block(self) -> None:
        backend, _ = select_backend("auto", _req(), _ready_probe(free_vram_mb=None))
        self.assertEqual(backend, "comfyui")

    def test_forced_codex_builtin_always_wins(self) -> None:
        backend, warnings = select_backend("codex_builtin", _req(), _ready_probe())
        self.assertEqual(backend, "codex_builtin")
        self.assertEqual(warnings, [])

    def test_forced_comfyui_reports_but_stays_comfyui(self) -> None:
        backend, warnings = select_backend("comfyui", _req(), BackendProbe(installed=False))
        self.assertEqual(backend, "comfyui")
        self.assertTrue(warnings)

    def test_bad_mode_defaults_to_auto(self) -> None:
        backend, _ = select_backend("nonsense", _req(), _ready_probe())
        self.assertEqual(backend, "comfyui")

    def test_lazy_start_allowed_when_server_down_but_startable(self) -> None:
        ok, _ = comfy_ready(_ready_probe(server_ok=False, can_start=True))
        self.assertTrue(ok)

    def test_missing_nodes_blocks(self) -> None:
        ok, why = comfy_ready(_ready_probe(nodes_present=False))
        self.assertFalse(ok)
        self.assertIn("custom node", why)


class CodexBuiltinTests(unittest.TestCase):
    def test_available(self) -> None:
        ok, _ = CodexBuiltinProvider().available()
        self.assertTrue(ok)

    def test_generate_is_planned_not_pixels(self) -> None:
        p = CodexBuiltinProvider()
        result = p.generate(_req(reference_paths=(Path("a.png"), Path("b.png"))))
        self.assertEqual(result.status, "planned")
        self.assertIsNone(result.output_path)
        self.assertEqual(result.backend, "codex_builtin")
        self.assertEqual(result.effective_settings["references"], ["a.png", "b.png"])

    def test_reference_cap(self) -> None:
        req = _req(reference_paths=tuple(Path(f"{i}.png") for i in range(6)))
        self.assertEqual(len(req.capped_references()), MAX_PROVIDER_REFERENCES)


if __name__ == "__main__":
    unittest.main()
