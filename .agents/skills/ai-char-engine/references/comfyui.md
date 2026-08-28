# Local ComfyUI image backend

Load this only for local setup, local-generation execution detail, or recovery. The user should never need to operate ComfyUI directly.

## Role

ComfyUI is an optional local pixel backend behind AI Character Engine. It does not own Character Brain state, reference trust, provenance, prompt policy, or validation. AICE compiles the request first, then hands only selected golden/trusted references to the provider.

The user can choose conversationally between:
- `comfyui` — force local generation; never silently switch to Codex if it fails;
- `codex_builtin` — use Codex built-in `image_gen` and never start ComfyUI;
- `auto` — use validated local generation when viable, with bounded fallback to built-in generation;
- `ask_each_time` — ask only when both engines are actually viable.

## Current validated local stack

The 8 GB RTX 5070 Laptop profile is intentionally conservative because real smoke testing showed that GPU VAE decode could exhaust the card after sampling.

- Qwen-Image-Edit-2509 via `ComfyUI-GGUF`
- Q3_K_M is the 8 GB default; Q4_K_S remains available for larger/tuned profiles
- fused 8-step Lightning LoRA; Euler + simple scheduler; CFG 1.0
- native `TextEncodeQwenImageEditPlus` multi-image identity conditioning, up to 3 selected refs
- ~1 MP scene buckets, batch size 1
- `--lowvram`, VRAM reserve, PyTorch cross-attention and CPU VAE decode on the 8 GB profile
- one custom node family: `ComfyUI-GGUF`
- runtime, venv, models and logs live under `~/.aice/runtime` / configured local model paths, never in Git
- server is localhost-only (`127.0.0.1`)

The initial no-reference character seed still uses Codex built-in `image_gen`: the local workflow is an edit/reference workflow and must not be advertised as a validated text-to-image seed generator.

## Setup and validation

Codex runs these internally; never make the normal user copy them:

```text
aice comfy setup
aice comfy doctor --smoke
```

Setup is idempotent: intact runtime/model assets are reused. The smoke test performs a real GPU generation and only then marks local generation validated. If the smoke test fails, local generation stays unavailable/degraded and `auto` does not pretend it is ready.

Do not repeatedly rerun setup or smoke tests during ordinary generation. Use them only for initial setup or real recovery.

## Normal generation

The main skill uses the provider-neutral command:

```text
aice generate <character> "<request>" --budget balanced --progress
```

Use `--backend comfyui|codex_builtin|auto` only for a one-shot explicit user choice. Saved defaults are managed through the hidden `aice backend` commands.

ComfyUI generation stages are factual coarse events, not progress percentages:

```text
context_compiled
backend_selected
local_backend_starting
settings_resolved
references_uploading
workflow_preparing
workflow_submitted
rendering
output_fetching
provider_complete
```

A bounded recovery may emit `recovering`; a real failure emits `provider_failed`. Automatic mode may emit `fallback_planned`, after which the result becomes a built-in `image_gen` plan.

Codex should translate only useful events into natural language. Do not dump raw events unless debugging is requested and do not invent an ETA.

## Fallback semantics

- `auto`: ComfyUI runtime failure -> one safe provider recovery -> built-in plan if local still fails.
- explicit/saved `comfyui`: local failure stays a failure; ask the user before using built-in generation.
- explicit/saved `codex_builtin`: no ComfyUI startup.
- unset/`ask_each_time` with both engines ready: ask before spending compute.
- unset/`ask_each_time` with only built-in viable: do not ask a pointless question.

## Diagnostics

`aice doctor` keeps core plugin health independent from optional local generation and reports `local_image_backend` as unavailable/degraded/available.

Use internally when needed:

```text
aice comfy status
aice comfy doctor
aice comfy start
aice comfy stop
```

Never kill processes the AICE runtime did not start. Never expose ComfyUI to LAN/Internet by default. Never commit runtime/model/generated/private state.
