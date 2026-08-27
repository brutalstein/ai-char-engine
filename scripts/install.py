from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

PLUGIN_NAME = "ai-char-engine"


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def plugin_target(home: Path) -> Path:
    return home / "plugins" / PLUGIN_NAME


def marketplace_path(home: Path) -> Path:
    return home / ".agents" / "plugins" / "marketplace.json"


def update_marketplace(path: Path) -> dict[str, Any]:
    if path.exists():
        data = json.loads(path.read_text(encoding="utf-8"))
    else:
        data = {"name": "personal", "interface": {"displayName": "Personal Plugins"}, "plugins": []}
    data.setdefault("name", "personal")
    data.setdefault("interface", {}).setdefault("displayName", "Personal Plugins")
    plugins = data.setdefault("plugins", [])
    entry = {
        "name": PLUGIN_NAME,
        "source": {"source": "local", "path": f"./plugins/{PLUGIN_NAME}"},
        "policy": {"installation": "AVAILABLE", "authentication": "ON_INSTALL"},
        "category": "Productivity",
    }
    replaced = False
    for index, existing in enumerate(plugins):
        if existing.get("name") == PLUGIN_NAME:
            plugins[index] = entry
            replaced = True
            break
    if not replaced:
        plugins.append(entry)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return data


def copy_plugin(source: Path, target: Path) -> None:
    source = source.resolve()
    target = target.resolve()
    if source == target:
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=str(target.parent)) as td:
        staging = Path(td) / PLUGIN_NAME
        shutil.copytree(
            source,
            staging,
            ignore=shutil.ignore_patterns(".git", ".aice", ".venv", "venv", "__pycache__", "*.egg-info", "build", "dist"),
        )
        if target.exists():
            shutil.rmtree(target)
        shutil.move(str(staging), str(target))


def install(home: Path, *, run_pip: bool = True) -> dict[str, str]:
    source = repo_root()
    target = plugin_target(home)
    copy_plugin(source, target)
    market = marketplace_path(home)
    update_marketplace(market)
    if run_pip:
        subprocess.run([sys.executable, "-m", "pip", "install", "-e", str(target)], check=True)
    return {"plugin": str(target), "marketplace": str(market)}


def main() -> int:
    parser = argparse.ArgumentParser(description="Install AI Character Engine as a personal Codex plugin")
    parser.add_argument("--home", default=str(Path.home()), help="Home directory override for testing")
    parser.add_argument("--no-pip", action="store_true", help="Skip editable Python package installation")
    args = parser.parse_args()
    result = install(Path(args.home).expanduser().resolve(), run_pip=not args.no_pip)
    print(json.dumps({"ok": True, **result, "restart_codex": True}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
