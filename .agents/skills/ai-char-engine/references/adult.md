# Explicit adult profile (local LUSTIFY SDXL)

Load this only when a request is explicit adult synthetic content or the user asks to set up the local adult model. The normal user never needs ComfyUI/model/settings details.

## Contract

A dedicated **local** ComfyUI capability renders explicit adult imagery for fully adult synthetic or user-authorized characters. It never uses Codex built-in image generation for the explicit render and never leaves localhost.

- checkpoint: **LUSTIFY! SDXL v4.0**
- identity: **IP-Adapter Plus SDXL (ViT-H)** + CLIP-ViT-H from 1–2 golden/trusted references
- workflow: `lustify_sdxl_adult`
- capability: `adult_explicit`

Character Brain, trust, provenance, selection and validation remain provider-neutral. LUSTIFY output is generated evidence: candidate first, never self-promoted.

## Routing

`aice generate` classifies explicitness deterministically in English/Turkish:

- `normal` / `suggestive` -> ordinary routing;
- `explicit` -> planner `local-adult`, primary ComfyUI, no cross-provider repair;
- `disallowed` -> `refused` before any provider is touched.

Phrases such as “use LUSTIFY”, “yerel +18 model”, “image gen kullanma”, and equivalent English wording can explicitly select the local adult route.

### `local_adult_unavailable`

The adult capability is missing **or has not passed its own current smoke validation**. Offer to set it up/repair it or offer a non-explicit alternative, then stop. Never downgrade the explicit render to built-in generation.

Internal setup path:

```text
aice comfy setup --capabilities adult_explicit
aice comfy doctor --smoke
```

### `adult_identity_required`

The LUSTIFY workflow is reference-driven. If the user asks for explicit content while creating the very first character seed, do not send that explicit scratch request to built-in generation or Qwen bootstrap.

Instead:
1. establish a neutral, non-explicit adult identity seed;
2. show it and get the user's approval so it becomes golden;
3. retry the original explicit request through the validated local adult capability.

## Validation

v0.5.1 validates local capabilities independently:

```text
identity
bootstrap
adult_explicit
```

Model presence alone is not readiness. Adult generation is advertised only after the adult model stack/workflow passes its own real smoke execution. Runtime/model changes invalidate affected smoke state until doctor succeeds again.

## Setup/storage

The adult-only weights are roughly 10.3 GB incremental when the base identity runtime is already installed. On a fresh setup the required identity stack is also included; installer preflight reports actual missing bytes and headroom.

Downloads are resumable and SHA-256 verified. A same-sized corrupt cached model is redownloaded instead of being trusted.

## 8 GB defaults

| knob | default |
|---|---|
| resolution | 832×1216 portrait/full-body; scene-aware square/landscape |
| sampler / scheduler | `dpmpp_2m` / `karras` |
| steps / CFG | 30 / 5.0 |
| batch | 1 |
| IP-Adapter | 0.75 portrait, 0.72 square, 0.55 full-body/wide |
| references | 1–2 golden/trusted |
| runtime | low-VRAM + CPU VAE on the 8 GB profile |

Do not ask the user to tune these in normal conversation.

## Reproducibility

Adult results record explicitness, model/workflow hashes, reference IDs/roles/origins, IP-Adapter/CLIP-Vision metadata, seed/settings, free VRAM at start, and output SHA-256.

## Safety scope

Only fully adult fictional/synthetic or user-authorized adult character workflows. Never work around a `refused` result. Disallowed categories are stopped before provider execution.
