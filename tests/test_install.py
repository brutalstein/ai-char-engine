from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

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


if __name__ == "__main__":
    unittest.main()
