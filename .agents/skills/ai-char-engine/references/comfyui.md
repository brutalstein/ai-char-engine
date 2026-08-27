# Local ComfyUI image backend

Load this only when the user asks to set up local generation, when a generation
should run locally, or when the local backend misbehaves. Normal generations do
not need this file.

## What it is

An optional local image backend. When installed it replaces Codex built-in
`image_gen` for normal generations; when absent or unhealthy, generation
transparently falls back to `image_gen`. The Character Brain, reference
selection, provenance, budgets and repair rules are unchanged — ComfyUI only
turns an already-compiled request into pixels.

Stack (chosen for an 8 GB Blackwell laptop; all Apache-2.0):
- Qwen-Image-Edit-2509, GGUF quant (Q4_K_S default, Q3_K_M tight-VRAM), fused
  8-step Lightning LoRA
- identity = the model's native `TextEncodeQwenImageEditPlus` multi-image input
  (1–3 references), no IP-Adapter / InstantID / PuLID
- one custom node: `ComfyUI-GGUF` (city96)
- runtime + venv + models live in `~/.aice/runtime` (never committed, 127.0.0.1 only)

## Setup (Codex runs this; never ask the user to type it)

```
aice comfy setup            # idempotent: clone + venv + torch(cu130) + node + models
aice comfy doctor --smoke   # real GPU generation; marks the backend validated on success
```

`setup` is safe to re-run — intact files and installed packages are skipped.
If `doctor --smoke` fails, the backend stays unvalidated and `auto` keeps using
`image_gen`; report the one-line error, do not loop.

## Normal generation

Prefer the existing flow, then hand the compiled request to the backend:

```
aice comfy generate <character> "<request>" --budget balanced --backend auto
```

- `auto` picks ComfyUI only when installed, validated, models present, server
  healthy/startable and free VRAM is sufficient; otherwise `codex_builtin`.
- On a `codex_builtin` (or fallback) result, `status` is `planned` and
  `result.effective_settings.prompt` holds the prompt — run built-in `image_gen`
  yourself with the listed references, exactly as before.
- On a `comfyui` result, `output_path` is a finished PNG. Record it through the
  normal `aice record` path; `ledger` carries reproducibility (model, workflow
  hash, seed, effective settings).

The server starts lazily on the first local generation and can be left running;
`aice comfy stop` shuts down the AICE-managed process only.

## Diagnostics

`aice doctor` always shows `ok: true` for the core plugin plus a
`local_image_backend` section: `unavailable` (not installed), `degraded`
(installed but models missing or not validated), `available` (ready).
`aice comfy status` shows the process/pin state; `aice comfy doctor` runs the
strict checks.
