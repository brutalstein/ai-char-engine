from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
manifest = json.loads((ROOT / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8"))
assert manifest["name"] == "ai-char-engine"
assert manifest["skills"].startswith("./")
skill = ROOT / manifest["skills"] / "ai-char-engine" / "SKILL.md"
assert skill.is_file(), skill
text = skill.read_text(encoding="utf-8")
assert text.startswith("---\nname: ai-char-engine\n")
assert "interactive" in text.casefold()
print("plugin validation: ok")
