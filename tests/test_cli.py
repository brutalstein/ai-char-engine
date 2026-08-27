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

    def test_doctor_needs_no_api_key(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            result = self.run_cli("--home", str(Path(td) / ".aice"), "doctor")
            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(result.stdout)
            self.assertFalse(payload["openai_api_key_required"])
            self.assertTrue(payload["interactive_guide"])

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


if __name__ == "__main__":
    unittest.main()
