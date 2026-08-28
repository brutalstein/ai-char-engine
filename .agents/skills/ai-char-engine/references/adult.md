# Explicit adult profile (local LUSTIFY SDXL)

Load this only when a request is explicit adult synthetic content or the user asks to
set up the local adult model. The normal user never sees ComfyUI, models, or settings.

## What this is

A dedicated **local** ComfyUI profile for explicit adult imagery of a fully adult,
synthetic or user-authorized character. It never uses Codex built-in image generation
and never leaves `127.0.0.1`.

- checkpoint: **LUSTIFY! SDXL v4.0** (`lustifySDXLNSFWSFW_v40.safetensors`), SDXL, CreativeML-OpenRAIL-M
- identity: **IP-Adapter Plus SDXL (ViT-H)** + CLIP-ViT-H, driven by the character's
  golden/trusted references (1–2 images; more dilutes the identity embedding)
- workflow profile: `lustify_sdxl_adult` (versioned, under `src/aice/workflows/`)
- capability key: `adult_explicit`

Character Brain, trust tiers, provenance, selection and validation are unchanged and
provider-neutral. A LUSTIFY output is a normal generated result: it enters as
`candidate` and only a separate quality gate / user approval can promote it. LUSTIFY
never trusts or promotes its own output.

## Routing

`aice generate` runs a compact deterministic intent classifier and sets the request
explicitness. You route on that result — do not pre-judge:

- `normal` / `suggestive` → ordinary routing (see `comfyui.md`).
- `explicit` → planner strategy `local-adult`, primary `comfyui`, no cross-provider
  repair, cross-provider **reference reuse allowed** (a trusted ref made by Codex or
  the user still conditions LUSTIFY).
- `disallowed` → the orchestrator returns status `refused` before any provider is
  touched. Relay the refusal text; never retry or reword.

Phrases like "use the local adult model" / "not the built-in generator" also force the
local profile even when the wording itself is not explicit.

### If the profile is not installed

Status `local_adult_unavailable` (never a downgrade to cloud). The handoff carries:

```text
aice comfy setup --capabilities adult_explicit
aice comfy doctor --smoke
```

Tell the user the local adult backend is not ready, offer to set it up, or offer a
non-explicit version of the image with the standard profile. Then stop.

## Safety scope (do not weaken)

Only for fully adult fictional/synthetic characters, or user-owned/authorized adult
character workflows already supported by the character system. The classifier refuses,
and you must never work around: minors or young-looking subjects, incest/family sexual
context, non-consent, sexual violence, real-person sexual deepfakes, hidden-camera or
voyeuristic sexual content, or otherwise illegal sexual content.

## Setup

```text
aice comfy setup --capabilities adult_explicit
aice comfy doctor --smoke
```

Downloads (~10.3 GB total, one-time, resumable, hash-verified, outside Git under
`~/.aice/runtime`): LUSTIFY SDXL v4 checkpoint, IP-Adapter Plus SDXL weights,
CLIP-ViT-H image encoder, and the pinned `ComfyUI_IPAdapter_plus` custom node. Setup is
idempotent — intact files are reused. Disk preflight includes these before downloading.

## 8 GB hardware fit (RTX 5070 Laptop, decided for the user)

One fp16 checkpoint, no quant tiers. Identity comes from IP-Adapter, so the same
process-global 8 GB server flags as the Qwen path apply (`--lowvram`,
`--reserve-vram 0.9`, `--cpu-vae`). Priorities: identity > photorealism > reliability > speed.

| knob | default | why |
|---|---|---|
| resolution | 832×1216 portrait (square/landscape by scene), ≤1 MP | SDXL native bucket, no tiling on 8 GB |
| sampler / scheduler | `dpmpp_2m` / `karras` | most reliable SDXL photoreal 2nd-order combo |
| steps / CFG | 30 / 5.0 | mid of LUSTIFY's 3–7 band; avoids plastic skin |
| batch | 1 | 8 GB |
| IP-Adapter weight | 0.75 portrait, 0.72 square, 0.55 full-body/wide | tighter face lock on portraits; body/wardrobe freedom on full-body |
| references | 1–2 golden/trusted; a lone ref is duplicated for the 2-input batch | more dilutes identity |
| negative baseline | non-photographic + gross-anatomy + youthful-appearance terms | added automatically; user negative is appended |

Never ask the user to choose these.

## Reproducibility

Each adult result records: `explicit`, model file + sha256, workflow name + hash,
reference ids/roles/origins, `identity_method`, IP-Adapter file + sha256 + weight,
CLIP-Vision file, resolution, seed, free VRAM at start.
