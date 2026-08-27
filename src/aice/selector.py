from __future__ import annotations

import re
from collections import Counter
from typing import Any

BUDGETS = {
    "economy": {"max_refs": 2, "history": 4, "context_chars": 1600, "validation": "critical", "repairs": 0},
    "balanced": {"max_refs": 3, "history": 8, "context_chars": 2600, "validation": "light", "repairs": 1},
    "quality": {"max_refs": 4, "history": 12, "context_chars": 4200, "validation": "full", "repairs": 1},
}

KEYWORDS: dict[str, tuple[str, ...]] = {
    "face": ("face", "portrait", "headshot", "yüz", "portre", "selfie", "profile picture", "pp"),
    "upper_body": ("upper body", "waist up", "chest up", "belden", "selfie", "portrait"),
    "full_body": ("full body", "boydan", "head to toe", "outfit", "standing", "yürürken", "walking"),
    "front": ("front", "önden", "straight on", "selfie", "camera"),
    "back": ("back", "rear", "arkadan", "from behind", "behind"),
    "side": ("side", "profile", "yan", "yandan", "3/4", "three quarter"),
    "seated": ("seated", "sitting", "otur", "chair", "şezlong", "lounger"),
    "hands": ("hand", "hands", "wrist", "bilek", "bracelet", "bileklik", "drink", "glass", "phone", "selfie"),
    "arms": ("arm", "arms", "kol", "sleeveless", "short sleeve"),
    "legs": ("leg", "legs", "bacak", "walking", "full body", "boydan", "lounger"),
}


def infer_tags(prompt: str) -> set[str]:
    text = prompt.casefold()
    tags: set[str] = set()
    for tag, phrases in KEYWORDS.items():
        if any(phrase in text for phrase in phrases):
            tags.add(tag)
    if not tags:
        tags.update({"face", "upper_body"})
    return tags


def visible_permanent_features(profile: dict[str, Any], prompt: str, inferred_tags: set[str]) -> list[dict[str, str]]:
    text = prompt.casefold()
    visible: list[dict[str, str]] = []
    for feature in profile.get("permanent_features", []):
        visibility = {str(x).casefold() for x in feature.get("visibility_tags", [])}
        location = str(feature.get("location", "")).replace("_", " ").casefold()
        explicit = bool(location and location in text)
        if explicit or visibility.intersection(inferred_tags):
            visible.append({
                "id": str(feature.get("id", "detail")),
                "kind": str(feature.get("kind", "feature")),
                "location": str(feature.get("location", "")),
                "description": str(feature.get("description", "")),
            })
    return visible


def select_references(manifest: dict[str, Any], prompt: str, budget: str = "balanced") -> list[dict[str, Any]]:
    if budget not in BUDGETS:
        raise ValueError(f"Unknown budget: {budget}")
    wanted = infer_tags(prompt)
    rear_only = "back" in wanted and "front" not in wanted and "face" not in wanted
    eligible = [r for r in manifest.get("references", []) if r.get("tier") in {"golden", "trusted"}]

    def score(record: dict[str, Any]) -> float:
        tags = set(record.get("tags", []))
        role = str(record.get("role", ""))
        tier_bonus = 50 if record.get("tier") == "golden" else 30
        overlap = len(tags.intersection(wanted)) * 12
        role_bonus = sum(8 for tag in wanted if tag in role)
        seed_bonus = 8 if role == "seed" else 0
        face_penalty = -30 if rear_only and ("face" in tags or "front" in tags) else 0
        return tier_bonus + float(record.get("trust", 0)) * 20 + overlap + role_bonus + seed_bonus + face_penalty

    ranked = sorted(eligible, key=lambda r: (-score(r), r.get("id", "")))
    limit = BUDGETS[budget]["max_refs"]
    chosen: list[dict[str, Any]] = []
    used_roles: Counter[str] = Counter()
    for record in ranked:
        role = str(record.get("role", ""))
        if used_roles[role] >= 1 and len(ranked) > limit:
            continue
        chosen.append(record)
        used_roles[role] += 1
        if len(chosen) >= limit:
            break

    if not rear_only and chosen and not any("face" in set(r.get("tags", [])) or r.get("role") == "seed" for r in chosen):
        face = next((r for r in ranked if "face" in set(r.get("tags", [])) or r.get("role") == "seed"), None)
        if face:
            chosen[-1] = face
    return chosen


def recent_avoidance(history: list[dict[str, Any]], window: int) -> list[str]:
    rows = [row for row in history if row.get("status") in {"approved", "draft"}][-window:]
    if len(rows) < 2:
        return []
    fields = ("shot", "angle", "gaze", "pose", "environment", "lighting", "outfit")
    notes: list[str] = []
    for field in fields:
        values = [str(row.get("fingerprint", {}).get(field, "")).strip() for row in rows]
        values = [v for v in values if v]
        if not values:
            continue
        value, count = Counter(values).most_common(1)[0]
        if count >= max(2, len(rows) // 2):
            notes.append(f"avoid repeating {field}={value}")
    return notes[:4]


def tokenize_words(text: str) -> set[str]:
    return set(re.findall(r"[\w-]+", text.casefold(), flags=re.UNICODE))
