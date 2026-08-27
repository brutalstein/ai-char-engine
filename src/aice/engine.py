from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .selector import BUDGETS, infer_tags, recent_avoidance, select_references, visible_permanent_features
from .storage import history_path, load_manifest, load_profile
from .utils import compact_json, read_jsonl

BOOTSTRAP_ROLES: list[dict[str, Any]] = [
    {"role": "face_front", "tags": ["face", "front", "upper_body"], "framing": "neutral head-and-shoulders front view"},
    {"role": "face_3q_left", "tags": ["face", "side", "upper_body"], "framing": "neutral left three-quarter head-and-shoulders view"},
    {"role": "face_3q_right", "tags": ["face", "side", "upper_body"], "framing": "neutral right three-quarter head-and-shoulders view"},
    {"role": "full_body_front", "tags": ["full_body", "front", "legs", "arms"], "framing": "neutral full-body front view, head to toe"},
    {"role": "full_body_side", "tags": ["full_body", "side", "legs", "arms"], "framing": "neutral full-body side view, head to toe"},
    {"role": "full_body_back", "tags": ["full_body", "back", "legs", "arms"], "framing": "neutral full-body rear view, head to toe"},
]


def identity_summary(profile: dict[str, Any]) -> dict[str, Any]:
    identity = profile.get("identity", {})
    body = profile.get("body", {})
    summary: dict[str, Any] = {}
    for key in ("adult", "age_range"):
        value = identity.get(key)
        if value not in (None, "", {}, []):
            summary[key] = value
    for key in ("face", "skin", "hair", "eyes"):
        value = identity.get(key)
        if value:
            summary[key] = value
    if body:
        summary["body"] = body
    return summary


def coverage_gaps(manifest: dict[str, Any], prompt: str) -> list[str]:
    wanted = infer_tags(prompt)
    trusted = [r for r in manifest.get("references", []) if r.get("tier") in {"golden", "trusted"}]
    available = set()
    for ref in trusted:
        available.update(ref.get("tags", []))
    gaps: list[str] = []
    for tag in ("face", "full_body", "side", "back"):
        if tag in wanted and tag not in available:
            gaps.append(tag)
    return gaps


def build_context(home: Path, character: str, prompt: str, budget: str = "balanced") -> dict[str, Any]:
    if budget not in BUDGETS:
        raise ValueError(f"Unknown budget: {budget}")
    char_dir, profile = load_profile(home, character)
    manifest = load_manifest(char_dir)
    refs = select_references(manifest, prompt, budget)
    if not refs:
        raise ValueError("No golden/trusted identity references are available. Register a seed or trusted reference first.")
    tags = infer_tags(prompt)
    history = read_jsonl(history_path(char_dir))
    avoidance = recent_avoidance(history, BUDGETS[budget]["history"])
    details = visible_permanent_features(profile, prompt, tags)
    payload: dict[str, Any] = {
        "character": profile["id"],
        "budget": budget,
        "request": prompt,
        "identity": identity_summary(profile),
        "hard_rules": profile.get("hard_rules", [])[:4],
        "visible_permanent_details": details[:4],
        "references": [
            {
                "id": ref["id"],
                "path": str((char_dir / ref["path"]).resolve()),
                "role": ref["role"],
                "tier": ref["tier"],
                "trust": ref["trust"],
            }
            for ref in refs
        ],
        "avoid_recent": avoidance,
        "coverage_gaps": coverage_gaps(manifest, prompt),
        "validation": BUDGETS[budget]["validation"],
        "max_repairs": BUDGETS[budget]["repairs"],
    }
    return trim_context(payload, BUDGETS[budget]["context_chars"])


def trim_context(payload: dict[str, Any], max_chars: int) -> dict[str, Any]:
    result = json.loads(json.dumps(payload))
    if len(compact_json(result)) <= max_chars:
        return result
    result["avoid_recent"] = result.get("avoid_recent", [])[:2]
    if len(compact_json(result)) <= max_chars:
        return result
    result["hard_rules"] = result.get("hard_rules", [])[:2]
    if len(compact_json(result)) <= max_chars:
        return result
    identity = result.get("identity", {})
    for key in ("face", "body"):
        value = identity.get(key)
        if isinstance(value, dict) and len(value) > 3:
            identity[key] = dict(list(value.items())[:3])
    if len(compact_json(result)) <= max_chars:
        return result
    result["visible_permanent_details"] = result.get("visible_permanent_details", [])[:2]
    if len(compact_json(result)) <= max_chars:
        return result
    raise ValueError(f"Compiled context still exceeds budget ({max_chars} chars). Simplify character metadata.")


def render_generation_prompt(context: dict[str, Any]) -> str:
    ref_roles = "; ".join(f"Image {i+1}={r['role']}" for i, r in enumerate(context.get("references", [])))
    detail_lines = "; ".join(
        f"{d.get('kind')} at {d.get('location')}: {d.get('description')}" for d in context.get("visible_permanent_details", [])
    )
    avoid_recent = "; ".join(context.get("avoid_recent", []))
    identity = compact_json(context.get("identity", {}))
    parts = [
        "Use case: photorealistic-natural",
        "Asset type: personal virtual-creator photograph",
        f"Primary request: {context['request']}",
        f"Identity contract: use the loaded references as the exact same adult synthetic character; preserve recognizable face, natural skin tone, hair identity, and stable body proportions. Compact traits: {identity}",
    ]
    if ref_roles:
        parts.append(f"Input images: {ref_roles}; identity references, not edit targets.")
    if detail_lines:
        parts.append(f"Visible permanent details to preserve exactly when visible: {detail_lines}")
    if avoid_recent:
        parts.append(f"Controlled diversity: {avoid_recent}; choose a natural alternative without changing identity.")
    parts.extend(
        [
            "Style/medium: ultra-realistic natural photography; believable skin texture, anatomy, optics, lighting, and casual human imperfection.",
            "Composition/framing: follow the user's requested camera relationship; avoid defaulting to the same direct gaze or repeated pose unless explicitly requested.",
            "Constraints: same person, adult, realistic anatomy, no text, no watermark, no identity redesign, no gratuitous body exaggeration.",
        ]
    )
    return "\n".join(parts)


def bootstrap_plan(home: Path, character: str) -> dict[str, Any]:
    char_dir, profile = load_profile(home, character)
    manifest = load_manifest(char_dir)
    trusted = [r for r in manifest.get("references", []) if r.get("tier") in {"golden", "trusted"}]
    trusted_roles = {r["role"] for r in trusted}
    seed = next((r for r in trusted if r.get("role") == "seed" and r.get("tier") == "golden"), None)
    if seed is None:
        raise ValueError("A golden seed reference is required. Run `aice seed` first.")

    seed_tags = set(seed.get("tags", []))
    # Count any already-useful trusted evidence as coverage instead of paying for redundant duplicates.
    if any({"face", "front"}.issubset(set(r.get("tags", []))) for r in trusted):
        trusted_roles.add("face_front")
    if any({"full_body", "front"}.issubset(set(r.get("tags", []))) for r in trusted):
        trusted_roles.add("full_body_front")
    has_face_anchor = "face" in seed_tags or any("face" in set(r.get("tags", [])) for r in trusted)
    has_full_body_anchor = "full_body" in seed_tags or any("full_body" in set(r.get("tags", [])) and r.get("role") != "seed" for r in trusted)
    full_body_front_trusted = "full_body_front" in trusted_roles or any(
        r.get("tier") == "golden" and "full_body" in set(r.get("tags", [])) for r in trusted
    )

    tasks: list[dict[str, Any]] = []
    blocked: list[dict[str, str]] = []
    for spec in BOOTSTRAP_ROLES:
        if spec["role"] in trusted_roles:
            continue
        is_body = "full_body" in spec["tags"]
        if not is_body and not has_face_anchor:
            blocked.append({"role": spec["role"], "reason": "No trusted face evidence is available."})
            continue
        if is_body and not has_full_body_anchor:
            if spec["role"] != "full_body_front":
                blocked.append({
                    "role": spec["role"],
                    "reason": "Body geometry is not anchored yet. First create and explicitly approve full_body_front, or upload a trusted full-body reference.",
                })
                continue
            risk = "high-extrapolation"
            approval = True
        elif is_body and not full_body_front_trusted and spec["role"] != "full_body_front":
            blocked.append({
                "role": spec["role"],
                "reason": "A trusted full_body_front anchor is required before deriving side/back body references.",
            })
            continue
        else:
            risk = "derived"
            approval = False

        if is_body and full_body_front_trusted:
            anchor = next((r for r in trusted if r.get("role") == "full_body_front"), None)
            if anchor is None:
                anchor = next((r for r in trusted if "full_body" in set(r.get("tags", []))), seed)
        else:
            anchor = seed
        tasks.append({
            "role": spec["role"],
            "tags": spec["tags"],
            "anchor_path": str((char_dir / anchor["path"]).resolve()),
            "anchor_id": anchor["id"],
            "risk": risk,
            "requires_user_approval": approval,
            "prompt": (
                "Use the loaded trusted reference as the exact identity anchor. Create a clean reference photograph, not a glamour shot: "
                f"{spec['framing']}. Same adult synthetic person, preserve every grounded identity trait. "
                "Do not invent tattoos, marks, jewelry, facial traits, or body details that are not supported by the trusted reference set. "
                "Neutral relaxed posture/expression, simple fitted non-distracting clothing, plain softly lit background, realistic anatomy, no text, no watermark."
            ),
        })
    return {
        "character": profile["id"],
        "seed": str((char_dir / seed["path"]).resolve()),
        "seed_tags": sorted(seed_tags),
        "missing": tasks,
        "blocked": blocked,
        "rule": "High-extrapolation body anchors must be explicitly user-approved before they can seed further body-angle references.",
    }
