"""Compact, deterministic explicit-intent classification.

This is intentionally *not* an NLP subsystem. It is a small keyword/phrase matcher
that sorts an image request into four buckets so the provider planner can route it:

- ``normal``      -> ordinary photoreal request; normal routing applies.
- ``suggestive``  -> sensual but not explicit; normal routing applies.
- ``explicit``    -> explicit adult synthetic content; must use the local ComfyUI
                     adult profile (LUSTIFY), never built-in cloud image generation.
- ``disallowed``  -> sexual content the project must refuse (minors, incest,
                     non-consent, sexual violence, real-person sexual deepfakes,
                     hidden-camera/voyeur, or otherwise illegal).

The whole engine is already restricted to adult synthetic/authorized characters
(``storage.save_profile``), so "adult" is the baseline. This layer only decides
*explicitness* and *hard refusal*.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

NORMAL = "normal"
SUGGESTIVE = "suggestive"
EXPLICIT = "explicit"
DISALLOWED = "disallowed"

LEVELS = (NORMAL, SUGGESTIVE, EXPLICIT, DISALLOWED)


@dataclass(frozen=True)
class IntentVerdict:
    level: str
    matched: tuple[str, ...]
    wants_local_adult: bool
    reason: str

    @property
    def is_explicit(self) -> bool:
        return self.level == EXPLICIT

    @property
    def is_disallowed(self) -> bool:
        return self.level == DISALLOWED

    def as_dict(self) -> dict[str, object]:
        return {
            "level": self.level,
            "matched": list(self.matched),
            "wants_local_adult": self.wants_local_adult,
            "reason": self.reason,
        }


# --- vocabularies (data, not logic) -----------------------------------------

# Hard refusals. Matched as whole words / phrases, case-insensitive.
_MINORS = (
    "child", "children", "childlike", "kid", "kids", "toddler", "infant", "baby",
    "minor", "underage", "under-age", "under age", "preteen", "pre-teen",
    "prepubescent", "pubescent", "loli", "lolicon", "shota", "shotacon",
    "jailbait", "schoolgirl", "schoolboy", "school girl", "school boy",
    "grade schooler", "elementary school", "middle school", "little girl",
    "little boy", "young girl", "young boy", "underaged",
)
_INCEST = ("incest", "incestuous")
_FAMILY = (
    "sister", "brother", "mother", "father", "mom", "mommy", "dad", "daddy",
    "daughter", "son", "aunt", "uncle", "niece", "nephew", "cousin", "sibling",
    "stepsister", "step-sister", "step sister", "stepbrother", "step brother",
    "stepmom", "step mom", "stepmother", "stepdad", "step dad", "stepfather",
    "stepdaughter", "step daughter", "stepson", "step son",
)
_NONCONSENT = (
    "rape", "raping", "raped", "noncon", "non-con", "non con", "nonconsensual",
    "non-consensual", "non consensual", "without consent", "against her will",
    "against his will", "against their will", "forced sex", "force her",
    "molest", "molestation", "drugged", "roofied", "date rape",
    "unconscious", "passed out", "while she sleeps", "while he sleeps",
    "coerced", "coercion",
)
_SEXUAL_VIOLENCE = (
    "sexual assault", "sexual violence", "snuff", "gore porn", "torture porn",
    "beaten and", "abuse porn",
)
_DEEPFAKE = (
    "deepfake", "deep fake", "deep-fake", "face swap", "face-swap", "faceswap",
    "nudify", "undress photo", "undress this", "real person", "celebrity nude",
    "actress nude", "actor nude",
)
_VOYEUR = (
    "hidden camera", "hidden cam", "spycam", "spy cam", "voyeur", "voyeuristic",
    "peeping", "peeping tom", "upskirt", "creepshot", "creep shot",
    "secretly filmed", "secretly recorded", "changing room", "locker room",
    "public restroom", "bathroom spy",
)
_AGE_RE = re.compile(
    r"\b(?:[0-9]|1[0-7])\s*(?:years?[\s-]*old|y(?:[\s-]*o)?[\s-]*(?:girl|boy|female|male)?)\b"
)

# Explicit adult synthetic content.
_EXPLICIT = (
    "nsfw", "18+", "+18", "explicit", "explicit photo", "explicit content",
    "explicit image", "sexually explicit", "nude", "nudes", "nudity", "naked",
    "topless", "bottomless", "full frontal", "fully nude", "buck naked",
    "sex", "sexual", "having sex", "sex scene", "intercourse", "penetration",
    "penetrated", "blowjob", "blow job", "oral sex", "handjob", "hand job",
    "cumshot", "cum shot", "creampie", "cum on", "facial cumshot",
    "doggystyle", "doggy style", "cowgirl position", "reverse cowgirl",
    "masturbate", "masturbating", "masturbation", "orgasm", "squirting",
    "porn", "porno", "pornographic", "hardcore", "xxx", "erotica nude",
    "nipple", "nipples", "areola", "areolae", "genitals", "genitalia",
    "vagina", "vulva", "pussy", "penis", "dick pic", "erect penis", "erection",
    "spread legs", "spread eagle", "bdsm", "bondage sex", "hentai",
    "adult version", "make it explicit", "make it nsfw", "make it 18+",
    "make it +18", "nsfw version", "more explicit", "uncensored nude",
    "uncensored version", "sex tape",
)

# Suggestive but not explicit.
_SUGGESTIVE = (
    "lingerie", "underwear", "bra and panties", "panties", "thong", "negligee",
    "bikini", "swimsuit", "one-piece swimsuit", "micro bikini", "cleavage",
    "sensual", "seductive", "suggestive", "provocative", "see-through",
    "see through", "sheer top", "sheer dress", "wet t-shirt", "boudoir",
    "implied nude", "covered nude", "pin-up", "pinup", "sexy pose", "risque",
    "revealing outfit", "skimpy",
)

# Signals that the user specifically wants the local adult backend for this request.
_WANTS_LOCAL_ADULT = (
    "local adult model", "local adult backend", "local adult engine",
    "use the local adult", "use local adult", "use lustify", "lustify",
    "local nsfw", "local nsfw model", "don't use the built-in",
    "do not use the built-in", "not the built-in", "not the built in",
    "no built-in generator", "not built-in generation", "use comfyui for this",
    "use the local model for this", "local model for this one",
)


def _norm(text: str) -> str:
    return " " + " ".join(str(text or "").casefold().split()) + " "


def _hits(haystack: str, needles: tuple[str, ...]) -> list[str]:
    out: list[str] = []
    for term in needles:
        pattern = term.casefold()
        if " " in pattern or "-" in pattern or "+" in pattern:
            if pattern in haystack:
                out.append(term)
        elif re.search(r"(?<![a-z])" + re.escape(pattern) + r"(?![a-z])", haystack):
            out.append(term)
    return out


def classify_explicitness(text: str) -> IntentVerdict:
    """Deterministically bucket a natural-language image request."""
    t = _norm(text)

    explicit_hits = _hits(t, _EXPLICIT)
    age_hit = bool(_AGE_RE.search(t))

    disallowed: list[str] = []
    disallowed += _hits(t, _MINORS)
    if age_hit:
        disallowed.append("under-18 age reference")
    disallowed += _hits(t, _INCEST)
    disallowed += _hits(t, _NONCONSENT)
    disallowed += _hits(t, _SEXUAL_VIOLENCE)
    disallowed += _hits(t, _DEEPFAKE)
    disallowed += _hits(t, _VOYEUR)
    # Family role + explicit sexual context -> incest-adjacent, refuse.
    family_hits = _hits(t, _FAMILY)
    if family_hits and explicit_hits:
        disallowed += [f"family term '{h}' with explicit context" for h in family_hits]

    wants_local = bool(_hits(t, _WANTS_LOCAL_ADULT))

    if disallowed:
        return IntentVerdict(
            DISALLOWED,
            tuple(dict.fromkeys(disallowed)),
            wants_local,
            "request matches a category the project does not generate",
        )

    if explicit_hits:
        return IntentVerdict(
            EXPLICIT, tuple(dict.fromkeys(explicit_hits)), wants_local,
            "explicit adult synthetic content requested",
        )

    suggestive_hits = _hits(t, _SUGGESTIVE)
    if suggestive_hits:
        return IntentVerdict(
            SUGGESTIVE, tuple(dict.fromkeys(suggestive_hits)), wants_local,
            "suggestive but not explicit",
        )

    return IntentVerdict(NORMAL, (), wants_local, "no explicit-adult signal")


def demo() -> None:
    assert classify_explicitness("old-town cafe, rainy afternoon, candid photo").level == NORMAL
    assert classify_explicitness("her in a bikini on the beach").level == SUGGESTIVE
    assert classify_explicitness("make it an explicit nude photo").level == EXPLICIT
    assert classify_explicitness("+18 version of the last shot").level == EXPLICIT
    assert classify_explicitness("use the local adult model, no built-in generator").wants_local_adult
    assert classify_explicitness("explicit photo of a schoolgirl").level == DISALLOWED
    assert classify_explicitness("nude 15 yo girl").level == DISALLOWED
    assert classify_explicitness("explicit scene with her step sister").level == DISALLOWED
    assert classify_explicitness("hidden camera nude in a locker room").level == DISALLOWED
    assert classify_explicitness("deepfake nude of a real person").level == DISALLOWED
    assert classify_explicitness("a young adult woman, 25, business portrait").level == NORMAL
    print("intent.demo ok")


if __name__ == "__main__":
    demo()
