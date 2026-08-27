# Evidence-grounded character brain

Use only when synthesizing, resolving, or repairing character identity state.

## Fact namespaces

Prefer compact paths:
- `identity.age_range`
- `identity.face.shape`
- `identity.skin.tone`
- `identity.skin.undertone`
- `identity.hair.color`
- `identity.hair.hairline`
- `identity.eyes.color`
- `body.build`
- `body.proportions.shoulder_hip`
- `permanent.<feature_id>` for tattoo/birthmark/piercing/always-present jewelry

Mutable continuity (haircut, temporary nail color, current accessory, recent styling) belongs in `character.json` via `aice set-mutable`, not in immutable evidence facts.

## Observation rules

Visual observations must cite a golden/trusted reference ID. The brain resolver weights evidence by authority and counts each source once, so repeated analysis cannot manufacture consensus.

Use `aice observe <character> --json <payload>` with a compact list such as:

```json
[
  {"path":"identity.hair.color","value":"jet black","source_kind":"visual","source_ref":"..."},
  {"path":"identity.skin.tone","value":"fair","source_kind":"visual","source_ref":"..."}
]
```

If the user explicitly states a permanent fact, use `source_kind: user_asserted`. If the user settles a conflict or explicitly says a fact must never change, use `aice lock-fact`.

## Permanent features

Store as a structured value with visibility tags, for example:

```json
{
  "path": "permanent.left_wrist_tattoo",
  "value": {
    "kind": "tattoo",
    "location": "left_wrist",
    "description": "small minimalist crescent",
    "visibility_tags": ["hands", "arms"]
  },
  "source_kind": "visual",
  "source_ref": "..."
}
```

A permanent feature should not become resolved from an unclear crop. Prefer unknown over invented detail.

## Conflict behavior

If similarly authoritative references disagree, the resolver emits `conflict`. Do not pick one based on intuition. Ask the user only about those conflicted facts, then lock their choice.

## Generated reference lineage

Generated references always enter as `candidate` and must cite one or more golden/trusted parent IDs. They must pass `identity`, `anatomy`, and `stable_traits` checks before promotion. Generated references do not become golden without explicit user approval.
