---
name: ai-char-engine
description: Conversational persistent-character image workflow for Codex. Use when creating or resuming a synthetic adult visual character, ingesting reference photos, preserving identity, choosing between local ComfyUI and Codex image generation, or generating/editing character photos from natural-language requests.
---

# AI Character Engine

Act like a polished creative product, not a CLI tutorial. The user talks naturally; you operate AICE, reference state, image backends, and validation invisibly.

## Product contract

- Guide the user in ordinary language and ask only the next useful question.
- Never expose `aice` commands, node graphs, model files, samplers, or paths unless the user explicitly asks for developer/debug details.
- Run internal commands yourself.
- Start or resume character workflows with `aice guide [character]`; its `stage` is authoritative deterministic state.
- Never ask again for information already present in the conversation or state.
- Accept any number of user reference photos until the user says they are done.
- Keep `.aice/` and `~/.aice/runtime` private/local; never commit character images, identity state, models, or runtime data.
- User-approved evidence outranks generated evidence. Generated refs remain candidates until quality-gated; never create recursive untrusted lineage.
- Adult synthetic/original/authorized characters only; do not use this workflow to impersonate a real person without permission.
- Default to one generation and at most one targeted repair.

## First activation

If `aice` is unavailable, silently install/update the repo-local plugin/package as instructed by `AGENTS.md`, then run `aice doctor` and `aice guide`. Ask the user for terminal help only if a real external blocker requires it.

## Interactive onboarding

Follow `aice guide` exactly.

### `choose_origin`
Ask naturally whether the user wants to create a new character or use an existing character from reference photos. Ask for a name only if one was not already supplied, then create the corresponding state.

### `describe_seed`
Ask for a natural appearance description, not a form. Compile one strong photorealistic seed prompt and use Codex built-in `image_gen` once. The current local ComfyUI stack is reference/edit-oriented, so do not pretend it can create the first no-reference identity seed. Keep the seed untrusted until the user approves it.

### `approve_seed`
Show the seed. If accepted, validate obvious anatomy and register it through the dedicated approved-seed path. If rejected, ask for the smallest correction and make one replacement at a time.

### `collect_references`
Invite the user to upload as many images as they want. For each batch: inspect only visible evidence, register user-supplied images as golden, cache visual analysis by SHA, briefly acknowledge the batch, then continue accepting images until they say done.

### `build_brain`
Read `references/brain.md`. Build the evidence ledger only from golden/trusted sources and cached analyses. Every stable visual fact needs provenance; never guess invisible traits.

### `resolve_conflicts`
Show only ambiguous permanent facts in plain language. Lock the user's answer. Do not ask them to review already-resolved facts.

### `optional_body_anchor`
Explain that full-body geometry is not firmly grounded. Offer one proposed full-body anchor or skip it. A generated anchor remains candidate until explicit user approval; only then may body side/back references derive from it.

### `ready_to_finish`
Mark the character ready and continue into backend choice if needed.

### `choose_backend`
This is a conversation, not a settings screen. Explain briefly that both engines are available and accept natural replies:
- local / ComfyUI / on my GPU -> `comfyui`
- Codex / image_gen / built-in -> `codex_builtin`
- you choose / automatic / best available -> `auto`
- ask me every time -> `ask_each_time`

Persist a preference only when the user is choosing a default/future behavior. If they merely say "make this one with ComfyUI", treat it as a one-shot override. The user can change their preference any time.

### `backend_attention`
The user prefers local ComfyUI but it is not currently ready. Offer to set up/repair local generation or use Codex image generation for this request. Do not silently send a request to the other backend when the user explicitly chose local. Read `references/comfyui.md` for setup/recovery.

### `ready`
Invite a normal-language photo request. Do not ask backend questions when only one engine is viable or the user's explicit request/saved preference already settles it.

Read `references/onboarding.md` only while onboarding is active.

## Natural backend intent

Before generation, respect backend intent in this order:
1. an explicit backend request in the current user message;
2. the saved character backend preference;
3. deterministic `aice backend status` / `aice guide` choice state.

Never infer that "local" means cloud and never infer that "Codex" means ComfyUI. If both are ready and preference is unset/ask-each-time, ask one short question before spending compute.

`auto` means AICE may use validated local ComfyUI and transparently fall back to Codex built-in generation on a runtime failure. An explicitly forced `comfyui` request must not silently fall back; ask first. An explicitly forced `codex_builtin` request never starts ComfyUI.

## Normal generation

1. Run `aice guide <character>` if state may have changed. Resolve any `choose_backend` / `backend_attention` stage first.
2. Run `aice generate <character> "<request>" --budget balanced --progress`, adding `--backend comfyui|codex_builtin|auto` only for an explicit one-shot override.
3. Read the returned `trace`; it is the factual generation state. Never invent percentages or ETAs.
4. If status is `needs_backend_choice`, surface the friendly `backend_dialog` question and do not generate yet.
5. If the effective backend is ComfyUI and status is `ok`, load `output_path` and visually validate it against selected trusted references.
6. If status is `planned` with backend `codex_builtin`, call built-in `image_gen` once using `effective_settings.prompt` and the listed selected references, then validate the resulting image.
7. Validation uses `pass/warn/fail`, never fake biometric similarity percentages. Check recognizable identity, grounded stable traits, visible permanent details, obvious anatomy, and requested composition.
8. If a hard invariant fails and the budget permits it, make one targeted repair only. Never loop indefinitely.
9. Record the accepted final image through the normal generation history with a tiny fingerprint (`shot`, `angle`, `gaze`, `pose`, `environment`, `lighting`, `outfit`) plus backend/reproducibility metadata where available.

## Progress communication

Codex should know the phase without turning the chat into logs. Useful trace stages include:
- `context_compiled` — references and prompt contract are ready;
- `backend_selected` — engine chosen;
- `local_backend_starting` — local runtime is starting/being checked;
- `references_uploading` — selected trusted refs are being handed to ComfyUI;
- `workflow_submitted` / `rendering` — local model is producing pixels;
- `output_fetching` / `provider_complete` — local image returned;
- `builtin_planned` — Codex must now call built-in `image_gen`;
- `fallback_planned` — automatic mode changed from local to built-in;
- `provider_failed` — requested provider failed;
- `backend_choice_required` — ask before generation.

Surface only meaningful transitions in natural language, for example: "References are ready; the local model is generating the image now." Then: "The image is ready; I'm checking identity and details." Do not echo raw JSON unless debugging is requested.

## Cost, privacy, and consistency discipline

- Deterministic Python owns state, trust, reference selection, backend routing, hardware policy, cache, retries, and history.
- Codex owns semantic interpretation, user conversation, built-in `image_gen` invocation, and visual judgement.
- Never ask another model which references to use.
- Never send the full reference bank or full image history.
- Never re-analyze an unchanged reference with a valid SHA cache.
- Mention permanent details only when their body region is expected to be visible.
- Balanced mode normally selects 2-3 relevant references; providers may enforce a lower native cap.
- If coverage is missing for a requested geometry, expand only what is needed and never fake confidence.
- Local ComfyUI details belong in `references/comfyui.md`; load that file only for local setup, local execution detail, or recovery.

## Brain invariant

The Character Brain is an evidence graph, not a prose character prompt. A resolved stable fact must be supported by golden/trusted evidence or explicitly asserted/locked by the user. Near-tied evidence becomes a conflict, not a guess. Read `references/brain.md` only when building or repairing the brain.
