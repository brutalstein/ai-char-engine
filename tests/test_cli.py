from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


class CliTests(unittest.TestCase):
    def run_cli(self, *args: str, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
        env = os.environ.copy()
        src = str(Path(__file__).resolve().parents[1] / "src")
        env["PYTHONPATH"] = src + os.pathsep + env.get("PYTHONPATH", "")
        return subprocess.run(
            [sys.executable, "-m", "aice.cli", *args],
            cwd=str(cwd) if cwd else None,
            env=env,
            text=True,
            capture_output=True,
            check=False,
        )

    def test_end_to_end_deterministic_cli(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            home = root / ".aice"
            seed = root / "seed.png"
            seed.write_bytes(b"seed")
            result = self.run_cli("--home", str(home), "init", "Maya")
            self.assertEqual(result.returncode, 0, result.stderr)
            result = self.run_cli("--home", str(home), "seed", "maya", str(seed), "--tags", "face,front,upper_body")
            self.assertEqual(result.returncode, 0, result.stderr)
            result = self.run_cli("--home", str(home), "context", "maya", "candid cafe portrait", "--compact")
            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["character"], "maya")
            self.assertGreaterEqual(len(payload["references"]), 1)
            result = self.run_cli("--home", str(home), "doctor")
            self.assertEqual(result.returncode, 0, result.stderr)
            doctor = json.loads(result.stdout)
            self.assertFalse(doctor["openai_api_key_required"])

    def test_generated_ref_cannot_enter_golden_directly(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            home = root / ".aice"
            image = root / "x.png"
            image.write_bytes(b"x")
            self.assertEqual(self.run_cli("--home", str(home), "init", "Maya").returncode, 0)
            result = self.run_cli(
                "--home", str(home), "add-ref", "maya", str(image),
                "--role", "face_front", "--source", "generated", "--tier", "golden",
            )
            self.assertEqual(result.returncode, 2)
            self.assertIn("Generated references", result.stderr)


if __name__ == "__main__":
    unittest.main()
