from __future__ import annotations

import re
from collections import Counter
from typing import Any

BUDGETS = {
    "economy": {"max_refs": 2, "history": 4, "context_chars": 1700, "validation": "critical", "repairs": 0},
    "balanced": {"max_refs": 3, "history": 8, "context_chars": 2800, "validation": "light", "repairs": 1},
    "quality": {"max_refs": 4, "history": 12, "context_chars": 4400, "validation": "full", "repairs": 1},
}

KEYWORDS: dict[str, tuple[str, ...]] = {
    "face": ("face", "portrait", "headshot", "yüz", "portre", "selfie", "profile picture", "pp"),
    "upper_body": ("upper body", "waist up", "chest up", "belden", "selfie", "portrait"),
    "full_body": ("full body", "boydan", "head to toe", "outfit", "standing", "yürürken", "walking"),
    "front": ("front view", "önden", "straight on", "selfie", "facing camera"),
    "back": ("rear view", "arkadan", "from behind", "back view"),
    "side": ("side view", "side profile", "yan profil", "yandan", "3/4", "three quarter", "three-quarter"),
    "seated": ("seated", "sitting", "otur", "chair", "şezlong", "lounger"),
    "hands": ("hand", "hands", "wrist", "bilek", "bracelet", "bileklik", "drink", "glass", "phone", "selfie"),
    "arms": ("arm", "arms", "kol", "sleeveless", "short sleeve"),
    "legs": ("leg", "legs", "bacak", "walking", "full body", "boydan", "lounger"),
}


def infer_tags(prompt: str) -> set[str]:
    text = " ".join(prompt.casefold().split())
    tags: set[str] = set()
    for tag, phrases in KEYWORDS.items():
        if any(phrase in text for phrase in phrases):
            tags.add(tag)
    if "profile picture" in text or re.search(r"\binstagram\s+pp\b", text):
        tags.discard("side")
        tags.update({"face", "upper_body"})
    if not tags:
        tags.update({"face", "upper_body"})
    return tags


def select_references(manifest: dict[str, Any], prompt: str, budget: str = "balanced") -> list[dict[str, Any]]:
    if budget not in BUDGETS:
        raise ValueError(f"Unknown budget: {budget}")
    wanted = infer_tags(prompt)
    rear_only = "back" in wanted and "front" not in wanted and "face" not in wanted
    eligible = [r for r in manifest.get("references", []) if r.get("tier") in {"golden", "trusted"}]

    def score(record: dict[str, Any]) -> float:
        tags = set(record.get("tags", []))
        role = str(record.get("role", ""))
        tier_bonus = 60 if record.get("tier") == "golden" else 35
        overlap = len(tags.intersection(wanted)) * 14
        role_bonus = sum(8 for tag in wanted if tag in role)
        seed_bonus = 6 if role == "seed" else 0
        geometry_penalty = -40 if rear_only and ("front" in tags or role in {"seed", "face_front"}) else 0
        return tier_bonus + float(record.get("trust", 0)) * 20 + overlap + role_bonus + seed_bonus + geometry_penalty

    ranked = sorted(eligible, key=lambda r: (-score(r), str(r.get("id", ""))))
    limit = BUDGETS[budget]["max_refs"]
    chosen: list[dict[str, Any]] = []
    used_roles: Counter[str] = Counter()
    for record in ranked:
        role = str(record.get("role", ""))
        if used_roles[role] and len(ranked) > limit:
            continue
        chosen.append(record)
        used_roles[role] += 1
        if len(chosen) >= limit:
            break

    if not rear_only and chosen and not any("face" in set(r.get("tags", [])) or r.get("role") in {"seed", "face_front"} for r in chosen):
        face = next((r for r in ranked if "face" in set(r.get("tags", [])) or r.get("role") in {"seed", "face_front"}), None)
        if face:
            chosen[-1] = face
    return chosen


def recent_avoidance(history: list[dict[str, Any]], window: int) -> list[str]:
    rows = [row for row in history if row.get("status") == "approved"][-window:]
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
        if count >= max(2, (len(rows) + 1) // 2):
            notes.append(f"avoid repeating {field}={value}")
    return notes[:4]
