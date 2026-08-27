from __future__ import annotations

from collections import defaultdict
from typing import Any

from .storage import load_brain, load_manifest, save_brain
from .utils import canonical_value, deep_set, utc_now

AUTHORITY = {
    "user_locked": 1000,
    "user_asserted": 160,
    "golden": 100,
    "trusted": 70,
}


def _source_authority(manifest: dict[str, Any], source_ref: str | None, source_kind: str) -> tuple[str, int]:
    if source_kind == "user_locked":
        return "user_locked", AUTHORITY["user_locked"]
    if source_kind == "user_asserted":
        return "user_asserted", AUTHORITY["user_asserted"]
    if not source_ref:
        raise ValueError("Visual observations require source_ref")
    record = next((r for r in manifest.get("references", []) if r.get("id") == source_ref), None)
    if record is None:
        raise KeyError(source_ref)
    tier = str(record.get("tier"))
    if tier not in {"golden", "trusted"}:
        raise ValueError("Brain observations may cite only golden/trusted references")
    return tier, AUTHORITY[tier]


def _resolve_fact(fact: dict[str, Any]) -> None:
    observations = fact.get("observations", [])
    locked = next((o for o in reversed(observations) if o.get("authority") == "user_locked"), None)
    if locked:
        fact.update({"status": "resolved", "value": locked["value"], "locked": True, "conflicts": []})
        return

    scores: dict[str, int] = defaultdict(int)
    values: dict[str, Any] = {}
    sources: dict[str, set[str]] = defaultdict(set)
    for obs in observations:
        key = canonical_value(obs.get("value"))
        values[key] = obs.get("value")
        source_key = str(obs.get("source_ref") or obs.get("source_kind"))
        if source_key in sources[key]:
            continue
        sources[key].add(source_key)
        scores[key] += int(obs.get("weight", 0))

    if not scores:
        fact.update({"status": "unknown", "value": None, "locked": False, "conflicts": []})
        return
    ranked = sorted(scores.items(), key=lambda item: (-item[1], item[0]))
    top_key, top_score = ranked[0]
    if len(ranked) == 1:
        fact.update({"status": "resolved", "value": values[top_key], "locked": False, "conflicts": []})
        return
    second_key, second_score = ranked[1]
    if top_score >= int(second_score * 1.35) + 1:
        fact.update({"status": "resolved", "value": values[top_key], "locked": False, "conflicts": []})
    else:
        fact.update({
            "status": "conflict",
            "value": None,
            "locked": False,
            "conflicts": [
                {"value": values[top_key], "score": top_score},
                {"value": values[second_key], "score": second_score},
            ],
        })


def add_observations(char_dir, observations: list[dict[str, Any]]) -> dict[str, Any]:
    if not observations:
        raise ValueError("At least one observation is required")
    brain = load_brain(char_dir)
    manifest = load_manifest(char_dir)
    facts = brain.setdefault("facts", {})
    touched: set[str] = set()
    for incoming in observations:
        path = str(incoming.get("path", "")).strip()
        if not path or path.startswith("mutable."):
            raise ValueError("Observation path is missing or reserved; mutable state belongs in character.json")
        if "value" not in incoming:
            raise ValueError(f"Observation for {path!r} is missing value")
        source_kind = str(incoming.get("source_kind", "visual"))
        source_ref = incoming.get("source_ref")
        authority, weight = _source_authority(manifest, source_ref, source_kind)
        fact = facts.setdefault(path, {"status": "unknown", "value": None, "locked": False, "observations": []})
        obs = {
            "value": incoming["value"],
            "source_kind": source_kind,
            "source_ref": source_ref,
            "authority": authority,
            "weight": weight,
            "observed_at": utc_now(),
        }
        sig = (canonical_value(obs["value"]), str(source_ref), source_kind)
        existing = {
            (canonical_value(x.get("value")), str(x.get("source_ref")), str(x.get("source_kind")))
            for x in fact.get("observations", [])
        }
        if sig not in existing:
            fact.setdefault("observations", []).append(obs)
        touched.add(path)
    for path in touched:
        _resolve_fact(facts[path])
    save_brain(char_dir, brain)
    return brain_summary(brain)


def lock_fact(char_dir, path: str, value: Any) -> dict[str, Any]:
    return add_observations(char_dir, [{"path": path, "value": value, "source_kind": "user_locked", "source_ref": None}])


def brain_summary(brain: dict[str, Any]) -> dict[str, Any]:
    resolved: dict[str, Any] = {}
    conflicts: dict[str, Any] = {}
    evidence: dict[str, Any] = {}
    for path, fact in sorted(brain.get("facts", {}).items()):
        status = fact.get("status", "unknown")
        if status == "resolved":
            deep_set(resolved, path, fact.get("value"))
        elif status == "conflict":
            conflicts[path] = fact.get("conflicts", [])
        evidence[path] = {
            "status": status,
            "locked": bool(fact.get("locked")),
            "sources": sorted({str(o.get("source_ref") or o.get("source_kind")) for o in fact.get("observations", [])}),
        }
    return {"resolved": resolved, "conflicts": conflicts, "evidence": evidence}


def resolved_truth(brain: dict[str, Any]) -> dict[str, Any]:
    return brain_summary(brain)["resolved"]


def visible_permanent_features(brain: dict[str, Any], prompt: str, inferred_tags: set[str]) -> list[dict[str, Any]]:
    text = prompt.casefold()
    permanent = resolved_truth(brain).get("permanent", {})
    if not isinstance(permanent, dict):
        return []
    visible: list[dict[str, Any]] = []
    for feature_id, value in permanent.items():
        if not isinstance(value, dict):
            continue
        visibility = {str(x).casefold() for x in value.get("visibility_tags", [])}
        location = str(value.get("location", "")).replace("_", " ").casefold()
        explicit = bool(location and location in text)
        if explicit or visibility.intersection(inferred_tags):
            visible.append({"id": feature_id, **value})
    return visible
