# AI Character Engine

A Codex-native plugin for building one persistent synthetic adult character and generating new photorealistic images of that same character with minimal user effort.

The product is conversational by design: **you do not need to learn commands, prompt engineering, ComfyUI nodes, model settings, or reference-management rules.** Codex asks the next useful question and operates the deterministic character engine behind the scenes.

## What it does

- create a character from scratch or from existing reference photos
- accept any number of user reference images
- build an evidence-grounded Character Brain with source provenance
- surface conflicting permanent details instead of guessing
- let explicit user-confirmed facts outrank ambiguous visual evidence
- maintain golden / trusted / candidate / rejected reference lineage
- lazily expand missing views instead of creating a huge reference pack
- select only the small set of references useful for the current scene
- keep tattoos, marks and other permanent details visibility-aware
- cache unchanged reference analysis by SHA-256
- remember recent pose/framing patterns through tiny fingerprints instead of old images
- choose conversationally between local ComfyUI and Codex built-in image generation
- expose factual generation stages to Codex without fake percentages or noisy logs
- keep generation and repair budgets bounded

## Easiest install

Open or clone this repository in Codex and say:

> Install this plugin and set it up for me.

Repository:

`https://github.com/brutalstein/ai-char-engine`

Codex is instructed to install/update the personal plugin, validate packaging, run diagnostics and tests, and avoid making you type commands unless a real external blocker requires it. Restart or refresh Codex if plugin discovery asks for it.

## Image engines

AI Character Engine supports two pixel backends while keeping the same Character Brain and reference policy.

### Codex image generation

The built-in path requires no OpenAI API key from AICE. It is also used for the very first from-scratch identity seed because the current local workflow is reference/edit-oriented.

### Local ComfyUI

If you have a compatible NVIDIA GPU, say:

> Set up local image generation.

Codex installs a private AICE-managed ComfyUI runtime outside the repository, downloads the validated model stack, and runs a real GPU smoke test. The user never needs to open ComfyUI.

The currently tuned 8 GB RTX 5070 Laptop profile uses Qwen-Image-Edit-2509 GGUF with Q3_K_M, an 8-step Lightning LoRA, native multi-reference identity conditioning, low-VRAM operation and CPU VAE decode. The runtime is bound to `127.0.0.1` only.

### Choosing the backend

If both engines are ready and you have not chosen a preference, Codex asks naturally:

> Both image engines are ready. Do you want local ComfyUI, Codex image generation, or should I choose automatically?

You can reply however you like:

> use comfy locally

> use Codex for this one

> you choose automatically from now on

> ask me every time

A one-off request such as "make this one with ComfyUI" does not silently become a permanent setting. You can change the default later in normal language.

`auto` may fall back from local generation to Codex after one bounded local recovery. If you explicitly choose local ComfyUI, AICE does **not** silently send the job to the other backend when local generation fails; Codex asks first.

## What onboarding feels like

### New character

Say:

> I want to create a new character from scratch.

Codex asks for a natural description, creates one seed image, shows it for approval, builds the Character Brain, and proposes missing body/reference views only when useful.

### Existing character

Say:

> I already have the character. I want to upload references.

Upload as many images as you want. Codex keeps accepting batches until you say `done`, analyzes only visible evidence, caches the work, builds the brain, and asks only about genuine conflicts.

### Generate a photo

Once ready, just describe it:

> old-town cafe, rainy afternoon, candid friend-taken photo

Internally AICE compiles context, selects trusted references, resolves the backend, renders once, validates identity/details, and records the accepted result.

## Generation status

Codex receives coarse factual stages such as:

```text
context_compiled
backend_selected
local_backend_starting
references_uploading
workflow_submitted
rendering
output_fetching
provider_complete
```

For built-in generation it receives `builtin_planned` and invokes `image_gen`. Automatic fallback is explicitly recorded as `fallback_planned`.

These are state events, not made-up progress percentages. Codex can turn them into useful updates such as:

> References are ready; the local model is generating now.

> The image is ready; I'm checking identity and details.

## Architecture

```text
Natural Codex conversation
          |
          v
Interactive guide / state machine
          |
          +-----------------------+
          |                       |
          v                       v
Evidence Character Brain    Trusted reference bank
(provenance + conflicts)    golden / trusted / candidate / rejected
          |                       |
          +-----------+-----------+
                      v
          deterministic context compiler
                      |
             2-3 relevant refs normally
                      |
                      v
             backend preference/router
                  /             \
                 v               v
        Local ComfyUI        Codex image_gen
       (optional, local)       (built-in)
                 \               /
                  +-------------+
                        v
                visual validation
                        |
              <= 1 targeted repair
                        |
                        v
                 accepted image +
             compact generation ledger
```

The standard AICE package stays dependency-light and deterministic. Codex owns semantic conversation and visual judgement; ComfyUI or built-in `image_gen` owns pixel generation.

## Character Brain

The brain is an evidence ledger, not one giant prose prompt.

Conceptually:

```text
identity.hair.color = "jet black"
  source: user-face-front-...
  authority: golden

identity.eyes.color = conflict
  brown <- golden reference A
  hazel <- golden reference B
```

Near-tied evidence becomes an explicit conflict. A direct user lock is authoritative.

Permanent features can include visibility metadata:

```json
{
  "kind": "tattoo",
  "location": "left_wrist",
  "description": "small minimalist crescent",
  "visibility_tags": ["hands", "arms"]
}
```

The tattoo is omitted from active context when the wrist/arm is not expected to be visible.

## Reference trust model

- **golden** — user-supplied or explicitly user-approved source of truth
- **trusted** — generated reference that passed identity/anatomy/stable-trait checks
- **candidate** — generated but not yet trusted
- **rejected** — failed quality gate

Generated refs cannot silently bootstrap trust. They require trusted parents and validation; golden promotion additionally requires explicit user approval.

## Usage budgets

| mode | selected refs | recent approved history | validation | max repair |
|---|---:|---:|---|---:|
| economy | 2 | 4 | critical | 0 |
| balanced | 3 | 8 | light | 1 |
| quality | 4* | 12 | full | 1 |

`balanced` is the default. *A specific image provider may enforce a lower native reference cap; the current Qwen local workflow accepts up to 3.

## Private runtime data

Character state is kept in `.aice/` and ignored by Git. Local ComfyUI/runtime/model files are kept outside the repository under the configured `~/.aice` runtime/model locations.

Never commit either private character state or local model/runtime assets.

## Developer commands

Normal users should not need these; Codex invokes them internally.

```text
aice doctor
aice guide [character]
aice backend status <character>
aice backend set <character> auto|comfyui|codex_builtin|ask_each_time
aice generate <character> "..." --progress
aice begin <name> --origin scratch|references
aice add-ref ...
aice refs-done <character>
aice observe <character> --json ...
aice brain <character>
aice lock-fact <character> <path> --value ...
aice context <character> "..." --compact
aice prompt <character> "..."
aice record ...
aice stats <character>
aice comfy setup
aice comfy doctor --smoke
```

Manual development setup requires Python 3.11+:

```bash
python -m pip install -e .
python scripts/validate_plugin.py
aice doctor
python -m unittest discover -s tests -v
```

## Design principles

1. natural conversation outside, deterministic state inside
2. evidence before assumption
3. conflict instead of confident guessing
4. generated refs never recursively create trust
5. smallest useful context per image
6. unlimited user refs, selective model refs
7. explicit backend choice when it matters; no pointless questions
8. one normal generation and one bounded repair at most
9. cache unchanged visual analysis
10. local runtime is private, localhost-only and optional
11. factual progress state, never fake percentages
12. visual consistency is measured and validated rather than claimed magically

## Status

`v0.3.0` adds a first-class conversational image-backend layer on top of the v0.2 Character Brain: persistent/one-shot backend choice, provider-neutral generation, Codex-visible progress traces, explicit fallback semantics, reference provenance in provider metadata, official Codex skill metadata, repo marketplace packaging, and the validated local ComfyUI workflow.
