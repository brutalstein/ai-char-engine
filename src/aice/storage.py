from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Any

from .utils import atomic_write_json, read_json, sha256_file, slugify, utc_now

SCHEMA_VERSION = 1


def engine_home(explicit: str | None = None) -> Path:
    raw = explicit or os.environ.get("AICE_HOME") or ".aice"
    return Path(raw).expanduser().resolve()


def character_dir(home: Path, character: str) -> Path:
    return home / "characters" / slugify(character)


def profile_path(char_dir: Path) -> Path:
    return char_dir / "character.json"


def manifest_path(char_dir: Path) -> Path:
    return char_dir / "references" / "manifest.json"


def history_path(char_dir: Path) -> Path:
    return char_dir / "history" / "generations.jsonl"


def create_character(home: Path, display_name: str) -> tuple[Path, dict[str, Any]]:
    slug = slugify(display_name)
    char_dir = character_dir(home, slug)
    if profile_path(char_dir).exists():
        raise FileExistsError(f"Character already exists: {slug}")

    for rel in (
        "references/uploaded",
        "references/golden",
        "references/trusted",
        "references/candidates",
        "references/rejected",
        "outputs/drafts",
        "outputs/approved",
        "outputs/rejected",
        "history",
        "cache",
    ):
        (char_dir / rel).mkdir(parents=True, exist_ok=True)

    profile: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "id": slug,
        "display_name": display_name.strip(),
        "created_at": utc_now(),
        "identity": {
            "adult": True,
            "age_range": "",
            "face": {},
            "skin": {},
            "hair": {},
            "eyes": {},
        },
        "body": {},
        "evidence": {"face": "unknown", "upper_body": "unknown", "full_body": "unknown", "back": "unknown"},
        "permanent_features": [],
        "mutable_state": {},
        "content_style": {
            "preferred": ["photorealistic", "natural", "candid"],
            "avoid": ["repetitive pose", "plastic skin", "CGI look"],
        },
        "hard_rules": [
            "Preserve the exact same adult synthetic character identity.",
            "Do not redesign facial identity, natural skin tone, or stable body proportions.",
            "Keep permanent features only where they are actually visible.",
        ],
    }
    atomic_write_json(profile_path(char_dir), profile)
    atomic_write_json(manifest_path(char_dir), {"schema_version": SCHEMA_VERSION, "references": []})
    return char_dir, profile


def load_profile(home: Path, character: str) -> tuple[Path, dict[str, Any]]:
    char_dir = character_dir(home, character)
    profile = read_json(profile_path(char_dir))
    if profile is None:
        raise FileNotFoundError(f"Unknown character: {slugify(character)}")
    return char_dir, profile


def save_profile(char_dir: Path, profile: dict[str, Any]) -> None:
    if profile.get("schema_version") != SCHEMA_VERSION:
        raise ValueError(f"character.json schema_version must be {SCHEMA_VERSION}")
    if not profile.get("id"):
        raise ValueError("character.json must contain id")
    atomic_write_json(profile_path(char_dir), profile)


def load_manifest(char_dir: Path) -> dict[str, Any]:
    return read_json(manifest_path(char_dir), {"schema_version": SCHEMA_VERSION, "references": []})


def save_manifest(char_dir: Path, manifest: dict[str, Any]) -> None:
    atomic_write_json(manifest_path(char_dir), manifest)


def register_reference(
    char_dir: Path,
    source_path: Path,
    *,
    role: str,
    source: str,
    tier: str,
    tags: list[str] | None = None,
    parent_ids: list[str] | None = None,
    notes: str = "",
    copy_file: bool = True,
) -> dict[str, Any]:
    source_path = source_path.expanduser().resolve()
    if not source_path.is_file():
        raise FileNotFoundError(str(source_path))
    if tier not in {"golden", "trusted", "candidate", "rejected"}:
        raise ValueError("tier must be golden, trusted, candidate, or rejected")
    digest = sha256_file(source_path)
    ref_id = f"{role}-{digest[:12]}"
    manifest = load_manifest(char_dir)
    existing = next((r for r in manifest["references"] if r["sha256"] == digest), None)
    if existing:
        return existing

    ext = source_path.suffix.lower() or ".png"
    destination = char_dir / "references" / ("candidates" if tier == "candidate" else tier) / f"{ref_id}{ext}"
    destination.parent.mkdir(parents=True, exist_ok=True)
    if copy_file:
        shutil.copy2(source_path, destination)
    else:
        destination = source_path

    trust = {"golden": 1.0, "trusted": 0.9, "candidate": 0.5, "rejected": 0.0}[tier]
    record = {
        "id": ref_id,
        "role": role,
        "source": source,
        "tier": tier,
        "trust": trust,
        "tags": sorted(set(tags or [])),
        "parent_ids": parent_ids or [],
        "sha256": digest,
        "path": str(destination.relative_to(char_dir)) if destination.is_relative_to(char_dir) else str(destination),
        "created_at": utc_now(),
        "notes": notes,
        "checks": {},
    }
    manifest["references"].append(record)
    save_manifest(char_dir, manifest)
    return record


def promote_reference(char_dir: Path, ref_id: str, checks: dict[str, str], *, golden: bool = False) -> dict[str, Any]:
    required = {"identity", "anatomy", "stable_traits"}
    missing = required - set(checks)
    if missing:
        raise ValueError(f"Missing required checks: {', '.join(sorted(missing))}")
    if any(str(checks[key]).lower() != "pass" for key in required):
        raise ValueError("Reference cannot be promoted unless all required checks pass")

    manifest = load_manifest(char_dir)
    record = next((r for r in manifest["references"] if r["id"] == ref_id), None)
    if record is None:
        raise KeyError(ref_id)
    if record["tier"] == "rejected":
        raise ValueError("Rejected references cannot be promoted")

    old_path = char_dir / record["path"]
    new_tier = "golden" if golden else "trusted"
    new_dir = char_dir / "references" / new_tier
    new_dir.mkdir(parents=True, exist_ok=True)
    new_path = new_dir / old_path.name
    if old_path.resolve() != new_path.resolve():
        shutil.move(str(old_path), str(new_path))
    record["tier"] = new_tier
    record["trust"] = 1.0 if golden else 0.9
    record["path"] = str(new_path.relative_to(char_dir))
    record["checks"] = {k: str(v).lower() for k, v in checks.items()}
    record["promoted_at"] = utc_now()
    save_manifest(char_dir, manifest)
    return record


def reject_reference(char_dir: Path, ref_id: str, reason: str) -> dict[str, Any]:
    manifest = load_manifest(char_dir)
    record = next((r for r in manifest["references"] if r["id"] == ref_id), None)
    if record is None:
        raise KeyError(ref_id)
    old_path = char_dir / record["path"]
    new_dir = char_dir / "references" / "rejected"
    new_dir.mkdir(parents=True, exist_ok=True)
    new_path = new_dir / old_path.name
    if old_path.exists() and old_path.resolve() != new_path.resolve():
        shutil.move(str(old_path), str(new_path))
    record["tier"] = "rejected"
    record["trust"] = 0.0
    record["path"] = str(new_path.relative_to(char_dir))
    record["rejected_at"] = utc_now()
    record["notes"] = (record.get("notes", "") + f"\nRejected: {reason}").strip()
    save_manifest(char_dir, manifest)
    return record
