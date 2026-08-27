from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path
from typing import Any

from . import __version__
from .engine import BOOTSTRAP_ROLES, bootstrap_plan, build_context, render_generation_prompt
from .storage import (
    character_dir,
    create_character,
    engine_home,
    history_path,
    load_manifest,
    load_profile,
    promote_reference,
    register_reference,
    reject_reference,
    save_profile,
)
from .utils import append_jsonl, compact_json, parse_json_arg, sha256_file, utc_now

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}


def emit(payload: Any, pretty: bool = True) -> None:
    if isinstance(payload, str):
        print(payload)
        return
    print(json.dumps(payload, ensure_ascii=False, indent=2 if pretty else None, sort_keys=pretty))


def cmd_init(args: argparse.Namespace) -> None:
    home = engine_home(args.home)
    char_dir, profile = create_character(home, args.name)
    emit({"ok": True, "character": profile["id"], "path": str(char_dir), "next": f"aice seed {profile['id']} <image>"})


def cmd_seed(args: argparse.Namespace) -> None:
    home = engine_home(args.home)
    char_dir, _ = load_profile(home, args.character)
    path = Path(args.image)
    if path.suffix.lower() not in IMAGE_EXTENSIONS:
        raise ValueError("Seed must be PNG, JPEG, or WEBP")
    tags = [x.strip() for x in args.tags.split(",") if x.strip()] or ["face", "front"]
    record = register_reference(
        char_dir,
        path,
        role="seed",
        source="user_uploaded",
        tier="golden",
        tags=tags,
        notes="Primary user-approved source of truth.",
    )
    _, profile = load_profile(home, args.character)
    evidence = profile.setdefault("evidence", {})
    for key in ("face", "upper_body", "full_body", "back"):
        if key in tags:
            evidence[key] = "known"
    save_profile(char_dir, profile)
    emit({"ok": True, "reference": record, "next": f"aice bootstrap-plan {args.character}"})


def cmd_profile_template(args: argparse.Namespace) -> None:
    home = engine_home(args.home)
    _, profile = load_profile(home, args.character)
    emit(profile)


def cmd_set_profile(args: argparse.Namespace) -> None:
    home = engine_home(args.home)
    char_dir, existing = load_profile(home, args.character)
    incoming = parse_json_arg(args.json)
    if not isinstance(incoming, dict):
        raise ValueError("Profile payload must be a JSON object")
    protected = {"schema_version": existing["schema_version"], "id": existing["id"], "display_name": existing["display_name"], "created_at": existing["created_at"]}
    merged = dict(existing)
    merged.update(incoming)
    merged.update(protected)
    if merged.get("identity", {}).get("adult") is not True:
        raise ValueError("This engine is intentionally restricted to adult characters")
    save_profile(char_dir, merged)
    emit({"ok": True, "character": existing["id"], "profile": str(char_dir / "character.json")})


def cmd_add_ref(args: argparse.Namespace) -> None:
    home = engine_home(args.home)
    char_dir, _ = load_profile(home, args.character)
    tags = [x.strip() for x in args.tags.split(",") if x.strip()] if args.tags else []
    parent_ids = [x.strip() for x in args.parents.split(",") if x.strip()] if args.parents else []
    tier = args.tier
    if tier == "golden" and args.source != "user_uploaded":
        raise ValueError("Generated references must enter as candidate/trusted; golden promotion requires explicit user approval")
    record = register_reference(
        char_dir,
        Path(args.image),
        role=args.role,
        source=args.source,
        tier=tier,
        tags=tags,
        parent_ids=parent_ids,
        notes=args.notes or "",
    )
    if args.source == "user_uploaded" and tier == "golden":
        _, profile = load_profile(home, args.character)
        evidence = profile.setdefault("evidence", {})
        for key in ("face", "upper_body", "full_body", "back"):
            if key in tags:
                evidence[key] = "known"
        save_profile(char_dir, profile)
    emit({"ok": True, "reference": record})


def cmd_promote_ref(args: argparse.Namespace) -> None:
    home = engine_home(args.home)
    char_dir, _ = load_profile(home, args.character)
    checks = parse_json_arg(args.checks)
    if not isinstance(checks, dict):
        raise ValueError("checks must be a JSON object")
    if args.golden and not args.user_approved:
        raise ValueError("--golden requires --user-approved")
    record = promote_reference(char_dir, args.ref_id, checks, golden=args.golden)
    emit({"ok": True, "reference": record})


def cmd_reject_ref(args: argparse.Namespace) -> None:
    home = engine_home(args.home)
    char_dir, _ = load_profile(home, args.character)
    emit({"ok": True, "reference": reject_reference(char_dir, args.ref_id, args.reason)})


def cmd_list_refs(args: argparse.Namespace) -> None:
    home = engine_home(args.home)
    char_dir, _ = load_profile(home, args.character)
    refs = load_manifest(char_dir).get("references", [])
    if args.tier:
        refs = [r for r in refs if r.get("tier") == args.tier]
    emit(refs)


def cmd_bootstrap_plan(args: argparse.Namespace) -> None:
    emit(bootstrap_plan(engine_home(args.home), args.character))


def cmd_context(args: argparse.Namespace) -> None:
    payload = build_context(engine_home(args.home), args.character, args.prompt, args.budget)
    emit(payload, pretty=not args.compact)


def cmd_prompt(args: argparse.Namespace) -> None:
    payload = build_context(engine_home(args.home), args.character, args.prompt, args.budget)
    print(render_generation_prompt(payload))


def cmd_record(args: argparse.Namespace) -> None:
    home = engine_home(args.home)
    char_dir, profile = load_profile(home, args.character)
    fingerprint = parse_json_arg(args.fingerprint) if args.fingerprint else {}
    if not isinstance(fingerprint, dict):
        raise ValueError("fingerprint must be a JSON object")
    image_path = Path(args.image).expanduser().resolve()
    if not image_path.is_file():
        raise FileNotFoundError(str(image_path))
    if image_path.suffix.lower() not in IMAGE_EXTENSIONS:
        raise ValueError("Output must be PNG, JPEG, or WEBP")
    destination_dir = char_dir / "outputs" / ({"approved": "approved", "rejected": "rejected"}.get(args.status, "drafts"))
    destination_dir.mkdir(parents=True, exist_ok=True)
    stamp = utc_now().replace(":", "").replace("+00:00", "Z").replace("-", "")
    destination = destination_dir / f"{stamp}-{image_path.name}"
    shutil.copy2(image_path, destination)
    row = {
        "id": f"gen-{sha256_file(destination)[:12]}",
        "created_at": utc_now(),
        "character": profile["id"],
        "prompt": args.prompt,
        "status": args.status,
        "budget": args.budget,
        "image": str(destination.relative_to(char_dir)),
        "fingerprint": fingerprint,
        "validation": parse_json_arg(args.validation) if args.validation else {},
    }
    append_jsonl(history_path(char_dir), row)
    emit({"ok": True, "generation": row, "saved": str(destination)})


def cmd_stats(args: argparse.Namespace) -> None:
    home = engine_home(args.home)
    char_dir, profile = load_profile(home, args.character)
    refs = load_manifest(char_dir).get("references", [])
    history_file = history_path(char_dir)
    generations = 0
    statuses: dict[str, int] = {}
    if history_file.exists():
        for line in history_file.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            generations += 1
            row = json.loads(line)
            statuses[row.get("status", "unknown")] = statuses.get(row.get("status", "unknown"), 0) + 1
    tiers: dict[str, int] = {}
    for ref in refs:
        tiers[ref["tier"]] = tiers.get(ref["tier"], 0) + 1
    emit({"character": profile["id"], "references": tiers, "generations": generations, "generation_statuses": statuses})


def cmd_doctor(args: argparse.Namespace) -> None:
    home = engine_home(args.home)
    home.mkdir(parents=True, exist_ok=True)
    probe = home / ".write-test"
    probe.write_text("ok", encoding="utf-8")
    probe.unlink()
    py_ok = sys.version_info >= (3, 11)
    emit({
        "ok": py_ok,
        "version": __version__,
        "python": sys.version.split()[0],
        "python_supported": py_ok,
        "home": str(home),
        "home_writable": True,
        "openai_api_key_required": False,
        "image_backend": "Codex built-in image_gen (invoked by the skill, not this CLI)",
        "note": "Live image generation must be tested inside Codex because the built-in image_gen tool is a Codex capability.",
    })


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="aice", description="AI Character Engine deterministic state CLI")
    parser.add_argument("--version", action="version", version=__version__)
    parser.add_argument("--home", help="State directory (default: AICE_HOME or ./.aice)")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("init", help="Create a new adult synthetic character workspace")
    p.add_argument("name")
    p.set_defaults(func=cmd_init)

    p = sub.add_parser("seed", help="Register the primary user-approved seed image")
    p.add_argument("character")
    p.add_argument("image")
    p.add_argument("--tags", default="face,front", help="Evidence visible in the seed, e.g. face,front,upper_body,full_body")
    p.set_defaults(func=cmd_seed)

    p = sub.add_parser("profile-template", help="Print the current profile JSON for model-assisted filling")
    p.add_argument("character")
    p.set_defaults(func=cmd_profile_template)

    p = sub.add_parser("set-profile", help="Merge model/user supplied JSON into the character profile")
    p.add_argument("character")
    p.add_argument("--json", required=True, help="Inline JSON or path to a JSON file")
    p.set_defaults(func=cmd_set_profile)

    p = sub.add_parser("add-ref", help="Register a reference image")
    p.add_argument("character")
    p.add_argument("image")
    p.add_argument("--role", required=True)
    p.add_argument("--source", choices=["user_uploaded", "generated"], default="generated")
    p.add_argument("--tier", choices=["golden", "trusted", "candidate", "rejected"], default="candidate")
    p.add_argument("--tags", default="")
    p.add_argument("--parents", default="")
    p.add_argument("--notes", default="")
    p.set_defaults(func=cmd_add_ref)

    p = sub.add_parser("promote-ref", help="Promote a validated candidate to trusted/golden")
    p.add_argument("character")
    p.add_argument("ref_id")
    p.add_argument("--checks", required=True, help='JSON/path with identity/anatomy/stable_traits="pass"')
    p.add_argument("--golden", action="store_true")
    p.add_argument("--user-approved", action="store_true")
    p.set_defaults(func=cmd_promote_ref)

    p = sub.add_parser("reject-ref", help="Reject a candidate reference")
    p.add_argument("character")
    p.add_argument("ref_id")
    p.add_argument("--reason", required=True)
    p.set_defaults(func=cmd_reject_ref)

    p = sub.add_parser("list-refs", help="List reference metadata")
    p.add_argument("character")
    p.add_argument("--tier", choices=["golden", "trusted", "candidate", "rejected"])
    p.set_defaults(func=cmd_list_refs)

    p = sub.add_parser("bootstrap-plan", help="Return only missing identity-reference generation tasks")
    p.add_argument("character")
    p.set_defaults(func=cmd_bootstrap_plan)

    p = sub.add_parser("context", help="Compile a token-bounded generation context")
    p.add_argument("character")
    p.add_argument("prompt")
    p.add_argument("--budget", choices=["economy", "balanced", "quality"], default="balanced")
    p.add_argument("--compact", action="store_true")
    p.set_defaults(func=cmd_context)

    p = sub.add_parser("prompt", help="Render the compact image-generation prompt")
    p.add_argument("character")
    p.add_argument("prompt")
    p.add_argument("--budget", choices=["economy", "balanced", "quality"], default="balanced")
    p.set_defaults(func=cmd_prompt)

    p = sub.add_parser("record", help="Persist a generated output and its compact content fingerprint")
    p.add_argument("character")
    p.add_argument("image")
    p.add_argument("--prompt", required=True)
    p.add_argument("--fingerprint", default="{}", help="Inline JSON or JSON path")
    p.add_argument("--validation", default="{}", help="Inline JSON or JSON path")
    p.add_argument("--status", choices=["draft", "approved", "rejected"], default="draft")
    p.add_argument("--budget", choices=["economy", "balanced", "quality"], default="balanced")
    p.set_defaults(func=cmd_record)

    p = sub.add_parser("stats", help="Show compact character/reference/generation stats")
    p.add_argument("character")
    p.set_defaults(func=cmd_stats)

    p = sub.add_parser("doctor", help="Check deterministic local prerequisites")
    p.set_defaults(func=cmd_doctor)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        args.func(args)
        return 0
    except (FileNotFoundError, FileExistsError, ValueError, KeyError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
