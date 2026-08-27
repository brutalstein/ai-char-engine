from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .brain import resolved_truth, visible_permanent_features
from .selector import BUDGETS, infer_tags, recent_avoidance, select_references
from .storage import history_path, load_brain, load_manifest, load_profile
from .utils import compact_json, tail_jsonl

BOOTSTRAP_ROLES: list[dict[str, Any]] = [
    {"role": "face_front", "tags": ["face", "front", "upper_body"], "framing": "neutral head-and-shoulders front view"},
    {"role": "face_3q_left", "tags": ["face", "side", "upper_body"], "framing": "neutral left three-quarter head-and-shoulders view"},
    {"role": "face_3q_right", "tags": ["face", "side", "upper_body"], "framing": "neutral right three-quarter head-and-shoulders view"},
    {"role": "full_body_front", "tags": ["full_body", "front", "legs", "arms"], "framing": "neutral full-body front view, head to toe"},
    {"role": "full_body_side", "tags": ["full_body", "side", "legs", "arms"], "framing": "neutral full-body side view, head to toe"},
    {"role": "full_body_back", "tags": ["full_body", "back", "legs", "arms"], "framing": "neutral full-body rear view, head to toe"},
]


def compact_identity(brain: dict[str, Any], profile: dict[str, Any]) -> dict[str, Any]:
    truth = resolved_truth(brain)
    summary: dict[str, Any] = {}
    for key in ("identity", "body"):
        value = truth.get(key)
        if value:
            summary[key] = value
    mutable = profile.get("mutable_state")
    if mutable:
        summary["current"] = mutable
    return summary


def coverage_gaps(manifest: dict[str, Any], prompt: str) -> list[str]:
    wanted = infer_tags(prompt)
    trusted = [r for r in manifest.get("references", []) if r.get("tier") in {"golden", "trusted"}]
    available: set[str] = set()
    for ref in trusted:
        available.update(str(x) for x in ref.get("tags", []))
    return [tag for tag in ("face", "full_body", "side", "back") if tag in wanted and tag not in available]


def build_context(home: Path, character: str, prompt: str, budget: str = "balanced") -> dict[str, Any]:
    if budget not in BUDGETS:
        raise ValueError(f"Unknown budget: {budget}")
    char_dir, profile = load_profile(home, character)
    brain = load_brain(char_dir)
    manifest = load_manifest(char_dir)
    refs = select_references(manifest, prompt, budget)
    if not refs:
        raise ValueError("No golden/trusted identity references are available. Finish onboarding or add trusted references first.")
    tags = infer_tags(prompt)
    history = tail_jsonl(history_path(char_dir), BUDGETS[budget]["history"] * 3)
    avoidance = recent_avoidance(history, BUDGETS[budget]["history"])
    details = visible_permanent_features(brain, prompt, tags)
    payload: dict[str, Any] = {
        "character": profile["id"],
        "budget": budget,
        "request": prompt,
        "identity": compact_identity(brain, profile),
        "hard_rules": profile.get("hard_rules", [])[:4],
        "visible_permanent_details": details[:4],
        "references": [
            {
                "id": ref["id"],
                "path": str((char_dir / ref["path"]).resolve()),
                "role": ref["role"],
                "tier": ref["tier"],
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
    result["visible_permanent_details"] = result.get("visible_permanent_details", [])[:2]
    if len(compact_json(result)) <= max_chars:
        return result
    identity = result.get("identity", {})
    if isinstance(identity, dict):
        for key in list(identity):
            value = identity[key]
            if isinstance(value, dict) and len(value) > 5:
                identity[key] = dict(list(value.items())[:5])
    if len(compact_json(result)) <= max_chars:
        return result
    raise ValueError(f"Compiled context exceeds {max_chars} chars; reduce low-value character metadata.")


def render_generation_prompt(context: dict[str, Any]) -> str:
    refs = "; ".join(f"Image {i + 1}={r['role']}" for i, r in enumerate(context.get("references", [])))
    details = "; ".join(
        f"{d.get('kind', 'feature')} at {d.get('location', '')}: {d.get('description', '')}"
        for d in context.get("visible_permanent_details", [])
    )
    avoidance = "; ".join(context.get("avoid_recent", []))
    parts = [
        "Use case: photorealistic-natural",
        "Asset type: personal virtual-creator photograph",
        f"Primary request: {context['request']}",
        "Identity contract: the loaded references depict the exact same adult synthetic character. Preserve recognizable facial identity and all grounded stable traits.",
    ]
    if context.get("identity"):
        parts.append(f"Compact grounded traits: {compact_json(context['identity'])}")
    if refs:
        parts.append(f"Input images: {refs}; identity references, not edit targets.")
    if details:
        parts.append(f"Visible permanent details: {details}")
    if avoidance:
        parts.append(f"Controlled diversity: {avoidance}; vary naturally without changing identity.")
    parts.extend([
        "Style/medium: ultra-realistic natural photography; believable skin texture, anatomy, optics, lighting, and casual human imperfection.",
        "Composition/framing: honor the requested camera relationship; do not default to the same gaze, pose, or framing unless requested.",
        "Constraints: adult synthetic character, realistic anatomy, no identity redesign, no unsupported permanent details, no text or watermark unless requested.",
    ])
    return "\n".join(parts)


def bootstrap_plan(home: Path, character: str) -> dict[str, Any]:
    char_dir, profile = load_profile(home, character)
    manifest = load_manifest(char_dir)
    trusted = [r for r in manifest.get("references", []) if r.get("tier") in {"golden", "trusted"}]
    if not trusted:
        raise ValueError("At least one golden/trusted reference is required before expansion")
    trusted_roles = {r["role"] for r in trusted}
    face_anchor = next((r for r in trusted if "face" in set(r.get("tags", []))), None)
    full_anchor = next((r for r in trusted if "full_body" in set(r.get("tags", [])) and "front" in set(r.get("tags", []))), None)
    fallback = next((r for r in trusted if r.get("tier") == "golden"), trusted[0])
    tasks: list[dict[str, Any]] = []
    blocked: list[dict[str, str]] = []
    for spec in BOOTSTRAP_ROLES:
        if spec["role"] in trusted_roles:
            continue
        tags = set(spec["tags"])
        is_body = "full_body" in tags
        if not is_body and face_anchor is None:
            blocked.append({"role": spec["role"], "reason": "No trusted face anchor exists."})
            continue
        if is_body and full_anchor is None and spec["role"] != "full_body_front":
            blocked.append({"role": spec["role"], "reason": "Approve a full-body front anchor before deriving side/back body references."})
            continue
        if spec["role"] == "full_body_front" and full_anchor is None:
            anchor = face_anchor or fallback
            risk = "high-extrapolation"
            approval = True
        elif is_body:
            anchor = full_anchor
            risk = "derived"
            approval = False
        else:
            anchor = face_anchor or fallback
            risk = "derived"
            approval = False
        tasks.append({
            "role": spec["role"],
            "tags": spec["tags"],
            "anchor_path": str((char_dir / anchor["path"]).resolve()),
            "anchor_id": anchor["id"],
            "risk": risk,
            "requires_user_approval": approval,
            "prompt": (
                "Create a clean identity-reference photograph from the loaded trusted anchor: "
                f"{spec['framing']}. Same adult synthetic person. Preserve all grounded identity traits. "
                "Do not invent tattoos, marks, jewelry, facial traits, or body geometry unsupported by trusted evidence. "
                "Neutral relaxed posture/expression, simple non-distracting clothing, plain soft background, realistic anatomy, no text, no watermark."
            ),
        })
    return {
        "character": profile["id"],
        "missing": tasks,
        "blocked": blocked,
        "rule": "High-extrapolation anchors require explicit user approval before becoming identity truth.",
    }
