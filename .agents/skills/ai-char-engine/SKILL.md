---
name: ai-char-engine
description: Conversational persistent-character image workflow for Codex. Use when creating/resuming a synthetic adult visual character, ingesting references, preserving identity, intelligently coordinating local ComfyUI with Codex image generation, or installing/updating AI Character Engine.
---

# AI Character Engine

Act like a polished creative product, never a CLI tutorial. The user speaks naturally; AICE owns identity/state/trust/planning and image providers stay invisible workers.

## Product contract

- Ask only the next useful question; never re-ask known facts.
- Never expose `aice` commands, ComfyUI nodes/settings, paths, or JSON unless debugging is requested.
- Run internal commands yourself. `aice guide [character]` is authoritative for conversational stage.
- Accept unlimited user references until they say done.
- Character Brain and trusted references are **provider-neutral**. A character is never “an ImageGen character” or “a ComfyUI character”.
- Provider origin is provenance, not trust. A trusted image originally created by either engine may be reused by the other.
- User-approved evidence outranks generated evidence. Normal generated outputs enter as candidate; no provider may trust/promote its own output.
- Only golden/trusted references may condition normal generation. Never create recursive candidate lineage.
- Keep `.aice/` and `~/.aice/runtime` private/local; never commit characters, images, models, caches, or runtime state.
- Adult synthetic/original/authorized characters only.
- Default to one primary generation. A second provider call is allowed only for one justified repair/expansion stage, never because “hybrid” sounds better.

## Install / update

If `aice` is unavailable, install/update per `AGENTS.md`, then run doctor and guide. If the user says “update/refresh/güncel plugin”, use the latest-refresh path; do not ask for shell commands or reconfirm. Preserve their working tree and verify installed version/tests before claiming success.

## Onboarding

Follow `aice guide`.

### `choose_origin`
Ask whether to create from scratch or use existing references. Ask for a name only when absent.

### `describe_seed`
Ask for one natural appearance description, not a technical form. Then run the provider-neutral seed planner:

`aice seed-generate <character> "<description>" --budget balanced --progress`

Behavior:
- built-in Codex generation can always plan a no-reference seed;
- local ComfyUI may also create the first seed when its optional **bootstrap** capability is installed and validated;
- if both are genuinely available and preference is unsettled, ask one short natural-language backend question;
- “use Comfy for this seed” is a one-shot local choice; if bootstrap is missing, set it up via `references/comfyui.md` or offer built-in for this request;
- “you decide / whatever is best” means intelligent `auto` planning.

If result is built-in `planned`, call built-in `image_gen` with the returned contract. If ComfyUI returns `ok`, show its output. Do not register either as identity truth before approval.

### `approve_seed`
Show the seed and ask whether this is the identity to keep. If accepted, validate obvious anatomy and use `approve-seed`, recording its actual origin provider (`codex_builtin` or `comfyui`). The approved seed becomes golden because the **user** approved it, not because a provider produced it. If rejected, ask for the smallest correction and replace it.

After approval, either provider may use that same golden seed. If the plan contains optional `expand_after_approval`, use local ComfyUI only when useful to derive missing views; each derived result remains candidate until quality-gated.

### `collect_references`
Accept unlimited batches. Register user images as golden/user-origin, inspect only visible evidence, cache by SHA, and continue until the user says done. Old characters and old references remain valid; provider origin may be absent and is treated as unknown/user where inferable.

### `build_brain`
Read `references/brain.md`. Build truth only from golden/trusted evidence and explicit user assertions. Never guess invisible traits.

### `resolve_conflicts`
Show only ambiguous permanent facts and lock the user's answer.

### `optional_body_anchor`
Offer one proposed anchor or skip. A generated anchor is candidate until accepted/quality-gated. Side/back derivations require a trusted body anchor as before.

### `ready_to_finish`
Mark ready and continue to backend preference only when needed.

### `choose_backend`
Map natural replies:
- local / ComfyUI / my GPU -> persistent `comfyui` only if they clearly mean default;
- Codex / image_gen / built-in -> `codex_builtin`;
- you choose / automatic / best available / use whichever is better -> `auto`;
- ask every time -> `ask_each_time`.

`auto` means **choose and combine intelligently**: AICE chooses the strongest viable primary provider for the operation and may permit one cross-provider repair/reference-expansion stage after validation. It does not automatically double-generate.

Natural one-shot phrases such as “use both if useful”, “Comfy first but let ImageGen help if needed”, or “hybrid for this one” map to `--backend hybrid`; do not persist a new preference unless the user explicitly asks for a future default.

### `backend_attention`
Saved local preference is unavailable. Offer setup/repair or ask permission for built-in this time. Never silently leave an explicit/saved local choice.

### `ready`
Invite an ordinary-language photo request.

Read `references/onboarding.md` only during onboarding.

## Backend intent order

1. explicit provider/strategy in the current user request;
2. saved character preference;
3. deterministic backend/guide state.

Explicit `comfyui` never silently falls back. Explicit `codex_builtin` never starts ComfyUI. `auto`/one-shot `hybrid` may recover once and use the other engine when the plan allows it.

## Normal generation

1. Refresh `aice guide <character>` if state may have changed.
2. Run `aice generate <character> "<request>" --budget balanced --progress`.
3. For one-shot intent, add `--backend comfyui|codex_builtin|auto|hybrid`.
4. Read `trace` and `result.plan`; never invent percentages/ETAs.
5. `needs_backend_choice`: ask `backend_dialog` and stop before spending compute.
6. ComfyUI `ok`: inspect `output_path` against selected trusted refs.
7. Built-in `planned`: call built-in `image_gen` once using `handoff` / `effective_settings` and the selected refs, then inspect result.
8. Validate `pass/warn/fail`: recognizable identity, grounded stable traits, visible permanent details, anatomy, requested composition.
9. If a hard/localized failure exists and `plan.allow_cross_provider_repair` is true, the optional `repair_if_needed` stage permits exactly one targeted repair with the named provider. Do not perform it on a passing image.
10. Record the accepted result and reproducibility/provider provenance. A generated image only joins the reference fabric if separately registered and quality-gated.

### Reference expansion

When a missing angle/geometry is genuinely useful, call generation with `--operation reference_expand`. The existing selector still chooses only golden/trusted parents. Register the produced image as `generated` + `candidate` with its `origin_provider` and parent IDs. Run identity/anatomy/stable-traits checks before promotion. This is how an ImageGen-created character can expand through ComfyUI and vice versa without drift.

### Targeted repair

For a localized failed output, `--operation repair --repair-of <image>` treats the failed image as an edit target, **not identity truth**. Trusted refs remain the identity anchors. Never register the repair target itself as trusted merely because it was used in editing.

## Progress

Useful factual stages include:
- `seed_contract_compiled`, `context_compiled`
- `plan_resolved`, `backend_selected`, `backend_choice_required`, `backend_setup_required`
- `local_backend_starting`, `settings_resolved`, `references_uploading`
- `workflow_preparing`, `workflow_submitted`, `rendering`, `output_fetching`, `provider_complete`
- `builtin_planned`, `fallback_planned`, `recovering`, `provider_failed`

Translate only meaningful transitions naturally, e.g. “The references are ready; the local model is generating now.” Never expose raw trace unless debugging.

## Cost / privacy / consistency

- Deterministic Python owns state, trust, selection, capability planning, hardware policy, cache, retries and ledger. Codex owns conversation, built-in `image_gen`, and visual judgement.
- Never ask another LLM which refs to use, send full history/reference bank, or re-analyze unchanged SHA-cached refs.
- Balanced mode normally uses 2–3 relevant refs. Provider native caps may be lower.
- Permanent details enter prompts only when their body region should be visible.
- If geometry lacks trusted coverage, expand only what is needed; never fake confidence.
- Load `references/comfyui.md` only for local setup/execution/recovery.

## Brain invariant

Character Brain is an evidence graph, not prose. Stable facts require golden/trusted evidence or explicit user assertion/lock. Near ties are conflicts, never guesses. Provider choice can change dynamically; identity truth cannot.
