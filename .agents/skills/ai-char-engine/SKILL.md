---
name: ai-char-engine
description: Conversational persistent-character image workflow for Codex. Use when creating or resuming a synthetic adult visual character, ingesting references, preserving identity, choosing local ComfyUI vs Codex image generation, generating/editing character photos, or installing/updating AI Character Engine as the current Codex plugin.
---

# AI Character Engine

Act like a polished creative product, not a CLI tutorial. The user talks naturally; operate AICE, reference state, image backends, and validation invisibly.

## Product contract

- Ask only the next useful question in ordinary language; never re-ask known facts.
- Never expose `aice` commands, ComfyUI nodes/settings, paths, or JSON unless developer/debug detail is requested.
- Run internal commands yourself. Start/resume character work with `aice guide [character]`; its `stage` is authoritative.
- Accept any number of user reference photos until they say done.
- Keep `.aice/` and `~/.aice/runtime` private/local; never commit character state, images, models, or runtime data.
- User-approved evidence outranks generated evidence. Generated refs stay candidates until quality-gated; never create recursive untrusted lineage.
- Adult synthetic/original/authorized characters only; do not impersonate a real person without permission.
- Default to one generation and at most one targeted repair.

## First activation

If `aice` is unavailable, silently install/update as instructed by `AGENTS.md`, then run `aice doctor` and `aice guide`. Ask for terminal help only for a real external blocker.

## Plugin refresh intent

If the user naturally says things like "update this plugin", "refresh this repo", "bu repoyu güncel plugin olarak güncelle", "make this the current plugin", or equivalent:

- treat that as permission to perform the update yourself; do not ask them to run commands or reconfirm;
- use the latest-refresh path from `AGENTS.md` so remote `main` is installed without modifying the user's working tree;
- replace/update the existing personal `ai-char-engine` plugin registration instead of creating duplicates;
- run plugin validation, core doctor, and tests before claiming success;
- report the installed version/revision concisely and mention a Codex restart only if discovery actually needs it.

## Interactive onboarding

Follow `aice guide` exactly.

### `choose_origin`
Ask whether to create a new character or use existing reference photos. Ask for a name only if absent, then create state.

### `describe_seed`
Ask for a natural appearance description, not a form. Compile one photorealistic seed prompt and use Codex built-in `image_gen` once. The current local workflow is reference/edit-oriented, so do not claim it can create the first no-reference identity seed. Keep the seed untrusted until approval.

### `approve_seed`
Show the seed. If accepted, validate obvious anatomy and use the dedicated approved-seed path. If rejected, ask for the smallest correction and make one replacement at a time.

### `collect_references`
Accept unlimited batches. Inspect only visible evidence, register user images as golden, cache analysis by SHA, briefly acknowledge the batch, and continue until the user says done.

### `build_brain`
Read `references/brain.md`. Build the evidence ledger only from golden/trusted sources and cached analyses. Every stable visual fact needs provenance; never guess invisible traits.

### `resolve_conflicts`
Show only ambiguous permanent facts in plain language and lock the user's answer.

### `optional_body_anchor`
Offer one proposed full-body anchor or skip it. A generated anchor remains candidate until explicit approval; only then may side/back body refs derive from it.

### `ready_to_finish`
Mark ready and continue into backend choice if needed.

### `choose_backend`
Explain briefly that both engines are ready. Map natural replies:
- local / ComfyUI / my GPU -> `comfyui`
- Codex / image_gen / built-in -> `codex_builtin`
- you choose / automatic / best available -> `auto`
- ask every time -> `ask_each_time`

Persist only when the user clearly chooses a future/default behavior. "Make this one with ComfyUI" is a one-shot override.

### `backend_attention`
The saved local preference is not ready. Offer setup/repair or built-in generation for this request. Never silently switch away from explicitly chosen local generation. Read `references/comfyui.md` for setup/recovery.

### `ready`
Invite a normal-language photo request. Do not ask backend questions when only one engine is viable or explicit/saved intent already settles it.

Read `references/onboarding.md` only during onboarding.

## Backend intent

Resolve backend intent in this order:
1. explicit backend in the current user request;
2. saved character preference;
3. deterministic `aice backend status` / `aice guide` state.

If both are ready and preference is unset/ask-each-time, ask once before spending compute. `auto` may use validated ComfyUI and fall back to built-in after one bounded recovery. Forced `comfyui` never silently falls back; forced `codex_builtin` never starts ComfyUI.

## Normal generation

1. Run `aice guide <character>` if state may have changed; resolve `choose_backend` / `backend_attention` first.
2. Run `aice generate <character> "<request>" --budget balanced --progress`. Add `--backend comfyui|codex_builtin|auto` only for a one-shot override.
3. Read `trace`; never invent percentages or ETAs.
4. `needs_backend_choice`: ask the friendly `backend_dialog` question and stop.
5. ComfyUI `ok`: load `output_path` and validate against selected trusted refs.
6. Built-in `planned`: call built-in `image_gen` once with `effective_settings.prompt` and listed selected refs, then validate.
7. Validate with `pass/warn/fail`: recognizable identity, grounded stable traits, visible permanent details, anatomy, and requested composition. Never invent biometric percentages.
8. If a hard invariant fails and budget permits, make one targeted repair only.
9. Record the accepted final image with a tiny fingerprint (`shot`, `angle`, `gaze`, `pose`, `environment`, `lighting`, `outfit`) and backend/reproducibility metadata when available.

## Progress communication

Useful factual trace stages:
- `context_compiled`, `backend_selected`
- `local_backend_starting`, `references_uploading`
- `workflow_submitted`, `rendering`
- `output_fetching`, `provider_complete`
- `builtin_planned`, `fallback_planned`
- `recovering`, `provider_failed`, `backend_choice_required`

Surface only meaningful transitions naturally, e.g. "References are ready; the local model is generating now." Then "The image is ready; I'm checking identity and details." Do not dump raw events unless debugging is requested.

## Cost, privacy, consistency

- Deterministic Python owns state, trust, selection, routing, hardware policy, cache, retries, and history; Codex owns conversation, built-in `image_gen`, and visual judgement.
- Never ask another model which refs to use, send the full reference bank/history, or re-analyze an unchanged ref with valid SHA cache.
- Mention permanent details only when their region should be visible. Balanced mode normally uses 2-3 relevant refs; a provider may enforce a lower native cap.
- If requested geometry lacks trusted coverage, expand only what is needed and never fake confidence.
- Load `references/comfyui.md` only for local setup/execution detail/recovery.

## Brain invariant

The Character Brain is an evidence graph, not prose. A stable fact requires golden/trusted evidence or explicit user assertion/lock. Near-tied evidence becomes a conflict, not a guess. Read `references/brain.md` only when building or repairing the brain.
