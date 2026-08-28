from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


class CliTests(unittest.TestCase):
    def run_cli(self, *args: str) -> subprocess.CompletedProcess[str]:
        env = os.environ.copy()
        src = str(Path(__file__).resolve().parents[1] / "src")
        env["PYTHONPATH"] = src + os.pathsep + env.get("PYTHONPATH", "")
        return subprocess.run([sys.executable, "-m", "aice.cli", *args], env=env, text=True, capture_output=True, check=False)

    def test_interactive_begin_and_guide(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            home = Path(td) / ".aice"
            result = self.run_cli("--home", str(home), "begin", "Maya", "--origin", "references")
            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["guide"]["stage"], "collect_references")
            result = self.run_cli("--home", str(home), "guide", "maya")
            self.assertEqual(json.loads(result.stdout)["stage"], "collect_references")

    def test_approved_generated_seed_has_dedicated_path(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            home = root / ".aice"
            seed = root / "generated.png"
            seed.write_bytes(b"generated-seed")
            self.assertEqual(self.run_cli("--home", str(home), "begin", "Nova", "--origin", "scratch").returncode, 0)
            result = self.run_cli("--home", str(home), "approve-seed", "nova", str(seed))
            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["reference"]["source"], "generated_approved")
            self.assertEqual(payload["reference"]["tier"], "golden")

    def test_doctor_needs_no_api_key(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            result = self.run_cli("--home", str(Path(td) / ".aice"), "doctor")
            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(result.stdout)
            self.assertFalse(payload["openai_api_key_required"])
            self.assertTrue(payload["interactive_guide"])
            self.assertIn("Interactive choice", payload["image_backend"])

    def test_observe_and_brain_cli(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            home = root / ".aice"
            seed = root / "seed.png"
            seed.write_bytes(b"seed")
            self.assertEqual(self.run_cli("--home", str(home), "begin", "Maya", "--origin", "references").returncode, 0)
            seed_out = self.run_cli("--home", str(home), "seed", "maya", str(seed), "--tags", "face,front")
            ref_id = json.loads(seed_out.stdout)["reference"]["id"]
            obs = json.dumps({"path": "identity.hair.color", "value": "black", "source_kind": "visual", "source_ref": ref_id})
            result = self.run_cli("--home", str(home), "observe", "maya", "--json", obs)
            self.assertEqual(result.returncode, 0, result.stderr)
            result = self.run_cli("--home", str(home), "brain", "maya")
            self.assertEqual(json.loads(result.stdout)["resolved"]["identity"]["hair"]["color"], "black")

    def test_backend_preference_roundtrip(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            home = Path(td) / ".aice"
            self.assertEqual(self.run_cli("--home", str(home), "begin", "Maya", "--origin", "references").returncode, 0)
            result = self.run_cli("--home", str(home), "backend", "set", "maya", "ask_each_time")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout)["preferences"]["backend"], "ask_each_time")
            result = self.run_cli("--home", str(home), "backend", "reset", "maya")
            self.assertEqual(json.loads(result.stdout)["preferences"]["backend"], "unset")

    def test_top_level_generate_can_plan_codex_builtin(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            home = root / ".aice"
            seed = root / "seed.png"
            seed.write_bytes(b"seed")
            self.assertEqual(self.run_cli("--home", str(home), "begin", "Maya", "--origin", "references").returncode, 0)
            self.assertEqual(self.run_cli("--home", str(home), "seed", "maya", str(seed)).returncode, 0)
            result = self.run_cli(
                "--home", str(home), "generate", "maya", "candid cafe portrait",
                "--backend", "codex_builtin", "--progress",
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["status"], "planned")
            self.assertEqual(payload["backend_effective"], "codex_builtin")
            self.assertTrue(any(x["stage"] == "builtin_planned" for x in payload["trace"]))
            self.assertIn("aice_progress", result.stderr)


if __name__ == "__main__":
    unittest.main()
