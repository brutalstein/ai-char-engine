# AI Character Engine

A personal, Codex-native **persistent visual character engine**. It turns one or more approved reference images into a compact character state and a trusted multi-angle reference bank, then uses Codex's built-in image generation to create new photos of the same synthetic adult character with as little repeated context and as few image calls as practical.

The project is deliberately **not** an Image API wrapper. The default workflow uses Codex's built-in `image_gen` capability, so it does not require an `OPENAI_API_KEY`. The local Python layer only manages deterministic state, reference selection, history fingerprints, budgets, and quality gates.

## Why this architecture

The hard problem is not "generate a pretty image." It is long-term **identity continuity**:

- same recognizable face
- stable skin/hair/body traits
- permanent details only when grounded and visible
- multi-angle reference coverage without recursive drift
- less repetition in gaze, pose, framing, environment, and lighting
- bounded token/context usage
- bounded image retries

The engine separates four concerns:

```text
User prompt
   |
   v
Compact character state + content memory   (local, deterministic)
   |
   v
Reference selector + context compiler       (local, deterministic)
   |
   v
Codex reasoning + built-in image_gen        (semantic + visual)
   |
   v
Adaptive validation -> max one repair       (Codex)
   |
   v
Final image + tiny content fingerprint      (local state)
```

## Current OpenAI assumptions

This repository targets the current Codex plugin/skill model and the built-in system image-generation workflow. OpenAI's current system `imagegen` skill prefers the built-in `image_gen` tool for normal generation/editing and explicitly does **not** require `OPENAI_API_KEY`; its separate CLI/API fallback is opt-in only. GPT-Image-2 is OpenAI's current state-of-the-art image generation/editing model and supports high-fidelity image inputs.

Because built-in image generation is a Codex capability, unit tests validate the deterministic engine locally; the final live image-generation smoke test must be run inside Codex.

## Install locally

Requires Python 3.11+.

```powershell
git clone https://github.com/brutalstein/ai-char-engine.git
cd ai-char-engine
python -m pip install -e .
aice doctor
```

No API key is required for the default Codex workflow.

## Quick start

### 1. Create a character

```powershell
aice init maya
```

### 2. Register a seed

Inspect the image first and tag only what is actually visible.

```powershell
aice seed maya C:\path\seed.png --tags face,front,upper_body
```

### 3. Inspect the profile template

```powershell
aice profile-template maya
```

In normal use the Codex skill inspects trusted images, writes only grounded stable traits, and applies the compact JSON update with `aice set-profile`.

### 4. Build missing reference coverage

```powershell
aice bootstrap-plan maya
```

The plan returns only missing roles. Generated refs enter as **candidate**. They cannot be used for normal generations until they pass identity/anatomy/stable-trait checks.

If a portrait seed does not establish body geometry, the engine will not silently generate a full body and then recursively treat it as truth. It may propose one high-extrapolation `full_body_front` anchor, but that anchor requires explicit user approval before side/back body refs can derive from it.

### 5. Generate through Codex

With the plugin/skill active, a short request is enough:

```text
Generate Maya in an old-town cafe on a rainy afternoon, candid friend-taken photo.
```

The skill runs a compact context compile, opens only selected references, invokes built-in image generation once, validates according to budget, applies at most one targeted correction, and records the final content fingerprint. If the requested camera geometry is not covered by trusted references, the context reports a `coverage_gaps` list so Codex can lazily expand the reference bank instead of silently hallucinating confidence.

## Budgets

| Mode | Ref cap | History window | Validation | Repair cap |
|---|---:|---:|---|---:|
| `economy` | 2 | 4 | critical-only | 0 |
| `balanced` | 3 | 8 | light | 1 |
| `quality` | 4 | 12 | full | 1 |

`balanced` is the default.

Example:

```powershell
aice context maya "walking through Rome at sunset" --budget balanced --compact
aice prompt maya "walking through Rome at sunset" --budget balanced
```

## Character data layout

Runtime state is local and ignored by git:

```text
.aice/
  characters/
    maya/
      character.json
      references/
        manifest.json
        golden/
        trusted/
        candidates/
        rejected/
      outputs/
        drafts/
        approved/
        rejected/
      history/
        generations.jsonl
      cache/
```

### Trust model

- `golden`: user-uploaded or explicitly user-approved source of truth
- `trusted`: generated reference that passed the required quality gate
- `candidate`: generated but not yet trusted
- `rejected`: failed quality gate

Normal image generations select only `golden` and `trusted` references.

## Character brain

`character.json` separates:

- immutable/stable identity evidence
- body evidence
- permanent features with visibility tags
- mutable continuity state
- content-style preferences
- hard identity rules

Unknown means unknown. The engine is designed not to turn guesses into identity truth.

## Anti-repetition memory

The engine does not resend past images. It stores a tiny fingerprint per accepted generation:

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

Repeated recent values become compact "avoid repeating ..." hints in the next context.

## Useful commands

```text
aice doctor
aice init <name>
aice seed <character> <image> [--tags ...]
aice profile-template <character>
aice set-profile <character> --json <json-or-file>
aice add-ref <character> <image> --role ...
aice promote-ref <character> <ref-id> --checks ...
aice reject-ref <character> <ref-id> --reason ...
aice list-refs <character>
aice bootstrap-plan <character>
aice context <character> "<prompt>" --budget balanced --compact
aice prompt <character> "<prompt>" --budget balanced
aice record <character> <image> --prompt ... --fingerprint ...
aice stats <character>
```

## Test

```powershell
python -m unittest discover -s tests -v
```

The tests need no network and no OpenAI API key.

## Design boundaries

This project is for persistent **adult synthetic/original/authorized** visual characters. Keep a virtual-creator account transparently presented as virtual/synthetic; do not use the workflow to impersonate real people without permission.

## Status

`v0.1.0` is intentionally a focused single-character engine: state, trusted-reference bootstrap, lazy reference expansion, deterministic reference selection, prompt/context budgeting, anti-repetition fingerprints, bounded validation policy, and Codex-native image generation orchestration.
