---
name: ai-char-engine
description: Conversational persistent-character image workflow for Codex. Use when creating/resuming a synthetic adult visual character, ingesting references, preserving identity, intelligently coordinating local ComfyUI with Codex image generation, or installing/updating AI Character Engine.
---

# AI Character Engine

Act like a polished interactive creative product, never a CLI tutorial. The user speaks naturally; AICE owns identity/state/trust/planning and image providers stay invisible workers.

## Product contract

- Ask only the next useful question; never re-ask known facts.
- Never expose `aice` commands, ComfyUI nodes/settings, paths, JSON, or raw traces unless debugging is requested.
- Run internal commands yourself. `aice guide [character]` is authoritative for conversational stage.
- Accept unlimited user references until they say done.
- Character Brain and trusted references are provider-neutral. A character is never tied to ImageGen or ComfyUI.
- Provider origin is provenance, not trust. A trusted image created by either engine may be reused by the other.
- User-approved evidence outranks generated evidence. Normal generated outputs enter as candidate; only golden/trusted refs may condition normal generation.
- Never create recursive candidate lineage or let a provider trust/promote its own output.
- Keep `.aice/` and `~/.aice/runtime` private/local; never commit characters, images, models, caches, or runtime state.
- Adult synthetic/original/authorized characters only.
- Default to one primary generation and at most one justified repair/reference-expansion call.

## Install / update

If `aice` is unavailable, install/update per `AGENTS.md`, then run doctor and guide. If the user says update/refresh/güncel/latest plugin, use the latest-refresh path automatically; do not ask for shell commands or reconfirm. Preserve their working tree and verify version/tests before claiming success.

## Onboarding

Follow `aice guide` exactly.

### `choose_origin`
Ask whether to create from scratch or use existing references. Ask for a name only when absent.

### `describe_seed`
Ask for one natural appearance description, not a form. Run the provider-neutral seed planner with `aice seed-generate` internally.

Built-in image generation can always plan a no-reference seed. Local ComfyUI may also create the first seed when its optional bootstrap capability is installed and validated. If both are viable and preference is unsettled, ask one short backend question. One-shot phrases such as “use Comfy for this seed” must not silently become defaults.

If the result is built-in `planned`, call built-in `image_gen` with the returned contract. If ComfyUI returns `ok`, show its output. Neither becomes identity truth before approval.

### `approve_seed`
Show the seed. If accepted, validate obvious anatomy and use the dedicated approved-seed path, recording the actual origin provider. User approval is what makes the seed golden. If rejected, ask for the smallest correction and replace it.

After approval, either provider may reuse the golden seed. Any generated expansion remains candidate until quality-gated.

### `collect_references`
Accept unlimited batches. User-uploaded refs are golden/user-origin. Inspect only visible evidence, cache by SHA, acknowledge briefly, and continue until the user says done.

### `build_brain`
Read `references/brain.md`. Build truth only from golden/trusted evidence and explicit user assertions. Never guess invisible traits.

### `resolve_conflicts`
Show only ambiguous permanent facts and lock the user's answer.

### `optional_body_anchor`
Offer one proposed anchor or skip. A generated anchor is candidate until accepted/quality-gated. Side/back body derivations still require a trusted body anchor.

### `ready_to_finish`
Mark ready and continue to backend preference only when needed.

### `choose_backend`
Map natural replies:
- local / ComfyUI / my GPU -> `comfyui`
- Codex / image_gen / built-in -> `codex_builtin`
- you choose / automatic / best available / whichever is better -> `auto`
- ask every time -> `ask_each_time`

Persist only when the user clearly chooses a future/default behavior. A current-request provider name is a one-shot override.

`auto` means intelligent planning, not double-generation. Natural one-shot phrases such as “use both if useful” or “hybrid for this one” map to `--backend hybrid`. Read `references/hybrid.md` only when cross-provider planning/repair/expansion is actually relevant.

### `backend_attention`
Saved local preference is unavailable. Offer setup/repair or ask permission to use built-in for this request. Never silently leave an explicit/saved local choice. Read `references/comfyui.md` for local setup/recovery.

### `ready`
Invite an ordinary-language photo request. Do not ask backend questions when only one engine is viable or explicit/saved intent already settles it.

Read `references/onboarding.md` only during onboarding.

## Backend intent order

1. explicit provider/strategy in the current request;
2. saved character preference;
3. deterministic backend/guide state.

Explicit `comfyui` never silently falls back. Explicit `codex_builtin` never starts ComfyUI. `auto` or one-shot `hybrid` may use a bounded alternate-provider fallback/follow-up only when the plan allows it.

## Explicit adult content

`aice generate` classifies explicitness itself; route on its result. Explicit adult synthetic requests use only the local ComfyUI adult profile (LUSTIFY SDXL) — never built-in generation, no silent downgrade. Status `local_adult_unavailable`: say it is not ready, offer setup or a non-explicit alternative, stop. Status `refused`: a disallowed category — relay it, do not retry. See `references/adult.md`.

## Normal generation

1. Refresh `aice guide <character>` if state may have changed.
2. Run provider-neutral `aice generate <character> "<request>" --budget balanced --progress` internally.
3. Add a one-shot `--backend comfyui|codex_builtin|auto|hybrid` only when current intent overrides the saved preference.
4. Read factual `trace` and generation `plan`; never invent percentages or ETAs.
5. `needs_backend_choice`: ask the friendly backend question and stop before spending compute.
6. ComfyUI `ok`: inspect `output_path` against selected trusted refs.
7. Built-in `planned`: call built-in `image_gen` once using returned handoff/effective settings and selected refs.
8. Validate `pass/warn/fail`: recognizable identity, grounded stable traits, visible permanent details, anatomy, requested composition.
9. If a localized hard failure exists and the plan permits it, perform one targeted repair only. Do not repair a passing image.
10. Record the accepted result with compact fingerprint and reproducibility/provider metadata. A generated image joins the reference fabric only if separately registered and quality-gated.

## Reference expansion / repair

For missing useful geometry, use generation operation `reference_expand`; the selector still supplies only golden/trusted parents. Register output as `generated` + `candidate` with its real provider and trusted parent IDs, then run identity/anatomy/stable-traits checks before promotion.

For localized failure, use operation `repair` with the failed image as `repair_of`. That image is an edit target, not identity truth; trusted refs remain the identity anchors.

Read `references/hybrid.md` for detailed cross-provider semantics.

## Progress

Useful factual stages include `seed_contract_compiled`, `context_compiled`, `plan_resolved`, `backend_selected`, `backend_choice_required`, `backend_setup_required`, `local_backend_starting`, `references_uploading`, `workflow_submitted`, `rendering`, `output_fetching`, `provider_complete`, `builtin_planned`, `fallback_planned`, `recovering`, and `provider_failed`.

Surface only meaningful transitions naturally, e.g. “The references are ready; the local model is generating now.” Never dump raw events unless debugging is requested.

## Cost / privacy / consistency

- Deterministic Python owns state, trust, selection, capability planning, hardware policy, cache, retries, and ledger. Codex owns conversation, built-in `image_gen`, and visual judgement.
- Never ask another LLM which refs to use, send full history/reference bank, or re-analyze unchanged SHA-cached refs.
- Balanced mode normally uses 2–3 relevant refs; providers may enforce lower native caps.
- Permanent details enter prompts only when their body region should be visible.
- If geometry lacks trusted coverage, expand only what is needed; never fake confidence.
- Load `references/comfyui.md` only for local setup/execution/recovery.

## Brain invariant

Character Brain is an evidence graph, not prose. Stable facts require golden/trusted evidence or explicit user assertion/lock. Near ties are conflicts, never guesses. Provider choice may change dynamically; identity truth cannot.
