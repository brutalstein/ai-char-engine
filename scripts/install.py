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
CANONICAL_REPO = "https://github.com/brutalstein/ai-char-engine.git"
DEFAULT_BRANCH = "main"


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


def _git_output(*args: str, cwd: Path | None = None) -> str:
    proc = subprocess.run(
        ["git", *args], cwd=str(cwd) if cwd else None,
        check=True, capture_output=True, text=True,
    )
    return proc.stdout.strip()


def source_revision(source: Path) -> str:
    try:
        return _git_output("rev-parse", "HEAD", cwd=source)
    except (OSError, subprocess.CalledProcessError):
        return ""


def source_version(source: Path) -> str:
    try:
        manifest = json.loads((source / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8"))
        return str(manifest.get("version", ""))
    except (OSError, json.JSONDecodeError):
        return ""


def install(home: Path, *, run_pip: bool = True, source: Path | None = None) -> dict[str, str]:
    source = (source or repo_root()).resolve()
    target = plugin_target(home)
    action = "updated" if target.exists() else "installed"
    revision = source_revision(source)
    version = source_version(source)
    copy_plugin(source, target)
    market = marketplace_path(home)
    update_marketplace(market)
    if run_pip:
        subprocess.run([sys.executable, "-m", "pip", "install", "-e", str(target)], check=True)
    return {
        "action": action,
        "plugin": str(target),
        "marketplace": str(market),
        "version": version,
        "source_revision": revision,
    }


def latest_source(remote: str | None = None):
    """Yield a clean checkout of the latest default branch without touching user edits."""
    source = repo_root()
    if remote is None:
        try:
            remote = _git_output("remote", "get-url", "origin", cwd=source)
        except (OSError, subprocess.CalledProcessError):
            remote = CANONICAL_REPO

    class _LatestCheckout:
        def __init__(self, repo: str):
            self.repo = repo
            self._tmp: tempfile.TemporaryDirectory[str] | None = None
            self.path: Path | None = None

        def __enter__(self) -> Path:
            if not shutil.which("git"):
                raise RuntimeError("git is required to refresh the latest plugin revision")
            self._tmp = tempfile.TemporaryDirectory()
            self.path = Path(self._tmp.name) / PLUGIN_NAME
            subprocess.run(
                ["git", "clone", "--quiet", "--depth", "1", "--branch", DEFAULT_BRANCH, self.repo, str(self.path)],
                check=True,
            )
            return self.path

        def __exit__(self, exc_type, exc, tb) -> None:
            if self._tmp is not None:
                self._tmp.cleanup()

    return _LatestCheckout(remote)


def main() -> int:
    parser = argparse.ArgumentParser(description="Install or update AI Character Engine as a personal Codex plugin")
    parser.add_argument("--home", default=str(Path.home()), help="Home directory override for testing")
    parser.add_argument("--no-pip", action="store_true", help="Skip editable Python package installation")
    parser.add_argument(
        "--latest", action="store_true",
        help="Install the latest main branch from the repository without modifying the current checkout",
    )
    args = parser.parse_args()
    home = Path(args.home).expanduser().resolve()
    try:
        if args.latest:
            with latest_source() as source:
                result = install(home, run_pip=not args.no_pip, source=source)
        else:
            result = install(home, run_pip=not args.no_pip)
    except (OSError, RuntimeError, subprocess.CalledProcessError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, indent=2), file=sys.stderr)
        return 2
    print(json.dumps({"ok": True, **result, "restart_codex": True}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
