from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from aice.providers.router import BackendProbe
from aice.providers.ux import backend_dialog, backend_status
from aice.storage import create_character, get_backend_preference, load_profile, set_backend_preference


def ready_probe() -> BackendProbe:
    return BackendProbe(
        installed=True,
        configured=True,
        validated=True,
        models_present=True,
        nodes_present=True,
        server_ok=True,
        free_vram_mb=6000,
    )


class BackendUxTests(unittest.TestCase):
    def test_new_character_starts_unset(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            home = Path(td) / ".aice"
            _, profile = create_character(home, "Maya", origin="references")
            self.assertEqual(get_backend_preference(profile), "unset")

    def test_unset_asks_when_local_and_builtin_are_ready(self) -> None:
        state = backend_dialog("unset", ready_probe())
        self.assertEqual(state["stage"], "choose_backend")
        self.assertTrue(state["needs_user_choice"])
        self.assertEqual({x["value"] for x in state["choices"]},
                         {"auto", "comfyui", "codex_builtin", "ask_each_time"})

    def test_ask_each_time_asks_when_both_ready(self) -> None:
        state = backend_dialog("ask_each_time", ready_probe())
        self.assertEqual(state["stage"], "choose_backend")

    def test_unset_does_not_ask_when_only_builtin_is_viable(self) -> None:
        state = backend_dialog("unset", BackendProbe(installed=False))
        self.assertEqual(state["stage"], "ready")
        self.assertFalse(state["needs_user_choice"])
        self.assertEqual(state["effective"], "codex_builtin")

    def test_saved_comfy_requires_attention_when_local_is_down(self) -> None:
        state = backend_dialog("comfyui", BackendProbe(installed=False))
        self.assertEqual(state["stage"], "backend_attention")
        self.assertTrue(state["needs_user_choice"])

    def test_auto_recommends_local_when_ready(self) -> None:
        state = backend_dialog("auto", ready_probe())
        self.assertEqual(state["stage"], "ready")
        self.assertEqual(state["effective"], "comfyui")

    def test_preference_persists(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            home = Path(td) / ".aice"
            char_dir, profile = create_character(home, "Maya", origin="references")
            set_backend_preference(char_dir, profile, "ask_each_time")
            _, loaded = load_profile(home, "maya")
            self.assertEqual(get_backend_preference(loaded), "ask_each_time")
            state = backend_status(home, "maya", probe=ready_probe())
            self.assertEqual(state["stage"], "choose_backend")

    def test_invalid_preference_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            home = Path(td) / ".aice"
            char_dir, profile = create_character(home, "Maya", origin="references")
            with self.assertRaises(ValueError):
                set_backend_preference(char_dir, profile, "mystery")


if __name__ == "__main__":
    unittest.main()
