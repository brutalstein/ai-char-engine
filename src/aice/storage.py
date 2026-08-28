from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Any

from .utils import atomic_write_json, read_json, sha256_file, slugify, utc_now

SCHEMA_VERSION = 2
REFERENCE_TIERS = {"golden", "trusted", "candidate", "rejected"}
TRUSTED_TIERS = {"golden", "trusted"}
BACKEND_PREFERENCES = {"unset", "auto", "comfyui", "codex_builtin", "ask_each_time"}


def engine_home(explicit: str | None = None) -> Path:
    raw = explicit or os.environ.get("AICE_HOME") or ".aice"
    return Path(raw).expanduser().resolve()


def character_dir(home: Path, character: str) -> Path:
    return home / "characters" / slugify(character)


def profile_path(char_dir: Path) -> Path:
    return char_dir / "character.json"


def brain_path(char_dir: Path) -> Path:
    return char_dir / "brain.json"


def manifest_path(char_dir: Path) -> Path:
    return char_dir / "references" / "manifest.json"


def history_path(char_dir: Path) -> Path:
    return char_dir / "history" / "generations.jsonl"


def onboarding_path(char_dir: Path) -> Path:
    return char_dir / "onboarding.json"


def analysis_cache_path(char_dir: Path) -> Path:
    return char_dir / "cache" / "analysis.json"


def list_characters(home: Path) -> list[dict[str, str]]:
    root = home / "characters"
    if not root.exists():
        return []
    rows: list[dict[str, str]] = []
    for child in sorted(root.iterdir()):
        if not child.is_dir():
            continue
        profile = read_json(profile_path(child))
        if isinstance(profile, dict) and profile.get("id"):
            rows.append({"id": str(profile["id"]), "display_name": str(profile.get("display_name", profile["id"]))})
    return rows


def create_character(home: Path, display_name: str, *, origin: str = "unknown") -> tuple[Path, dict[str, Any]]:
    if origin not in {"unknown", "scratch", "references"}:
        raise ValueError("origin must be unknown, scratch, or references")
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
        "adult": True,
        "mutable_state": {},
        "generation_preferences": {"backend": "unset"},
        "content_style": {
            "preferred": ["photorealistic", "natural", "candid"],
            "avoid": ["repetitive pose", "plastic skin", "CGI look"],
        },
        "hard_rules": [
            "Preserve the exact same adult synthetic character identity.",
            "Do not redesign grounded facial identity, natural skin tone, or stable body proportions.",
            "Preserve grounded permanent features only when their body region is visible.",
        ],
    }
    brain = {
        "schema_version": SCHEMA_VERSION,
        "facts": {},
        "updated_at": utc_now(),
    }
    manifest = {"schema_version": SCHEMA_VERSION, "references": []}
    onboarding = {
        "schema_version": SCHEMA_VERSION,
        "origin": origin,
        "references_closed": False,
        "ready": False,
        "created_at": utc_now(),
        "updated_at": utc_now(),
    }
    atomic_write_json(profile_path(char_dir), profile)
    atomic_write_json(brain_path(char_dir), brain)
    atomic_write_json(manifest_path(char_dir), manifest)
    atomic_write_json(onboarding_path(char_dir), onboarding)
    atomic_write_json(analysis_cache_path(char_dir), {"schema_version": SCHEMA_VERSION, "entries": {}})
    return char_dir, profile


def _migrate_profile(char_dir: Path, profile: dict[str, Any]) -> dict[str, Any]:
    version = int(profile.get("schema_version", 1))
    if version == SCHEMA_VERSION:
        return profile
    if version != 1:
        raise ValueError(f"Unsupported character schema_version: {version}")
    migrated = {
        "schema_version": SCHEMA_VERSION,
        "id": profile["id"],
        "display_name": profile.get("display_name", profile["id"]),
        "created_at": profile.get("created_at", utc_now()),
        "adult": bool(profile.get("identity", {}).get("adult", True)),
        "mutable_state": profile.get("mutable_state", {}),
        "generation_preferences": {"backend": "unset"},
        "content_style": profile.get("content_style", {"preferred": [], "avoid": []}),
        "hard_rules": profile.get("hard_rules", []),
    }
    atomic_write_json(profile_path(char_dir), migrated)
    if not brain_path(char_dir).exists():
        atomic_write_json(brain_path(char_dir), {"schema_version": SCHEMA_VERSION, "facts": {}, "updated_at": utc_now()})
    if not onboarding_path(char_dir).exists():
        atomic_write_json(onboarding_path(char_dir), {
            "schema_version": SCHEMA_VERSION,
            "origin": "unknown",
            "references_closed": True,
            "ready": False,
            "created_at": utc_now(),
            "updated_at": utc_now(),
        })
    if not analysis_cache_path(char_dir).exists():
        atomic_write_json(analysis_cache_path(char_dir), {"schema_version": SCHEMA_VERSION, "entries": {}})
    return migrated


def load_profile(home: Path, character: str) -> tuple[Path, dict[str, Any]]:
    char_dir = character_dir(home, character)
    profile = read_json(profile_path(char_dir))
    if profile is None:
        raise FileNotFoundError(f"Unknown character: {slugify(character)}")
    return char_dir, _migrate_profile(char_dir, profile)


def get_backend_preference(profile: dict[str, Any]) -> str:
    preference = str(profile.get("generation_preferences", {}).get("backend", "unset"))
    return preference if preference in BACKEND_PREFERENCES else "unset"


def set_backend_preference(char_dir: Path, profile: dict[str, Any], preference: str) -> dict[str, Any]:
    preference = str(preference).strip().casefold()
    if preference not in BACKEND_PREFERENCES:
        raise ValueError(f"backend preference must be one of: {', '.join(sorted(BACKEND_PREFERENCES))}")
    prefs = profile.setdefault("generation_preferences", {})
    prefs["backend"] = preference
    prefs["updated_at"] = utc_now()
    save_profile(char_dir, profile)
    return dict(prefs)


def save_profile(char_dir: Path, profile: dict[str, Any]) -> None:
    if profile.get("schema_version") != SCHEMA_VERSION:
        raise ValueError(f"character.json schema_version must be {SCHEMA_VERSION}")
    if not profile.get("id"):
        raise ValueError("character.json must contain id")
    if profile.get("adult") is not True:
        raise ValueError("This engine is intentionally restricted to adult characters")
    backend = get_backend_preference(profile)
    if backend not in BACKEND_PREFERENCES:  # defensive; getter normalizes invalid values
        raise ValueError("invalid generation backend preference")
    atomic_write_json(profile_path(char_dir), profile)


def load_brain(char_dir: Path) -> dict[str, Any]:
    brain = read_json(brain_path(char_dir), {"schema_version": SCHEMA_VERSION, "facts": {}, "updated_at": utc_now()})
    if brain.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("brain.json schema version mismatch")
    return brain


def save_brain(char_dir: Path, brain: dict[str, Any]) -> None:
    brain["schema_version"] = SCHEMA_VERSION
    brain["updated_at"] = utc_now()
    atomic_write_json(brain_path(char_dir), brain)


def load_onboarding(char_dir: Path) -> dict[str, Any]:
    return read_json(onboarding_path(char_dir), {
        "schema_version": SCHEMA_VERSION,
        "origin": "unknown",
        "references_closed": False,
        "ready": False,
        "created_at": utc_now(),
        "updated_at": utc_now(),
    })


def save_onboarding(char_dir: Path, state: dict[str, Any]) -> None:
    state["schema_version"] = SCHEMA_VERSION
    state["updated_at"] = utc_now()
    atomic_write_json(onboarding_path(char_dir), state)


def load_manifest(char_dir: Path) -> dict[str, Any]:
    manifest = read_json(manifest_path(char_dir), {"schema_version": SCHEMA_VERSION, "references": []})
    if manifest.get("schema_version") == 1:
        manifest["schema_version"] = SCHEMA_VERSION
        save_manifest(char_dir, manifest)
    return manifest


def save_manifest(char_dir: Path, manifest: dict[str, Any]) -> None:
    manifest["schema_version"] = SCHEMA_VERSION
    atomic_write_json(manifest_path(char_dir), manifest)


def _record_by_id(manifest: dict[str, Any], ref_id: str) -> dict[str, Any]:
    record = next((r for r in manifest.get("references", []) if r.get("id") == ref_id), None)
    if record is None:
        raise KeyError(ref_id)
    return record


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
    user_approved: bool = False,
) -> dict[str, Any]:
    source_path = source_path.expanduser().resolve()
    if not source_path.is_file():
        raise FileNotFoundError(str(source_path))
    if source not in {"user_uploaded", "generated", "generated_approved"}:
        raise ValueError("source must be user_uploaded, generated, or generated_approved")
    if tier not in REFERENCE_TIERS:
        raise ValueError("invalid reference tier")
    if source == "generated" and tier != "candidate":
        raise ValueError("Generated references must enter as candidate and pass the quality gate")
    if source == "generated_approved":
        if tier != "golden" or not user_approved or slugify(role) != "seed":
            raise ValueError("generated_approved is reserved for an explicitly approved initial seed")
    parent_ids = parent_ids or []
    manifest = load_manifest(char_dir)
    if source == "generated":
        if not parent_ids:
            raise ValueError("Generated references require at least one trusted parent reference")
        for parent_id in parent_ids:
            parent = _record_by_id(manifest, parent_id)
            if parent.get("tier") not in TRUSTED_TIERS:
                raise ValueError(f"Generated reference parent is not trusted: {parent_id}")

    digest = sha256_file(source_path)
    existing = next((r for r in manifest["references"] if r.get("sha256") == digest), None)
    if existing:
        return existing
    safe_role = slugify(role)
    ref_id = f"{safe_role}-{digest[:12]}"
    ext = source_path.suffix.lower() or ".png"
    bucket = "candidates" if tier == "candidate" else tier
    destination = char_dir / "references" / bucket / f"{ref_id}{ext}"
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source_path, destination)
    trust = {"golden": 1.0, "trusted": 0.9, "candidate": 0.5, "rejected": 0.0}[tier]
    record = {
        "id": ref_id,
        "role": safe_role,
        "source": source,
        "tier": tier,
        "trust": trust,
        "tags": sorted({str(x).strip() for x in (tags or []) if str(x).strip()}),
        "parent_ids": parent_ids,
        "sha256": digest,
        "path": str(destination.relative_to(char_dir)),
        "created_at": utc_now(),
        "notes": notes,
        "checks": {},
    }
    manifest["references"].append(record)
    save_manifest(char_dir, manifest)
    return record


def promote_reference(
    char_dir: Path,
    ref_id: str,
    checks: dict[str, str],
    *,
    golden: bool = False,
    user_approved: bool = False,
) -> dict[str, Any]:
    required = {"identity", "anatomy", "stable_traits"}
    missing = required - set(checks)
    if missing:
        raise ValueError(f"Missing required checks: {', '.join(sorted(missing))}")
    if any(str(checks[key]).casefold() != "pass" for key in required):
        raise ValueError("Reference cannot be promoted unless all required checks pass")
    if golden and not user_approved:
        raise ValueError("Golden promotion requires explicit user approval")
    manifest = load_manifest(char_dir)
    record = _record_by_id(manifest, ref_id)
    if record["tier"] == "rejected":
        raise ValueError("Rejected references cannot be promoted")
    if record["source"] == "generated" and record["tier"] != "candidate":
        raise ValueError("Generated references must pass through candidate state")
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
    record["checks"] = {k: str(v).casefold() for k, v in checks.items()}
    record["promoted_at"] = utc_now()
    if golden:
        record["user_approved_at"] = utc_now()
    save_manifest(char_dir, manifest)
    return record


def reject_reference(char_dir: Path, ref_id: str, reason: str) -> dict[str, Any]:
    manifest = load_manifest(char_dir)
    record = _record_by_id(manifest, ref_id)
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


def get_cached_analysis(char_dir: Path, ref_id: str) -> dict[str, Any] | None:
    manifest = load_manifest(char_dir)
    record = _record_by_id(manifest, ref_id)
    cache = read_json(analysis_cache_path(char_dir), {"schema_version": SCHEMA_VERSION, "entries": {}})
    entry = cache.get("entries", {}).get(record["sha256"])
    return entry if isinstance(entry, dict) else None


def set_cached_analysis(char_dir: Path, ref_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    manifest = load_manifest(char_dir)
    record = _record_by_id(manifest, ref_id)
    cache = read_json(analysis_cache_path(char_dir), {"schema_version": SCHEMA_VERSION, "entries": {}})
    cache.setdefault("entries", {})[record["sha256"]] = {
        "ref_id": ref_id,
        "sha256": record["sha256"],
        "analysis": payload,
        "updated_at": utc_now(),
    }
    cache["schema_version"] = SCHEMA_VERSION
    atomic_write_json(analysis_cache_path(char_dir), cache)
    return cache["entries"][record["sha256"]]
