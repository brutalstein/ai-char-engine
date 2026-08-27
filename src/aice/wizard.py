from __future__ import annotations

from typing import Any

from .brain import brain_summary
from .engine import bootstrap_plan
from .storage import list_characters, load_brain, load_manifest, load_onboarding, load_profile


def guide(home, character: str | None = None) -> dict[str, Any]:
    characters = list_characters(home)
    if not characters:
        return {
            "stage": "choose_origin",
            "user_message": "Would you like to create a brand-new character from scratch, or build one from reference photos you already have?",
            "choices": ["Create from scratch", "Use my reference photos"],
            "internal_hint": "After the user chooses, create the character with `aice begin <name> --origin scratch|references`.",
        }
    if character is None:
        if len(characters) == 1:
            character = characters[0]["id"]
        else:
            return {
                "stage": "select_character",
                "user_message": "Which character would you like to work with?",
                "choices": [row["display_name"] for row in characters],
                "characters": characters,
            }

    char_dir, profile = load_profile(home, character)
    state = load_onboarding(char_dir)
    manifest = load_manifest(char_dir)
    refs = manifest.get("references", [])
    golden = [r for r in refs if r.get("tier") == "golden"]
    candidates = [r for r in refs if r.get("tier") == "candidate"]
    brain = brain_summary(load_brain(char_dir))

    if state.get("origin") == "scratch" and not golden:
        if candidates:
            seed_candidate = candidates[0]
            return {
                "stage": "approve_seed",
                "character": profile["id"],
                "user_message": "I created the first identity image. Does this look like the character you want to keep? I can accept it or regenerate it.",
                "choices": ["Use this character", "Regenerate"],
                "candidate_ref": seed_candidate["id"],
            }
        return {
            "stage": "describe_seed",
            "character": profile["id"],
            "user_message": "Describe the character you want in your own words. You can be brief or very specific; I will handle the technical image prompt.",
            "choices": [],
        }

    if state.get("origin") == "references" and not state.get("references_closed"):
        return {
            "stage": "collect_references",
            "character": profile["id"],
            "user_message": (
                f"Upload as many reference photos as you want for {profile['display_name']}. "
                "Different angles, full-body photos, close portraits, and clear detail shots all help. "
                "When you are finished, just say 'done'."
            ),
            "choices": ["I will upload more", "Done"],
            "accepted_count": len(golden),
        }

    if not golden:
        return {
            "stage": "need_reference",
            "character": profile["id"],
            "user_message": "I still need at least one approved identity reference before I can build the character brain.",
            "choices": ["Upload a reference", "Create one for me"],
        }

    if not brain["resolved"] and not brain["conflicts"]:
        return {
            "stage": "build_brain",
            "character": profile["id"],
            "user_message": "I have the references. I’ll analyze them now and build the persistent character brain from only visually supported details.",
            "choices": [],
            "golden_refs": [r["id"] for r in golden],
        }

    if brain["conflicts"]:
        return {
            "stage": "resolve_conflicts",
            "character": profile["id"],
            "user_message": "A few permanent details conflict across your references. I’ll show only the ambiguous items so you can choose the correct version.",
            "choices": [],
            "conflicts": brain["conflicts"],
        }

    if state.get("ready"):
        return {
            "stage": "ready",
            "character": profile["id"],
            "user_message": "Character is ready. Tell me the photo you want in ordinary language.",
            "choices": [],
        }

    try:
        plan = bootstrap_plan(home, character)
    except ValueError:
        plan = {"missing": [], "blocked": []}
    high_risk = [x for x in plan.get("missing", []) if x.get("requires_user_approval")]
    if high_risk:
        return {
            "stage": "optional_body_anchor",
            "character": profile["id"],
            "user_message": (
                "Your current photos do not firmly establish full-body geometry. I can create one proposed full-body reference for you to approve, "
                "or we can skip that and start generating only scenes covered by the current references."
            ),
            "choices": ["Create the full-body reference", "Skip for now"],
            "tasks": high_risk,
        }

    return {
        "stage": "ready_to_finish",
        "character": profile["id"],
        "user_message": "The character brain is ready. I can now generate new photos from simple natural-language requests while preserving identity.",
        "choices": ["Start generating"],
    }
