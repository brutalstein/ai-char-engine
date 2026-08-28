from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from aice.comfy import config as cfgmod


class CapabilityValidationTests(unittest.TestCase):
    def _cfg(self) -> dict:
        return {
            "schema_version": 2,
            "validated": False,
            "validated_capabilities": {},
        }

    def test_capabilities_validate_independently(self) -> None:
        cfg = self._cfg()
        cfgmod.set_capability_validation(cfg, "identity", {"ok": True, "model": "qwen"})
        self.assertTrue(cfgmod.capability_validated(cfg, "identity"))
        self.assertFalse(cfgmod.capability_validated(cfg, "adult_explicit"))
        self.assertTrue(cfg["validated"])

        cfgmod.set_capability_validation(cfg, "adult_explicit", {"ok": False, "error": "oom"})
        self.assertTrue(cfgmod.capability_validated(cfg, "identity"))
        self.assertFalse(cfgmod.capability_validated(cfg, "adult_explicit"))

    def test_invalidating_adult_does_not_disable_identity(self) -> None:
        cfg = self._cfg()
        cfgmod.set_capability_validation(cfg, "identity", {"ok": True})
        cfgmod.set_capability_validation(cfg, "adult_explicit", {"ok": True})
        cfgmod.invalidate_capabilities(cfg, ["adult_explicit"], "adult weights changed")
        self.assertTrue(cfgmod.capability_validated(cfg, "identity"))
        self.assertFalse(cfgmod.capability_validated(cfg, "adult_explicit"))
        self.assertTrue(cfg["validated"])

    def test_legacy_global_validation_migrates_identity_only(self) -> None:
        ledger = cfgmod._migrate_validation({"schema_version": 1, "validated": True, "smoke": {}})
        self.assertTrue(ledger["identity"]["ok"])
        self.assertNotIn("bootstrap", ledger)
        self.assertNotIn("adult_explicit", ledger)

    def test_legacy_adult_smoke_is_preserved_when_present(self) -> None:
        ledger = cfgmod._migrate_validation({
            "schema_version": 1,
            "validated": True,
            "smoke": {"ok": True, "at": "2026-08-28T00:00:00Z", "adult": {"ok": True}},
        })
        self.assertTrue(ledger["identity"]["ok"])
        self.assertTrue(ledger["adult_explicit"]["ok"])

    def test_save_config_derives_legacy_validated_from_identity(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            old = cfgmod.comfy_home
            try:
                cfgmod.comfy_home = lambda: Path(td)
                cfg = self._cfg()
                cfgmod.set_capability_validation(cfg, "adult_explicit", {"ok": True})
                cfgmod.save_config(cfg)
                loaded = cfgmod.load_config()
                self.assertFalse(loaded["validated"])
                self.assertTrue(cfgmod.capability_validated(loaded, "adult_explicit"))
            finally:
                cfgmod.comfy_home = old


if __name__ == "__main__":
    unittest.main()
