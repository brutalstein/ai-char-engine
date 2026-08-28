# Local ComfyUI image backend

Load this only for local setup/execution/recovery. The normal user never operates ComfyUI, chooses nodes, or manages model files.

## Role

ComfyUI is a local pixel worker behind AICE. Character Brain, trust, reference selection, provenance and validation remain provider-neutral. A trusted reference may have originated from the user, Codex built-in generation, or ComfyUI; origin records lineage but never grants trust.

Normal strategies:
- `comfyui` — force local for this request/default; never silently switch if it fails;
- `codex_builtin` — built-in `image_gen`; never start ComfyUI;
- `auto` — capability-aware primary selection with bounded fallback/optional cross-provider assistance;
- one-shot `hybrid` — explicitly allow the planner to use the best primary plus at most one justified cross-provider stage;
- `ask_each_time` — ask only when both relevant choices are viable.

## Identity/reference stack

The tuned 8 GB RTX 5070 Laptop identity path remains conservative:
- Qwen-Image-Edit-2509 via `ComfyUI-GGUF`;
- Q3_K_M default + 8-step Lightning;
- native multi-image edit conditioning, up to 3 provider inputs;
- ~1 MP scene buckets, batch 1;
- low-VRAM / VRAM reserve / CPU VAE decode policy on 8 GB;
- localhost `127.0.0.1` only;
- runtime/models outside Git under AICE local runtime paths.

This path handles normal identity generation, reference expansion and targeted edit/repair from trusted references.

## Optional local character bootstrap

v0.4 can also create the **first no-reference synthetic identity locally** when the user wants that capability. It is intentionally optional because it adds substantial disk usage.

Bootstrap stack:
- Qwen-Image text-to-image GGUF `qwen-image-Q3_K_M.gguf`;
- Qwen-Image Lightning 8-step LoRA;
- shared Qwen 2.5 VL text encoder + Qwen Image VAE;
- versioned `qwen_text_to_image` API workflow;
- no reference required.

Codex installs it internally only when requested/needed:

```text
aice comfy setup --capabilities bootstrap
aice comfy doctor --smoke
```

The bootstrap models are not part of the default required download. Do not claim a newer model family is locally supported merely because it exists upstream; only advertise workflows actually present, pinned and runnable by this plugin.

If local bootstrap is unavailable, built-in `image_gen` remains a valid first-seed provider. After the user approves that seed, ComfyUI may use it as a golden identity reference and derive missing views. The inverse is also true: a Comfy-created approved seed may later be used by built-in generation.

## Trust / interoperability

Provider origin and trust are separate axes:

```text
user upload ----------------------> golden
Codex/Comfy first seed + approval -> golden
Codex/Comfy derived output --------> candidate -> quality gate -> trusted/golden
```

Rules:
- provider output never self-promotes;
- candidate/rejected images never condition normal generation;
- generated derivatives require trusted parent IDs;
- cross-provider reuse is allowed only after the same trust gate;
- a repair target is an edit target, not automatically an identity reference.

## Setup and validation

Default local identity setup:

```text
aice comfy setup
aice comfy doctor --smoke
```

Optional bootstrap download:

```text
aice comfy setup --capabilities bootstrap
aice comfy doctor --smoke
```

Setup is idempotent, revision-pinned and disk-aware. Intact weights are reused. Optional capability downloads are included in disk preflight rather than hidden behind the base install estimate.

A failed smoke keeps automatic local routing degraded. Do not repeatedly rerun setup/smoke during ordinary requests.

## Execution

Normal provider-neutral command:

```text
aice generate <character> "<request>" --budget balanced --progress
```

Useful one-shot variants:

```text
aice generate <character> "<request>" --backend hybrid --progress
aice generate <character> "<reference view>" --operation reference_expand --progress
aice generate <character> "<targeted correction>" --operation repair --repair-of <image> --progress
aice seed-generate <character> "<description>" --backend comfyui --progress
```

Codex invokes these; never teach them to normal users unless they request developer detail.

## Generation trace

Factual stages may include:
`seed_contract_compiled`, `context_compiled`, `plan_resolved`, `backend_selected`, `backend_setup_required`, `local_backend_starting`, `settings_resolved`, `references_uploading`, `workflow_preparing`, `workflow_submitted`, `rendering`, `output_fetching`, `provider_complete`, `recovering`, `provider_failed`, `fallback_planned`.

No fake percentages or ETAs.

## Failure semantics

- explicit/saved `comfyui`: failure remains local; ask before another provider;
- `auto`/one-shot `hybrid`: one bounded local recovery, then planner-authorized fallback if needed;
- built-in explicit: do not start ComfyUI;
- unset/ask-each-time: ask only if the relevant local capability is actually viable.

Never kill unrelated processes, expose the server to LAN/Internet, or commit runtime/model/private state.
