from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("aice_install", ROOT / "scripts" / "install.py")
module = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(module)


class InstallTests(unittest.TestCase):
    def test_marketplace_update_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / ".agents" / "plugins" / "marketplace.json"
            module.update_marketplace(path)
            module.update_marketplace(path)
            data = json.loads(path.read_text(encoding="utf-8"))
            matches = [p for p in data["plugins"] if p["name"] == "ai-char-engine"]
            self.assertEqual(len(matches), 1)
            self.assertEqual(matches[0]["source"]["path"], "./plugins/ai-char-engine")

    def test_marketplace_preserves_other_plugins(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / ".agents" / "plugins" / "marketplace.json"
            path.parent.mkdir(parents=True)
            path.write_text(json.dumps({"name":"personal","interface":{"displayName":"Mine"},"plugins":[{"name":"other","source":{"source":"local","path":"./plugins/other"},"policy":{"installation":"AVAILABLE","authentication":"ON_INSTALL"},"category":"Productivity"}]}, indent=2), encoding="utf-8")
            module.update_marketplace(path)
            data = json.loads(path.read_text(encoding="utf-8"))
            self.assertTrue(any(p["name"] == "other" for p in data["plugins"]))
            self.assertEqual(data["interface"]["displayName"], "Mine")

    def test_install_is_an_idempotent_add_or_update(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            home = Path(td)
            first = module.install(home, run_pip=False, source=ROOT)
            second = module.install(home, run_pip=False, source=ROOT)
            self.assertEqual(first["action"], "installed")
            self.assertEqual(second["action"], "updated")
            self.assertEqual(second["version"], "0.3.0")
            self.assertTrue((home / "plugins" / "ai-char-engine" / ".codex-plugin" / "plugin.json").is_file())
            market = json.loads((home / ".agents" / "plugins" / "marketplace.json").read_text(encoding="utf-8"))
            self.assertEqual(len([p for p in market["plugins"] if p["name"] == "ai-char-engine"]), 1)

    def test_latest_source_uses_clean_shallow_main_clone(self) -> None:
        commands: list[list[str]] = []

        def fake_run(cmd, **kwargs):
            commands.append(list(cmd))
            return SimpleNamespace(returncode=0, stdout="", stderr="")

        with patch.object(module.shutil, "which", return_value="git"), patch.object(module.subprocess, "run", side_effect=fake_run):
            with module.latest_source("https://example.test/ai-char-engine.git") as source:
                self.assertEqual(source.name, "ai-char-engine")
        self.assertEqual(commands[0][:6], ["git", "clone", "--quiet", "--depth", "1", "--branch"])
        self.assertIn("main", commands[0])
        self.assertIn("https://example.test/ai-char-engine.git", commands[0])


if __name__ == "__main__":
    unittest.main()
