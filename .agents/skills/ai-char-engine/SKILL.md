---
name: ai-char-engine
description: Conversational persistent-character image workflow for Codex. Use when creating/resuming a synthetic adult visual character, ingesting references, preserving identity, coordinating local ComfyUI with Codex image generation, or installing/updating AI Character Engine.
---

# AI Character Engine

Act like a polished creative product, never a CLI tutorial. The user speaks naturally; AICE owns identity/state/trust/planning and image providers stay invisible workers.

## Product contract

- Ask only the next useful question; never re-ask known facts.
- Run internal `aice` commands yourself. Do not expose commands, paths, nodes, JSON or raw traces unless debugging is requested.
- `aice guide [character]` is authoritative for conversational stage.
- Character Brain and trusted references are provider-neutral. Provider origin is provenance, never trust.
- User-approved evidence outranks generated evidence. Generated derivatives enter as candidate; only golden/trusted refs may condition normal generation.
- Never let a provider trust/promote its own output or create recursive candidate lineage.
- Keep `.aice/` and `~/.aice/runtime` private/local; never commit characters, images, models or runtime state.
- Adult synthetic/original/authorized characters only.
- Default to one primary generation and at most one justified repair/reference-expansion call.

## Install / update

If `aice` is unavailable, install/update per `AGENTS.md`, then run doctor and guide. Natural requests containing update/refresh/güncel/latest authorize the latest-refresh path automatically; preserve the user's worktree and verify version/tests before claiming success.

Local ComfyUI is optional. A capability is usable only when its own models/runtime are present **and its own smoke validation passed**. Identity, bootstrap and adult-explicit validation are independent.

## Onboarding

Follow `aice guide`.

### `choose_origin`
Ask scratch vs existing references; ask a name only if absent.

### `describe_seed`
Ask for one natural appearance description. Run `aice seed-generate` internally. Built-in generation can plan a neutral no-reference seed; validated local bootstrap may also create one. If both are viable and preference is unsettled, ask one short backend question.

If seed result is built-in `planned`, call built-in image generation from the returned contract. If ComfyUI returns `ok`, show the output. Neither becomes identity truth before approval.

If seed status is `adult_identity_required`, do **not** retry the explicit request through another provider. Explain briefly that the local adult workflow needs a trusted identity first, create/approve a non-explicit adult identity seed, then retry the original explicit request locally.

### `approve_seed`
Show the seed. If accepted, validate obvious anatomy and use the approved-seed path with the actual origin provider. User approval makes the seed golden. If rejected, ask for the smallest correction and replace it.

### `collect_references`
Accept unlimited batches until the user says done. User-uploaded refs are golden/user-origin. Inspect visible evidence only and cache by SHA.

### `build_brain` / `resolve_conflicts`
Read `references/brain.md`. Build truth only from golden/trusted evidence and explicit user assertions. Surface ambiguous permanent facts and lock the user's answer; never guess invisible traits.

### `optional_body_anchor`
Offer one proposed anchor or skip. Generated anchors remain candidate until accepted/quality-gated. Side/back derivations still need a trusted body anchor.

### `choose_backend`
Map natural replies:
- local / ComfyUI / my GPU -> `comfyui`
- Codex / image_gen / built-in -> `codex_builtin`
- you choose / automatic / best available -> `auto`
- ask every time -> `ask_each_time`

Persist only clearly future/default choices. Current-request provider wording is a one-shot override. “Use both if useful” maps to one-shot `hybrid`; it does not mean double-generation.

### `backend_attention`
Saved local preference is unavailable. Offer setup/repair or ask permission to use built-in for this non-explicit request. Never silently leave an explicit/saved local choice.

### `ready`
Invite an ordinary-language image request. Do not ask backend questions when intent/readiness already settles the route.

## Backend order

1. explicit current-request strategy/provider intent;
2. saved character preference;
3. deterministic capability/guide state.

Explicit `comfyui` never silently falls back. Explicit `codex_builtin` never starts ComfyUI. `auto`/one-shot `hybrid` may use a bounded alternate provider only when the returned plan permits it.

## Explicit adult content

`aice generate` classifies explicitness itself; route on its result. Explicit adult synthetic requests use only the **validated local** LUSTIFY ComfyUI capability—never built-in generation and no silent downgrade.

- `local_adult_unavailable`: offer local setup/repair or a non-explicit alternative, then stop.
- `adult_identity_required`: establish/approve a neutral identity seed first, then retry locally.
- `refused`: relay the refusal; never retry/reword around it.

Read `references/adult.md` only for this path or local adult setup.

## Normal generation

1. Refresh `aice guide <character>` if state may have changed.
2. Run provider-neutral `aice generate <character> "<request>" --budget balanced --progress` internally.
3. Add a one-shot backend override only when the current request overrides saved preference.
4. Read factual `trace` and `plan`; never invent percentages/ETAs.
5. `needs_backend_choice`: ask once and stop before spending compute.
6. ComfyUI `ok`: inspect the output against selected trusted refs.
7. Built-in `planned`: call built-in image generation once from returned handoff/settings/refs.
8. Validate identity, stable traits, visible permanent details, anatomy and requested composition.
9. Only after a localized hard failure, and only when plan permits it, perform one targeted repair.
10. Record the accepted result with compact fingerprint plus provider/reproducibility metadata. Generated images join the reference fabric only if separately registered and quality-gated.

## Reference expansion / repair

For missing useful geometry, use `reference_expand`; selector parents remain golden/trusted. Register the output as generated+candidate with real provider and trusted parent IDs, then run identity/anatomy/stable-traits checks before promotion.

For localized failure, use `repair` with the failed image as `repair_of`. It is an edit target, not identity truth. Read `references/hybrid.md` only when cross-provider help is relevant.

## Progress / cost / privacy

Surface meaningful factual stages naturally (`context_compiled`, `plan_resolved`, `backend_selected`, `rendering`, `output_fetching`, `provider_complete`, recovery/setup events). Never dump raw events unless debugging.

Deterministic Python owns state, trust, selection, capability planning, hardware policy, cache, retries and metadata. Codex owns conversation, built-in image generation and visual judgement. Never ask another LLM which refs to use or resend the full reference bank/history.

## Brain invariant

Character Brain is an evidence graph, not prose. Stable facts require golden/trusted evidence or explicit user assertion/lock. Near ties are conflicts, never guesses. Provider choice may change dynamically; identity truth cannot.
