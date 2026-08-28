# AI Character Engine

**A Codex-native persistent visual-character engine.** Build one synthetic adult character once, then generate new photorealistic images of that same identity through Codex image generation, local ComfyUI, or a capability-aware combination of both.

The product is conversational by design. The user does **not** need to learn commands, prompting tricks, ComfyUI nodes, checkpoints, samplers, CUDA settings, reference scoring, or lineage rules.

## What v0.4 changes

AI Character Engine no longer treats image backends as isolated worlds.

A character belongs to **AICE**, not to a provider:

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
 ├─ bounded validation / repair policy
 └─ reproducibility ledger
        ↓
   ┌───────────────┬────────────────────┐
   │               │                    │
ComfyUI local   Codex image_gen   optional one-stage handoff
   └───────────────┴────────────────────┘
```

A golden/trusted reference created by one engine can be used by the other. **Provider origin is provenance, not trust.** Generated derivatives never promote themselves: they enter as candidates and must pass the same identity/anatomy/stable-traits quality gate.

## Core capabilities

- create a character from scratch or ingest existing reference photos
- accept unlimited user references
- persistent evidence-grounded Character Brain
- source provenance, conflict surfacing and explicit user locks
- golden / trusted / candidate / rejected lineage
- SHA-256 analysis caching and deterministic reference selection
- visibility-aware permanent details such as tattoos/marks/accessories
- recent-pose anti-repetition without resending old generations
- provider-neutral trusted references usable by both image engines
- local ComfyUI identity generation and optional no-reference character bootstrap
- optional local-only explicit-adult profile (LUSTIFY SDXL v4 + IP-Adapter identity); explicit adult content never uses cloud generation
- Codex built-in image generation without an AICE OpenAI API key
- automatic capability-aware provider planning
- explicit one-shot hybrid cooperation when requested
- bounded cross-provider repair/reference expansion
- factual progress events rather than fake percentages
- pinned/reproducible local runtime and model metadata
- private local `.aice` state and local ComfyUI runtime

## Easiest install or update

Open/clone this repository in Codex and simply say:

> Install this plugin and make it ready for me.

Later, to refresh it:

> Bu repoyu güncel plugin olarak güncelle.

Codex is instructed to do the installation/update, package registration, validation, doctor checks and tests itself. The `--latest` refresh path uses a clean shallow checkout of remote `main`, so updating the installed plugin does not rewrite an unrelated dirty working tree.

Repository:

`https://github.com/brutalstein/ai-char-engine`

## Creating a character

### From scratch

Say:

> Yeni bir karakter oluşturmak istiyorum.

Codex asks for a natural description. AICE then plans the first identity seed using the best available capability.

The first seed can come from:
- **Codex built-in image generation**, always available through the Codex host; or
- **local ComfyUI**, when the optional local text-to-image bootstrap capability is installed and ready.

The seed is shown before it becomes identity truth. Only explicit user approval turns it into the golden seed.

After approval, either engine can reuse that same seed. If useful, local ComfyUI may derive additional views; derived images remain candidates until quality-gated.

### From existing photos

Say:

> Hazır karakterim var, referansları yükleyeceğim.

Upload as many photos as you want and say `done` when finished. AICE stores the trusted evidence once, builds the Character Brain, and later selects only the small relevant subset for each scene.

Existing v0.2/v0.3 characters remain usable. Old references do not need to be “converted to ComfyUI references”; the reference fabric is provider-neutral.

## Choosing the image engine

When both normal image engines are available and no preference is settled, Codex can ask naturally:

> Both image engines are ready. Do you want local ComfyUI, Codex image generation, or should I choose and combine them intelligently when useful?

Natural replies work:

> use Comfy locally

> use Codex for this one

> you choose from now on

> ask me every time

> Comfy first, but let the other one help if something needs fixing

Persistent choices are intentionally simple: local, built-in, automatic, or ask each time. A one-off “use both if useful” becomes a **hybrid strategy for that request only**.

### What `auto` means

`auto` is not “always ComfyUI with a fallback”. It is a deterministic capability-aware planner:

1. understand the requested operation
2. inspect trusted reference coverage
3. inspect local runtime/model capability
4. select one primary provider
5. generate once
6. visually validate
7. only if a hard/localized problem exists and the plan permits it, use one targeted second-provider repair

It does **not** double-generate every request.

## Cross-provider reference fabric

Every reference records independent concepts:

```text
trust tier:       golden / trusted / candidate / rejected
origin provider:  user / codex_builtin / comfyui / unknown
role/tags:        face_front / full_body / side / detail / ...
lineage:          parent reference IDs
content hash:     SHA-256
```

Examples:

```text
user photo ------------------------------> golden, origin=user
Codex seed + explicit user approval ------> golden, origin=codex_builtin
Comfy seed + explicit user approval ------> golden, origin=comfyui
Comfy derivative from golden seed --------> candidate
Codex derivative from trusted body anchor -> candidate
candidate + all quality checks pass ------> trusted
```

Once trusted, its original provider no longer limits where it can be used.

This blocks recursive drift while still allowing the two engines to cooperate.

## Local ComfyUI

Local generation is optional and isolated from the lightweight AICE Python environment.

The current tuned 8 GB RTX 5070 Laptop identity profile uses:
- Qwen-Image-Edit-2509 GGUF Q3_K_M
- 8-step Lightning
- up to three selected inputs
- low-VRAM policy
- CPU VAE decode on the 8 GB profile
- localhost-only ComfyUI
- one pinned custom-node family: ComfyUI-GGUF

For users who explicitly want **local creation of the very first character**, v0.4 adds an optional Qwen-Image text-to-image GGUF bootstrap workflow. Its extra weights are not downloaded during ordinary local identity setup.

### Local adult profile

v0.5 adds an optional, local-only profile for explicit adult imagery of a fully adult synthetic or user-authorized character:

- **LUSTIFY! SDXL v4.0** checkpoint with **IP-Adapter Plus SDXL (ViT-H)** identity from the character's own golden/trusted references
- versioned `lustify_sdxl_adult` workflow, tuned for 8 GB (832×1216, `dpmpp_2m`/`karras`, 30 steps, CFG 5.0, batch 1, CPU VAE)
- installed only on request: `aice comfy setup --capabilities adult_explicit` (~10.3 GB, outside Git)

Explicit adult requests are routed here automatically and **never** to cloud image generation. If the profile is not installed, Codex says so and offers setup or a non-explicit alternative — it does not silently downgrade. Requests involving minors, incest, non-consent, sexual violence, real-person deepfakes, or hidden-camera scenarios are refused. Generated adult images follow the same trust rules as any other output — nothing is auto-promoted.

Codex handles setup internally. The normal user never opens the ComfyUI browser UI.

## Generation lifecycle

A normal request such as:

> Milano'da yağmurlu bir akşam kafeden çıkarken arkadaşının çektiği doğal fotoğraf.

becomes internally:

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
approved history + reproducibility metadata
```

Progress events describe real state (`plan_resolved`, `rendering`, `output_fetching`, etc.). AICE does not invent percentages or ETAs.

## Targeted repair

A failed generated image may be supplied as an **edit target** while golden/trusted references remain the identity anchors. The failed image does not become trusted just because a repair workflow consumed it.

This enables workflows such as:

```text
ComfyUI primary image
        ↓
identity passes, localized hand/detail failure
        ↓
Codex targeted edit (if planner allowed it)
```

or the reverse when the local provider is the better repair path.

## Character Brain

Character Brain is an evidence graph rather than a long prose prompt.

Source authority is explicit. Repeated analysis of the same source cannot inflate consensus, near-ties become conflicts instead of guesses, and explicit user locks override ambiguous observations. Only relevant resolved truth is compiled into a bounded generation context.

## Privacy

Never commit:
- `.aice/` character state
- reference photos
- generated photos
- ComfyUI runtime/venv
- model weights
- analysis cache
- local generation logs containing private paths/content

The local ComfyUI server binds to `127.0.0.1` by default.

## Developer checks

Normal users do not need these, but the repository CI validates the same core paths Codex relies on:

```text
python -m pip install -e .
python -m compileall -q src scripts
python scripts/validate_plugin.py
python -m unittest discover -s tests -v
aice doctor
```

CI covers Python 3.11/3.12/3.13 on Ubuntu and Windows. GPU/large-model smoke tests remain local/opt-in because hosted CI does not provide the target RTX environment.

## Design principles

1. **AICE owns identity; providers only render.**
2. **Trust is evidence-based, never provider-based.**
3. **Natural language outside, deterministic state/planning inside.**
4. **One good generation beats blind multi-provider fan-out.**
5. **Hybrid means bounded cooperation, not extra compute by default.**
6. **Local capability is advertised only when actually present.**
7. **Old characters remain usable as the engine evolves.**
8. **Provider/model implementations can change without rewriting Character Brain.**

Current release: **v0.4.0**.
