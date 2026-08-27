from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path
from typing import Any

from . import __version__
from .brain import add_observations, brain_summary, lock_fact
from .engine import bootstrap_plan, build_context, render_generation_prompt
from .storage import (
    create_character,
    engine_home,
    get_cached_analysis,
    history_path,
    list_characters,
    load_brain,
    load_manifest,
    load_onboarding,
    load_profile,
    promote_reference,
    register_reference,
    reject_reference,
    save_onboarding,
    save_profile,
    set_cached_analysis,
)
from .utils import append_jsonl, parse_json_arg, sha256_file, utc_now
from .wizard import guide

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}


def emit(payload: Any, pretty: bool = True) -> None:
    if isinstance(payload, str):
        print(payload)
    else:
        print(json.dumps(payload, ensure_ascii=False, indent=2 if pretty else None, sort_keys=pretty))


def _image(path: str) -> Path:
    p = Path(path).expanduser().resolve()
    if p.suffix.casefold() not in IMAGE_EXTENSIONS:
        raise ValueError("Image must be PNG, JPEG, or WEBP")
    if not p.is_file():
        raise FileNotFoundError(str(p))
    return p


def cmd_begin(args: argparse.Namespace) -> None:
    home = engine_home(args.home)
    char_dir, profile = create_character(home, args.name, origin=args.origin)
    emit({"ok": True, "character": profile["id"], "path": str(char_dir), "guide": guide(home, profile["id"])})


def cmd_init(args: argparse.Namespace) -> None:
    args.origin = "unknown"
    cmd_begin(args)


def cmd_characters(args: argparse.Namespace) -> None:
    emit(list_characters(engine_home(args.home)))


def cmd_guide(args: argparse.Namespace) -> None:
    emit(guide(engine_home(args.home), args.character))


def cmd_seed(args: argparse.Namespace) -> None:
    home = engine_home(args.home)
    char_dir, _ = load_profile(home, args.character)
    tags = [x.strip() for x in args.tags.split(",") if x.strip()] or ["face", "front"]
    record = register_reference(
        char_dir,
        _image(args.image),
        role="seed",
        source="user_uploaded",
        tier="golden",
        tags=tags,
        notes="Primary user-provided identity reference.",
    )
    emit({"ok": True, "reference": record})


def cmd_approve_seed(args: argparse.Namespace) -> None:
    home = engine_home(args.home)
    char_dir, _ = load_profile(home, args.character)
    tags = [x.strip() for x in args.tags.split(",") if x.strip()] or ["face", "front"]
    record = register_reference(
        char_dir,
        _image(args.image),
        role="seed",
        source="generated_approved",
        tier="golden",
        tags=tags,
        notes="Initial generated seed explicitly approved by the user.",
        user_approved=True,
    )
    emit({"ok": True, "reference": record, "guide": guide(home, args.character)})


def cmd_add_ref(args: argparse.Namespace) -> None:
    home = engine_home(args.home)
    char_dir, _ = load_profile(home, args.character)
    tags = [x.strip() for x in args.tags.split(",") if x.strip()] if args.tags else []
    parents = [x.strip() for x in args.parents.split(",") if x.strip()] if args.parents else []
    record = register_reference(
        char_dir,
        _image(args.image),
        role=args.role,
        source=args.source,
        tier=args.tier,
        tags=tags,
        parent_ids=parents,
        notes=args.notes or "",
    )
    emit({"ok": True, "reference": record})


def cmd_refs_done(args: argparse.Namespace) -> None:
    home = engine_home(args.home)
    char_dir, _ = load_profile(home, args.character)
    state = load_onboarding(char_dir)
    state["references_closed"] = True
    save_onboarding(char_dir, state)
    emit({"ok": True, "guide": guide(home, args.character)})


def cmd_mark_ready(args: argparse.Namespace) -> None:
    home = engine_home(args.home)
    char_dir, _ = load_profile(home, args.character)
    state = load_onboarding(char_dir)
    state["ready"] = True
    save_onboarding(char_dir, state)
    emit({"ok": True, "guide": guide(home, args.character)})


def cmd_promote_ref(args: argparse.Namespace) -> None:
    home = engine_home(args.home)
    char_dir, _ = load_profile(home, args.character)
    checks = parse_json_arg(args.checks)
    if not isinstance(checks, dict):
        raise ValueError("checks must be a JSON object")
    record = promote_reference(
        char_dir,
        args.ref_id,
        checks,
        golden=args.golden,
        user_approved=args.user_approved,
    )
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


def cmd_observe(args: argparse.Namespace) -> None:
    home = engine_home(args.home)
    char_dir, _ = load_profile(home, args.character)
    payload = parse_json_arg(args.json)
    observations = payload if isinstance(payload, list) else [payload]
    if not all(isinstance(x, dict) for x in observations):
        raise ValueError("Observation payload must be an object or list of objects")
    emit({"ok": True, "brain": add_observations(char_dir, observations)})


def cmd_lock_fact(args: argparse.Namespace) -> None:
    home = engine_home(args.home)
    char_dir, _ = load_profile(home, args.character)
    emit({"ok": True, "brain": lock_fact(char_dir, args.path, parse_json_arg(args.value))})


def cmd_brain(args: argparse.Namespace) -> None:
    home = engine_home(args.home)
    char_dir, _ = load_profile(home, args.character)
    emit(brain_summary(load_brain(char_dir)))


def cmd_set_mutable(args: argparse.Namespace) -> None:
    home = engine_home(args.home)
    char_dir, profile = load_profile(home, args.character)
    patch = parse_json_arg(args.json)
    if not isinstance(patch, dict):
        raise ValueError("mutable patch must be a JSON object")
    profile.setdefault("mutable_state", {}).update(patch)
    save_profile(char_dir, profile)
    emit({"ok": True, "mutable_state": profile["mutable_state"]})


def cmd_analysis_get(args: argparse.Namespace) -> None:
    home = engine_home(args.home)
    char_dir, _ = load_profile(home, args.character)
    entry = get_cached_analysis(char_dir, args.ref_id)
    emit({"hit": entry is not None, "entry": entry})


def cmd_analysis_set(args: argparse.Namespace) -> None:
    home = engine_home(args.home)
    char_dir, _ = load_profile(home, args.character)
    payload = parse_json_arg(args.json)
    if not isinstance(payload, dict):
        raise ValueError("analysis payload must be an object")
    emit({"ok": True, "entry": set_cached_analysis(char_dir, args.ref_id, payload)})


def cmd_bootstrap_plan(args: argparse.Namespace) -> None:
    emit(bootstrap_plan(engine_home(args.home), args.character))


def cmd_context(args: argparse.Namespace) -> None:
    emit(build_context(engine_home(args.home), args.character, args.prompt, args.budget), pretty=not args.compact)


def cmd_prompt(args: argparse.Namespace) -> None:
    context = build_context(engine_home(args.home), args.character, args.prompt, args.budget)
    print(render_generation_prompt(context))


def cmd_record(args: argparse.Namespace) -> None:
    home = engine_home(args.home)
    char_dir, profile = load_profile(home, args.character)
    fingerprint = parse_json_arg(args.fingerprint)
    validation = parse_json_arg(args.validation)
    if not isinstance(fingerprint, dict) or not isinstance(validation, dict):
        raise ValueError("fingerprint and validation must be JSON objects")
    image = _image(args.image)
    bucket = {"approved": "approved", "rejected": "rejected"}.get(args.status, "drafts")
    destination_dir = char_dir / "outputs" / bucket
    destination_dir.mkdir(parents=True, exist_ok=True)
    stamp = utc_now().replace(":", "").replace("+00:00", "Z").replace("-", "")
    destination = destination_dir / f"{stamp}-{image.name}"
    shutil.copy2(image, destination)
    row = {
        "id": f"gen-{sha256_file(destination)[:12]}",
        "created_at": utc_now(),
        "character": profile["id"],
        "prompt": args.prompt,
        "status": args.status,
        "budget": args.budget,
        "image": str(destination.relative_to(char_dir)),
        "fingerprint": fingerprint,
        "validation": validation,
    }
    append_jsonl(history_path(char_dir), row)
    emit({"ok": True, "generation": row, "saved": str(destination)})


def cmd_stats(args: argparse.Namespace) -> None:
    home = engine_home(args.home)
    char_dir, profile = load_profile(home, args.character)
    refs = load_manifest(char_dir).get("references", [])
    tiers: dict[str, int] = {}
    for ref in refs:
        tiers[ref["tier"]] = tiers.get(ref["tier"], 0) + 1
    brain = brain_summary(load_brain(char_dir))
    emit({
        "character": profile["id"],
        "references": tiers,
        "resolved_facts": len(brain["evidence"]) - len(brain["conflicts"]),
        "conflicts": len(brain["conflicts"]),
        "onboarding": load_onboarding(char_dir),
    })


def cmd_doctor(args: argparse.Namespace) -> None:
    home = engine_home(args.home)
    home.mkdir(parents=True, exist_ok=True)
    probe = home / ".write-test"
    probe.write_text("ok", encoding="utf-8")
    probe.unlink()
    py_ok = sys.version_info >= (3, 11)
    report = {
        "ok": py_ok,  # core plugin health only; the local backend is optional
        "version": __version__,
        "python": sys.version.split()[0],
        "python_supported": py_ok,
        "home": str(home),
        "home_writable": True,
        "openai_api_key_required": False,
        "image_backend": "Codex built-in image_gen (fallback); local ComfyUI when installed",
        "interactive_guide": True,
    }
    try:  # never let an optional backend fail core doctor
        from .comfy.cli_ops import backend_health

        report["local_image_backend"] = backend_health()
    except Exception as exc:  # noqa: BLE001
        report["local_image_backend"] = {"state": "unavailable", "detail": str(exc)}
    emit(report)


def cmd_comfy(args: argparse.Namespace) -> None:
    from .comfy import cli_ops

    action = args.comfy_action
    if action == "status":
        emit(cli_ops.status())
    elif action == "doctor":
        emit(cli_ops.doctor(smoke=args.smoke))
    elif action == "setup":
        keys = [k.strip() for k in args.models.split(",") if k.strip()] if args.models else None
        emit(cli_ops.setup(model_keys=keys))
    elif action == "start":
        emit(cli_ops.start())
    elif action == "stop":
        emit(cli_ops.stop())
    elif action == "generate":
        from .providers.orchestrator import plan_and_generate, result_ledger_row

        out = plan_and_generate(
            engine_home(args.home), args.character, args.prompt,
            budget=args.budget, backend=args.backend,
            seed=args.seed, out_dir=Path(args.out) if args.out else None,
        )
        result = out["result"]
        emit({
            "ok": result.status != "failed",
            "backend_selected": out["backend_selected"],
            "backend_effective": out["backend_effective"],
            "status": result.status,
            "output_path": str(result.output_path) if result.output_path else None,
            "result": result.to_json(),
            "ledger": result_ledger_row(result),
            "context": out["context"] if args.with_context else None,
        })
    else:  # pragma: no cover - argparse enforces choices
        raise ValueError(f"unknown comfy action: {action}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="aice", description="AI Character Engine internal state CLI")
    parser.add_argument("--version", action="version", version=__version__)
    parser.add_argument("--home", help="State directory (default: AICE_HOME or ./.aice)")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("begin"); p.add_argument("name"); p.add_argument("--origin", choices=["scratch", "references"], required=True); p.set_defaults(func=cmd_begin)
    p = sub.add_parser("init"); p.add_argument("name"); p.set_defaults(func=cmd_init)
    p = sub.add_parser("characters"); p.set_defaults(func=cmd_characters)
    p = sub.add_parser("guide"); p.add_argument("character", nargs="?"); p.set_defaults(func=cmd_guide)
    p = sub.add_parser("seed"); p.add_argument("character"); p.add_argument("image"); p.add_argument("--tags", default="face,front"); p.set_defaults(func=cmd_seed)
    p = sub.add_parser("approve-seed"); p.add_argument("character"); p.add_argument("image"); p.add_argument("--tags", default="face,front,upper_body"); p.set_defaults(func=cmd_approve_seed)
    p = sub.add_parser("add-ref"); p.add_argument("character"); p.add_argument("image"); p.add_argument("--role", required=True); p.add_argument("--source", choices=["user_uploaded", "generated"], default="user_uploaded"); p.add_argument("--tier", choices=["golden", "trusted", "candidate", "rejected"], default="golden"); p.add_argument("--tags", default=""); p.add_argument("--parents", default=""); p.add_argument("--notes", default=""); p.set_defaults(func=cmd_add_ref)
    p = sub.add_parser("refs-done"); p.add_argument("character"); p.set_defaults(func=cmd_refs_done)
    p = sub.add_parser("mark-ready"); p.add_argument("character"); p.set_defaults(func=cmd_mark_ready)
    p = sub.add_parser("promote-ref"); p.add_argument("character"); p.add_argument("ref_id"); p.add_argument("--checks", required=True); p.add_argument("--golden", action="store_true"); p.add_argument("--user-approved", action="store_true"); p.set_defaults(func=cmd_promote_ref)
    p = sub.add_parser("reject-ref"); p.add_argument("character"); p.add_argument("ref_id"); p.add_argument("--reason", required=True); p.set_defaults(func=cmd_reject_ref)
    p = sub.add_parser("list-refs"); p.add_argument("character"); p.add_argument("--tier", choices=["golden", "trusted", "candidate", "rejected"]); p.set_defaults(func=cmd_list_refs)
    p = sub.add_parser("observe"); p.add_argument("character"); p.add_argument("--json", required=True); p.set_defaults(func=cmd_observe)
    p = sub.add_parser("lock-fact"); p.add_argument("character"); p.add_argument("path"); p.add_argument("--value", required=True); p.set_defaults(func=cmd_lock_fact)
    p = sub.add_parser("brain"); p.add_argument("character"); p.set_defaults(func=cmd_brain)
    p = sub.add_parser("set-mutable"); p.add_argument("character"); p.add_argument("--json", required=True); p.set_defaults(func=cmd_set_mutable)
    p = sub.add_parser("analysis-get"); p.add_argument("character"); p.add_argument("ref_id"); p.set_defaults(func=cmd_analysis_get)
    p = sub.add_parser("analysis-set"); p.add_argument("character"); p.add_argument("ref_id"); p.add_argument("--json", required=True); p.set_defaults(func=cmd_analysis_set)
    p = sub.add_parser("bootstrap-plan"); p.add_argument("character"); p.set_defaults(func=cmd_bootstrap_plan)
    p = sub.add_parser("context"); p.add_argument("character"); p.add_argument("prompt"); p.add_argument("--budget", choices=["economy", "balanced", "quality"], default="balanced"); p.add_argument("--compact", action="store_true"); p.set_defaults(func=cmd_context)
    p = sub.add_parser("prompt"); p.add_argument("character"); p.add_argument("prompt"); p.add_argument("--budget", choices=["economy", "balanced", "quality"], default="balanced"); p.set_defaults(func=cmd_prompt)
    p = sub.add_parser("record"); p.add_argument("character"); p.add_argument("image"); p.add_argument("--prompt", required=True); p.add_argument("--fingerprint", default="{}"); p.add_argument("--validation", default="{}"); p.add_argument("--status", choices=["draft", "approved", "rejected"], default="draft"); p.add_argument("--budget", choices=["economy", "balanced", "quality"], default="balanced"); p.set_defaults(func=cmd_record)
    p = sub.add_parser("stats"); p.add_argument("character"); p.set_defaults(func=cmd_stats)
    p = sub.add_parser("doctor"); p.set_defaults(func=cmd_doctor)

    c = sub.add_parser("comfy", help="local ComfyUI image backend (Codex-invoked)")
    csub = c.add_subparsers(dest="comfy_action", required=True)
    csub.add_parser("status").set_defaults(func=cmd_comfy)
    cd = csub.add_parser("doctor"); cd.add_argument("--smoke", action="store_true"); cd.set_defaults(func=cmd_comfy)
    cs = csub.add_parser("setup"); cs.add_argument("--models", default=""); cs.set_defaults(func=cmd_comfy)
    csub.add_parser("start").set_defaults(func=cmd_comfy)
    csub.add_parser("stop").set_defaults(func=cmd_comfy)
    cg = csub.add_parser("generate")
    cg.add_argument("character"); cg.add_argument("prompt")
    cg.add_argument("--budget", choices=["economy", "balanced", "quality"], default="balanced")
    cg.add_argument("--backend", choices=["auto", "comfyui", "codex_builtin"], default="auto")
    cg.add_argument("--seed", type=int, default=None)
    cg.add_argument("--out", default="")
    cg.add_argument("--with-context", action="store_true")
    cg.set_defaults(func=cmd_comfy)
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
