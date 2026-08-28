from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from aice.storage import create_character, load_manifest, promote_reference, register_reference


class ReferenceProvenanceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.home = self.root / ".aice"
        self.char_dir, _ = create_character(self.home, "Maya", origin="references")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _file(self, name: str, content: bytes) -> Path:
        path = self.root / name
        path.write_bytes(content)
        return path

    def test_user_upload_records_user_origin(self) -> None:
        ref = register_reference(self.char_dir, self._file("u.png", b"u"), role="seed",
                                 source="user_uploaded", tier="golden")
        self.assertEqual(ref["origin_provider"], "user")

    def test_approved_seed_can_record_either_provider(self) -> None:
        ref = register_reference(
            self.char_dir, self._file("seed.png", b"seed"), role="seed",
            source="generated_approved", tier="golden", user_approved=True,
            origin_provider="comfyui",
        )
        self.assertEqual(ref["origin_provider"], "comfyui")
        self.assertEqual(ref["tier"], "golden")

    def test_provider_origin_does_not_bypass_candidate_gate(self) -> None:
        parent = register_reference(self.char_dir, self._file("p.png", b"parent"), role="seed",
                                    source="user_uploaded", tier="golden")
        with self.assertRaises(ValueError):
            register_reference(
                self.char_dir, self._file("bad.png", b"bad"), role="side",
                source="generated", tier="trusted", parent_ids=[parent["id"]],
                origin_provider="codex_builtin",
            )

    def test_cross_provider_candidate_can_become_trusted_only_after_checks(self) -> None:
        parent = register_reference(self.char_dir, self._file("p.png", b"parent"), role="seed",
                                    source="user_uploaded", tier="golden")
        child = register_reference(
            self.char_dir, self._file("c.png", b"child"), role="side",
            source="generated", tier="candidate", parent_ids=[parent["id"]],
            origin_provider="comfyui",
        )
        promoted = promote_reference(
            self.char_dir, child["id"],
            {"identity": "pass", "anatomy": "pass", "stable_traits": "pass"},
        )
        self.assertEqual(promoted["tier"], "trusted")
        self.assertEqual(promoted["origin_provider"], "comfyui")

    def test_user_upload_cannot_claim_comfy_origin(self) -> None:
        with self.assertRaises(ValueError):
            register_reference(self.char_dir, self._file("u.png", b"u"), role="seed",
                               source="user_uploaded", tier="golden", origin_provider="comfyui")

    def test_existing_duplicate_backfills_origin_without_duplication(self) -> None:
        path = self._file("same.png", b"same")
        first = register_reference(
            self.char_dir, path, role="seed", source="generated_approved", tier="golden",
            user_approved=True, origin_provider="unknown",
        )
        second = register_reference(
            self.char_dir, path, role="seed", source="generated_approved", tier="golden",
            user_approved=True, origin_provider="codex_builtin",
        )
        self.assertEqual(first["id"], second["id"])
        manifest = load_manifest(self.char_dir)
        self.assertEqual(len(manifest["references"]), 1)
        self.assertEqual(manifest["references"][0]["origin_provider"], "codex_builtin")


if __name__ == "__main__":
    unittest.main()
