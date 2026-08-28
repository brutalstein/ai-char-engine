# AI Character Engine

**A Codex-native persistent visual-character engine.** Build one synthetic adult character once, then generate new photorealistic images of that same identity through Codex image generation, local ComfyUI, or a capability-aware combination of both.

The product is conversational by design. The normal user does **not** need to learn commands, prompting tricks, ComfyUI nodes, checkpoints, samplers, CUDA settings, reference scoring, or lineage rules.

## Architecture

A character belongs to **AICE**, not to an image provider:

```text
User natural language
        ↓
      Codex
        ↓
 AI Character Engine
 ├─ interactive state
 ├─ Character Brain
 ├─ provider-neutral reference fabric
 ├─ trust / provenance / lineage
 ├─ scene-aware reference selector
 ├─ capability-aware strategy planner
 ├─ capability-specific local validation
 ├─ bounded validation / repair policy
 └─ reproducibility metadata
        ↓
   ┌───────────────┬────────────────────┐
   │               │                    │
ComfyUI local   Codex image_gen   optional one-stage handoff
   └───────────────┴────────────────────┘
```

A golden/trusted reference created by one engine can be used by the other. **Provider origin is provenance, not trust.** Generated derivatives never promote themselves: they enter as candidates and must pass the same identity/anatomy/stable-traits quality gate.

## Current capabilities

- create a character from scratch or ingest existing reference photos
- accept unlimited user references during onboarding
- persistent evidence-grounded Character Brain
- source provenance, conflict surfacing, and explicit user locks
- golden / trusted / candidate / rejected lineage
- SHA-256 analysis caching and deterministic reference selection
- visibility-aware permanent details such as tattoos, marks, and accessories
- recent-pose anti-repetition without resending old generations
- provider-neutral trusted references usable by both image engines
- local ComfyUI identity generation with Qwen-Image-Edit-2509 GGUF
- optional local no-reference Qwen-Image bootstrap
- optional local-only explicit-adult profile using LUSTIFY SDXL v4 + IP-Adapter identity
- Codex built-in image generation without an AICE OpenAI API key
- automatic capability-aware provider planning
- explicit one-shot hybrid cooperation when useful
- bounded cross-provider repair/reference expansion
- factual progress events rather than fake percentages
- pinned/reproducible local runtime and model metadata
- localhost-only ComfyUI and private local character state

## Install or update with Codex

Open or clone this repository in Codex and say:

> Install this plugin and make it ready for me.

Later you can simply say:

> Bu repoyu güncel plugin olarak güncelle.

Codex is instructed to perform registration/update, validation, doctor checks, and tests itself. The `--latest` refresh path uses a clean shallow checkout of remote `main`, so updating the installed plugin does not rewrite an unrelated dirty working tree.

Repository: `https://github.com/brutalstein/ai-char-engine`

## Creating a character

### From scratch

Say:

> Yeni bir karakter oluşturmak istiyorum.

Codex asks for one natural description. AICE plans the first **non-explicit identity seed** using the best validated capability. The seed can come from Codex built-in image generation or, when installed and smoke-validated, local Qwen text-to-image.

The seed is shown before it becomes identity truth. Only explicit user approval turns it into the golden seed. After approval, either provider may reuse it and local reference expansion can derive additional geometry. Derived images remain candidates until quality-gated.

An explicit adult request cannot be used as a scratch identity bootstrap. AICE first establishes and approves a neutral adult identity seed, then the original explicit request can be retried through the local adult capability. This prevents an explicit scratch request from leaking into cloud generation or the unrelated Qwen bootstrap workflow.

### From existing photos

Say:

> Hazır karakterim var, referansları yükleyeceğim.

Upload as many photos as you want and say `done` when finished. AICE stores the evidence once, builds the Character Brain, and later selects only the small relevant subset for each scene.

Existing characters remain provider-neutral. Old references do not need to be converted into “ComfyUI references.”

## Choosing the image engine

Persistent choices stay simple:

- local ComfyUI
- Codex image generation
- automatic intelligent choice
- ask each time

A one-off request such as “Comfy first, let the other engine help only if needed” becomes a hybrid strategy for that request only.

`auto` is not “always ComfyUI with fallback.” It is a deterministic capability-aware planner:

1. understand the requested operation
2. inspect trusted reference coverage
3. inspect provider capability/readiness
4. choose one primary provider
5. generate once
6. visually validate
7. only if a hard localized problem exists and the plan permits it, allow one targeted second-provider repair

It does not double-generate every request.

## Reference fabric and trust

Every reference records independent concepts:

```text
trust tier:       golden / trusted / candidate / rejected
origin provider:  user / codex_builtin / comfyui / unknown
role/tags:        face_front / full_body / side / detail / ...
lineage:          parent reference IDs
content hash:     SHA-256
```

Candidate/rejected images never condition normal generation and never parent a generated reference. A failed image used for repair is an edit target, not identity truth.

## Local ComfyUI

Local generation is optional and isolated from the lightweight AICE Python environment. The managed runtime lives outside the Git repository.

The tuned 8 GB identity profile uses Qwen-Image-Edit-2509 GGUF Q3_K_M, 8-step Lightning, up to three selected trusted inputs, low-VRAM mode, CPU VAE decode, localhost-only ComfyUI, and pinned runtime/custom-node revisions.

Local first-character creation is an optional capability and downloads its extra Qwen text-to-image weights only when requested.

### Capability-specific validation

Presence of a model file is not enough to advertise a local capability. AICE keeps separate smoke-validation state for:

```text
identity
bootstrap
adult_explicit
```

Changing runtime pins or model inputs invalidates the affected capability until a real local smoke test passes again. This prevents a successful identity smoke from accidentally marking an unrelated optional workflow as ready.

### Local adult profile

The optional local adult profile uses LUSTIFY SDXL v4.0 with IP-Adapter Plus SDXL (ViT-H) identity conditioning from 1–2 golden/trusted references and a versioned `lustify_sdxl_adult` workflow. The 8 GB-oriented defaults stay around 1 MP with `dpmpp_2m` / `karras`, 30 steps, CFG 5, batch 1, and CPU VAE.

Explicit adult synthetic requests route only to this validated local capability; they do not silently downgrade to built-in image generation. If it is missing or has not passed its own smoke test, Codex offers setup/repair or a non-explicit alternative.

The deterministic intent layer recognizes English and Turkish conversational phrasing with accent-insensitive matching. Disallowed categories are rejected before any provider is touched.

For the detailed implementation map, model registry, workflow graph, measured target-machine behavior, and troubleshooting, see [`docs/adult-backend.md`](docs/adult-backend.md).

## Generation lifecycle

```text
Character Brain + request
        ↓
scene/reference selection
        ↓
provider-neutral GenerationRequest
        ↓
capability plan
        ↓
primary provider
        ↓
visual identity/detail validation
        ↓
0 or 1 targeted repair if justified
        ↓
approved history + provider/reproducibility metadata
```

Progress events describe real state (`plan_resolved`, `rendering`, `output_fetching`, etc.). AICE does not invent percentages or ETAs.

## Character Brain

Character Brain is an evidence graph rather than a long prose prompt. Source authority is explicit. Repeated analysis of the same source cannot inflate consensus, near-ties become conflicts instead of guesses, and explicit user locks override ambiguous observations. Only relevant resolved truth is compiled into a bounded generation context.

## Privacy

Never commit `.aice/` character state, reference/generated photos, ComfyUI runtime/venv, model weights, analysis cache, or local generation logs containing private paths/content. The managed ComfyUI server binds to `127.0.0.1`.

## Developer checks

```text
python -m pip install -e .
python -m compileall -q src scripts
python scripts/validate_plugin.py
python -m unittest discover -s tests -v
aice doctor
```

For a machine with local models installed, additionally run:

```text
aice comfy doctor --smoke
```

The smoke result is recorded separately per installed capability. Hosted CI covers Python 3.11/3.12/3.13 on Ubuntu and Windows; large-model/GPU validation remains local because hosted runners do not provide the target GPU/runtime.

## Design principles

1. **AICE owns identity; providers only render.**
2. **Trust is evidence-based, never provider-based.**
3. **Natural language outside, deterministic state/planning inside.**
4. **One good generation beats blind multi-provider fan-out.**
5. **Hybrid means bounded cooperation, not extra compute by default.**
6. **Local capability is advertised only after its own validation.**
7. **Old characters remain usable as the engine evolves.**
8. **Provider/model implementations can change without rewriting Character Brain.**

Current release: **v0.5.1**.
