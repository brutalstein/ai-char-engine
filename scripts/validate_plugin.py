from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

manifest = json.loads((ROOT / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8"))
pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
init_text = (ROOT / "src" / "aice" / "__init__.py").read_text(encoding="utf-8")

assert manifest["name"] == "ai-char-engine"
assert manifest["skills"].startswith("./")
assert manifest["interface"]["capabilities"] == ["Read", "Write"]

skill_dir = ROOT / manifest["skills"] / "ai-char-engine"
skill = skill_dir / "SKILL.md"
assert skill.is_file(), skill
text = skill.read_text(encoding="utf-8")
assert text.startswith("---\nname: ai-char-engine\n")
# Product wording evolved from "interactive" to "conversational" in v0.4; both
# describe the same user-facing contract. Validate the behavior rather than a stale keyword.
lower = text.casefold()
assert "interactive" in lower or "conversational" in lower
assert len(text) < 9000, "SKILL.md should stay compact; move cold-path details to references/"

openai_yaml = skill_dir / "agents" / "openai.yaml"
assert openai_yaml.is_file(), openai_yaml
openai_text = openai_yaml.read_text(encoding="utf-8")
assert "allow_implicit_invocation: true" in openai_text
assert "default_prompt:" in openai_text

marketplace_path = ROOT / ".agents" / "plugins" / "marketplace.json"
marketplace = json.loads(marketplace_path.read_text(encoding="utf-8"))
entries = [p for p in marketplace.get("plugins", []) if p.get("name") == "ai-char-engine"]
assert len(entries) == 1
entry = entries[0]
assert entry["source"]["source"] == "url"
assert entry["source"]["url"] == "https://github.com/brutalstein/ai-char-engine.git"
assert entry["source"]["ref"] == "main"
assert entry["policy"]["installation"] == "AVAILABLE"
assert entry["policy"]["authentication"] == "ON_INSTALL"

project_version = re.search(r'^version = "([^"]+)"$', pyproject, re.MULTILINE)
code_version = re.search(r'^__version__ = "([^"]+)"$', init_text, re.MULTILINE)
assert project_version and code_version
assert manifest["version"] == project_version.group(1) == code_version.group(1)

print("plugin validation: ok")
