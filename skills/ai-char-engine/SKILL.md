---
name: ai-char-engine
description: Maintain one persistent adult synthetic visual character across many GPT-Image generations with a compact local identity brain, trusted multi-angle references, anti-repetition memory, bounded validation, and no separate OpenAI API key. Use when the user wants to bootstrap, expand, inspect, or generate new photos of the same virtual creator/persona in Codex.
---

# AI Character Engine

This skill is a Codex-native orchestration layer around the built-in system `imagegen` capability. The deterministic Python CLI owns state; Codex owns semantic reasoning and visual inspection; the built-in `image_gen` tool owns generation/editing.

## Non-negotiable architecture

- Default image backend: Codex built-in `image_gen` through the system `imagegen` skill.
- Do **not** use the Image API, `OPENAI_API_KEY`, or a custom SDK runner unless the user explicitly asks to leave the Codex built-in path.
- Keep the character state under `.aice/`; it is local/private and gitignored by default.
- Treat user-approved uploaded references as the source of truth. Generated references are candidates until they pass the quality gate.
- Never recursively derive new trusted references from untrusted candidates.
- Never hallucinate invisible permanent details. If a tattoo, birthmark, jewelry item, body geometry, or facial feature is not grounded by trusted evidence, leave it unknown.
- The engine is intentionally restricted to adult synthetic/original/authorized characters. Do not use it to impersonate a real person without permission.
- Optimize for **consistency per model call**, not maximum agent activity.

## First-run setup

From repo root:

```bash
python -m pip install -e .
aice doctor
```

If `aice` already works, do not reinstall it.

## Modes

Infer one of these modes from the user's request:

1. `bootstrap` — create a new character from a user image or a freshly generated seed.
2. `expand` — fill missing trusted reference angles only.
3. `generate` — create a new lifestyle/social photo from a short user prompt.
4. `inspect` — show compact profile/reference/history state without generating.

Do not ask the user to restate information that is already in `.aice`.

---

# Bootstrap workflow

## A. Create the character state

```bash
aice init <character-name>
```

If the user supplied a seed image, inspect it with `view_image` **before** registering it. Determine only visible evidence tags such as:

- `face`
- `front`
- `upper_body`
- `full_body`
- `side`
- `back`
- `hands`
- `arms`
- `legs`

Then register it, for example:

```bash
aice seed <character> <seed-path> --tags face,front,upper_body
```

If there is no user seed, use the built-in `image_gen` tool once to create a primary adult synthetic seed, show it to the user, and only after acceptance register it as the seed.

## B. Build the compact identity brain

Run:

```bash
aice profile-template <character>
```

Inspect all user-approved golden references with `view_image`. Fill only grounded facts into a small JSON patch and apply it with:

```bash
aice set-profile <character> --json <json-file>
```

Prioritize stable traits:

- adult age range, not an exact age unless explicitly established
- facial structure traits that are visibly stable
- skin tone / undertone
- natural hair color and stable hairline traits
- eye color when actually visible
- stable body description only if body evidence exists
- permanent features (tattoo, birthmark, piercing) only when visible and unambiguous
- `visibility_tags` for permanent features, e.g. `hands`, `arms`, `left_wrist`
- current mutable state only when the user explicitly wants continuity over time

Keep descriptions concise. Do not write prose biographies into `character.json`.

## C. Expand references lazily

Run:

```bash
aice bootstrap-plan <character>
```

Process only the returned `missing` tasks. Do not generate blocked roles.

For each task:

1. `view_image` the returned `anchor_path`.
2. Use built-in `image_gen` with the task prompt.
3. Move/copy the generated result from Codex's generated-images location into a normal accessible workspace path if needed.
4. Register it as a candidate:

```bash
aice add-ref <character> <image-path> \
  --role <role> \
  --source generated \
  --tier candidate \
  --tags <comma-separated-tags> \
  --parents <anchor-id>
```

5. Inspect candidate and trusted anchor(s) with `view_image`.
6. Evaluate exactly these required checks:
   - `identity`: same recognizable character, no face redesign
   - `anatomy`: plausible, clean anatomy for the visible crop
   - `stable_traits`: no unsupported drift in grounded skin/hair/body/permanent features
7. If all pass, promote to trusted:

```bash
aice promote-ref <character> <ref-id> \
  --checks '{"identity":"pass","anatomy":"pass","stable_traits":"pass"}'
```

If any required check fails, reject it instead of retrying indefinitely:

```bash
aice reject-ref <character> <ref-id> --reason "<short reason>"
```

### High-extrapolation rule

If `bootstrap-plan` marks `requires_user_approval: true`, the trusted evidence did not actually establish that geometry (commonly a full body inferred from a portrait).

Generate at most **one** proposed anchor. Show it to the user. Do not use it to derive side/back body references until the user accepts it. On explicit approval, promote it to golden:

```bash
aice promote-ref <character> <ref-id> \
  --checks '{"identity":"pass","anatomy":"pass","stable_traits":"pass"}' \
  --golden --user-approved
```

This prevents synthetic extrapolation from silently becoming identity truth.

---

# Normal generation workflow

The user should be able to say something short such as:

> cafe in Milan, rainy afternoon, candid friend-taken photo

## 1. Compile minimal context

Default to balanced:

```bash
aice context <character> "<user request>" --budget balanced --compact
```

Available budgets:

- `economy`: at most 2 refs, smallest history context, critical-only validation, no repair loop
- `balanced`: at most 3 refs, compact anti-repetition memory, one light validation, max 1 targeted repair
- `quality`: at most 4 refs, larger context, full validation, max 1 targeted repair

Never load the full history or full reference bank into context.

If `coverage_gaps` is non-empty, do not silently pretend the identity bank covers that geometry. For `side`, `back`, or `full_body` gaps, run `aice bootstrap-plan <character>` and lazily fill a grounded missing reference first when possible. If the only path is a `high-extrapolation` anchor, generate at most one proposal and require explicit user approval before making it identity truth. A missing `face` anchor is a hard stop: request/register a trusted face reference.

## 2. Load only selected references

For each path in `references`, call `view_image` in the listed order. Do not load candidate/rejected references for normal generation.

## 3. Compile the generation prompt

Use:

```bash
aice prompt <character> "<user request>" --budget <budget>
```

Use this as the base prompt. You may make **one small semantic refinement** when the user's wording needs scene interpretation, but do not turn it into a giant prompt.

Preserve these principles:

- same exact adult synthetic character
- reference images are identity references, not edit targets
- only visible permanent details are mentioned
- candid/natural camera language when appropriate
- explicit anti-repetition hints from recent history
- realistic anatomy, skin, optics, and lighting
- no gratuitous body exaggeration
- no text/watermark unless explicitly requested

## 4. Generate once

Use the built-in `image_gen` tool once.

Do not produce multiple speculative variants unless the user requested variants.

## 5. Adaptive validation

### economy

Inspect only if there is an obvious identity/anatomy concern or the scene exposes a critical permanent detail.

### balanced

Inspect final once against the loaded references. Check:

- recognizable face/identity
- grounded skin/hair continuity
- stable body continuity where visible
- permanent visible details
- obvious anatomy/artifact failures
- repeated pose/gaze if anti-repetition constraints were active

### quality

Perform the balanced checks plus composition, perspective, hands, and all visible permanent details.

Use ordinal results (`pass`, `warn`, `fail`) rather than pretending to have scientifically calibrated face-similarity percentages.

If a hard invariant fails and the budget allows repair, perform **one targeted edit** with built-in image generation/edit semantics. Repeat the invariants and change only the failed property. Never enter an open-ended regenerate loop.

## 6. Persist only the final

Create a tiny content fingerprint with these fields when known:

```json
{
  "shot": "waist-up",
  "angle": "3q-right",
  "gaze": "away",
  "pose": "walking",
  "environment": "old-town-street",
  "lighting": "late-afternoon",
  "outfit": "red-shirt"
}
```

Record the final path:

```bash
aice record <character> <final-image-path> \
  --prompt "<original user request>" \
  --fingerprint '<compact-json>' \
  --validation '<compact-pass-warn-fail-json>' \
  --status approved \
  --budget <budget>
```

Do not keep rejected built-in variants in the character output folders unless the user asks.

---

# Token/call optimization rules

These rules are mandatory:

1. Prefer deterministic Python over extra model calls.
2. Never ask another model which refs to use; `aice context` already does deterministic selection.
3. Do not resend the full character profile when selected image references carry the identity.
4. Do not resend history images. Use only compact fingerprints from history.
5. Do not analyze the same reference repeatedly for metadata if its SHA-256 has not changed.
6. Use candidate references only for candidate validation, never normal generation.
7. Expand the reference bank on demand, not preemptively.
8. Default to `balanced` unless the user asks for lowest usage or maximum quality.
9. One generation is the normal path; one targeted repair is the bounded exception path.
10. Do not use subagents for ordinary generations.
11. Keep prompt augmentation short; preserve the user's intent instead of inventing a story.
12. If a detail is not visible in the requested composition, omit it from active prompt context.

---

# Inspect / maintenance

Useful commands:

```bash
aice list-refs <character>
aice stats <character>
aice context <character> "<request>" --budget balanced --compact
aice bootstrap-plan <character>
```

If the user explicitly changes a persistent trait (for example, cuts hair), update `mutable_state`. Do not overwrite immutable identity traits.

If the user uploads a stronger identity reference, register it as `user_uploaded`. It may be golden because it is explicit user evidence. Generated images never become golden without explicit user approval.

# Success criterion

A successful run is not "the model called many tools." It is:

> the fewest reasonable model/image calls that produce a believable new photo of the same persistent adult synthetic person, with no silent identity drift and no repetitive visual pattern.
