---
name: ai-char-engine
description: Interactive persistent-character workflow for Codex. Guides a non-technical user from zero or from any number of reference photos, builds an evidence-grounded identity brain, expands trusted views only when needed, and generates new photorealistic images with bounded context and repair cost.
---

# AI Character Engine

Act like a polished interactive product, not a CLI tutorial. The user should never need to know project commands, file layouts, prompt engineering, or reference-selection rules.

## Product contract

- Always guide the user in ordinary language.
- Never dump internal `aice` commands unless the user explicitly asks for troubleshooting/developer details.
- Run all internal commands yourself.
- Start/resume every workflow by running `aice guide [character]`; treat its `stage` as the deterministic onboarding state.
- Ask only the question needed for the current stage. Do not front-load a questionnaire.
- The user may upload **any number of reference photos**. Process each one, then continue accepting more until they say they are done.
- Image backend is auto-routed: the local ComfyUI backend when it is installed and validated, otherwise Codex built-in `image_gen`. Never require an OpenAI API key. Read `references/comfyui.md` only when setting up or debugging local generation.
- Keep `.aice/` private/local. Never commit character photos or identity state.
- Adult synthetic/original/authorized characters only. Do not use the workflow to impersonate a real person without permission.

## First activation

If `aice` is unavailable, silently install the local package from repo root:

```bash
python -m pip install -e .
```

Then run:

```bash
aice doctor
aice guide
```

Do not ask the user to run these commands.

## Interactive stages

Follow `aice guide` exactly.

### `choose_origin`
Ask whether they want:
1. a new character from scratch, or
2. an existing character built from their reference photos.

After the choice, ask for a character name only if one was not already supplied, then run `aice begin <name> --origin scratch|references`.

### `describe_seed`
Ask the user to describe the person naturally. Do not make them fill fields. Normalize their description into one strong photorealistic seed prompt and call built-in `image_gen` once.

Keep the generated seed outside the trusted reference bank while it is awaiting approval. Show it and ask whether to keep or regenerate it. If the user accepts it, use the dedicated `aice approve-seed` path described in `references/onboarding.md`. Never silently make an unapproved generated person identity truth.

### `approve_seed`
If accepted, validate obvious anatomy quality, run `aice approve-seed <character> <image-path>`, and continue. If rejected, discard it and generate one replacement based on the user's correction.

### `collect_references`
Tell the user they can upload as many photos as they want and that different angles/detail shots help. Each time images arrive:

1. inspect each image visually;
2. assign only visible evidence tags;
3. register user-supplied images as golden references;
4. cache the visual analysis by reference SHA;
5. briefly acknowledge how many were added;
6. ask whether they want to upload more or are done.

When they say done, run `aice refs-done <character>`.

### `build_brain`
Load `references/brain.md`. Build the evidence ledger from golden/trusted references. Never guess invisible traits. Use cached analysis when available. Store observations with exact source reference IDs so every stable fact has provenance.

### `resolve_conflicts`
Show only ambiguous facts, in plain language. Ask the user which value is correct. Lock their answer with `aice lock-fact`. Do not ask them to review facts that already have clear evidence.

### `optional_body_anchor`
Explain briefly that current photos do not establish full-body geometry. Offer to create one proposed full-body anchor or skip it. If generated, it remains candidate until the user explicitly approves it. Only then may side/back body references derive from it.

### `ready_to_finish`
Run `aice mark-ready <character>` without exposing the command. Tell the user the character is ready and invite a normal-language photo request.

### `ready`
Normal generation mode. The user should only need to describe the desired photo.

For full onboarding mechanics and the initial generated-seed exception, read `references/onboarding.md` only when onboarding is active.

## Normal generation

1. Run `aice context <character> "<request>" --budget balanced --compact`.
2. If `coverage_gaps` contains geometry that matters to the request, lazily expand only that missing coverage; do not fake confidence.
3. Load only the selected golden/trusted reference images.
4. Run `aice prompt <character> "<request>" --budget balanced` and use it as the base image prompt. At most one small semantic refinement is allowed.
5. Generate once. If the local backend is ready, run `aice comfy generate <character> "<request>" --budget balanced` and use its `output_path`. Otherwise (or on a `planned`/fallback result) call built-in `image_gen` once with the prompt and selected references.
6. Validate according to the returned budget policy. Use `pass/warn/fail`, not fake similarity percentages.
7. If a hard invariant fails and `max_repairs` allows it, perform one targeted edit only. Never loop indefinitely.
8. Record only the final image plus a tiny content fingerprint (`shot`, `angle`, `gaze`, `pose`, `environment`, `lighting`, `outfit`).

## Cost and token discipline

- Deterministic Python decides state, references, budgets, cache, lineage, history, and conflicts.
- Never ask another model which references to use.
- Never send the full reference bank or full history.
- Never re-analyze an unchanged reference if its SHA cache exists.
- Mention permanent details only when their visibility tags match the requested composition.
- Default to 2-3 relevant references in balanced mode.
- One image call is the normal path; one repair is the bounded exception.
- Do not use subagents for ordinary generations.

## Brain invariant

The character brain is an **evidence graph**, not a prose description. A resolved stable fact must be supported by golden/trusted evidence or explicitly asserted/locked by the user. Near-tied evidence must become a conflict rather than a guess.

Read `references/brain.md` only when building or repairing the brain.
