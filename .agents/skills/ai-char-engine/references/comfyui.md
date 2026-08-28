# Local ComfyUI image backend

Load this only for local setup/execution/recovery. The normal user never operates ComfyUI, chooses nodes, or manages model files.

## Role

ComfyUI is a local pixel worker behind AICE. Character Brain, trust, reference selection and provenance remain provider-neutral. Provider origin records lineage but never grants trust.

Normal strategies:
- `comfyui` — force local; never silently switch if it fails;
- `codex_builtin` — built-in image generation for non-explicit workflows;
- `auto` — capability-aware primary selection with bounded fallback/help where allowed;
- one-shot `hybrid` — best primary plus at most one justified cross-provider stage;
- `ask_each_time` — ask only when both relevant choices are viable.

## Identity stack

The tuned 8 GB identity path uses Qwen-Image-Edit-2509 via ComfyUI-GGUF, Q3_K_M + 8-step Lightning, up to three provider inputs, ~1 MP buckets, batch 1, low-VRAM/VRAM-reserve/CPU-VAE policy, localhost only, and runtime/models outside Git.

It handles normal identity generation, reference expansion and targeted edit/repair from trusted references.

## Optional bootstrap

Local first-character creation is separately optional because it adds substantial weights:

- Qwen-Image text-to-image GGUF Q3_K_M;
- Qwen-Image Lightning 8-step LoRA;
- shared Qwen text encoder + VAE;
- `qwen_text_to_image` workflow;
- no reference required.

Install only when requested/needed, then smoke-validate it. If unavailable, built-in generation remains a valid **non-explicit** first-seed provider.

An explicit scratch request is different: it returns `adult_identity_required`. Establish/approve a neutral adult identity first; never forward the explicit scratch description to built-in generation or Qwen bootstrap.

## Capability validation

v0.5.1 tracks readiness independently:

```text
identity
bootstrap
adult_explicit
```

A model file being present is not enough. The capability must also pass its own current local smoke. Runtime/pin/model changes invalidate affected validation until doctor succeeds again.

Default local identity setup:

```text
aice comfy setup
aice comfy doctor --smoke
```

Optional bootstrap:

```text
aice comfy setup --capabilities bootstrap
aice comfy doctor --smoke
```

Optional adult:

```text
aice comfy setup --capabilities adult_explicit
aice comfy doctor --smoke
```

Setup is idempotent, revision-pinned, disk-aware, resumable, and hash-verified. Installer decisions verify SHA-256 rather than trusting a same-sized cached file.

## Trust / interoperability

```text
user upload ----------------------> golden
Codex/Comfy seed + approval ------> golden
Codex/Comfy derivative -----------> candidate -> quality gate -> trusted/golden
```

Rules:
- provider output never self-promotes;
- candidate/rejected images never condition normal generation;
- generated derivatives require trusted parent IDs;
- cross-provider reuse is allowed only after the same trust gate;
- a repair target is an edit target, not identity truth.

## Execution

Normal internal entry point:

```text
aice generate <character> "<request>" --budget balanced --progress
```

One-shot internal variants include `--backend hybrid`, `--operation reference_expand`, `--operation repair --repair-of <image>`, and `aice seed-generate ... --backend comfyui`. Codex invokes them; do not teach commands to normal users unless they request developer detail.

## Progress / failure semantics

Factual stages include context/plan/backend selection, setup-required, local start, settings, reference upload, workflow submit/render/fetch, complete, recovery/failure, and planner-authorized fallback. No fake percentages or ETAs.

- explicit/saved local choice: failure remains local unless the product contract explicitly allows otherwise;
- normal `auto`/one-shot `hybrid`: one bounded recovery, then only planner-authorized fallback;
- explicit adult: validated local adult capability only; no built-in fallback;
- unset/ask-each-time: ask only if the relevant capability is actually viable.

Never kill unrelated processes, expose the server to LAN/Internet, or commit runtime/model/private state.
