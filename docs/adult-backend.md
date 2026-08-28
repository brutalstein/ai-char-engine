# Local adult backend (LUSTIFY SDXL) — developer reference

This is the engineering map for the optional local adult path in **AI Character Engine v0.5.1**. Read `AGENTS.md` and `.agents/skills/ai-char-engine/SKILL.md` first for the product contract.

## 1. Architectural invariant

The adult model is a provider capability, not a separate character system.

```text
Character Brain
      ↓
trusted reference fabric
      ↓
intent + capability planner
      ↓
local adult ComfyUI profile
      ↓
GenerationResult
```

Character truth remains provider-neutral. LUSTIFY never owns identity and never promotes its own output. Generated results enter as candidates and require the same identity/anatomy/stable-traits gate as any other generated reference.

## 2. Request lifecycle

`aice generate` calls `providers.orchestrator.plan_and_generate()`:

1. `intent.classify_explicitness(text)` returns `normal`, `suggestive`, `explicit`, or `disallowed`.
2. `disallowed` returns before Character Brain compilation or provider access.
3. Normal/suggestive requests keep ordinary routing.
4. Explicit adult synthetic requests compile their normal trusted Character Brain context but force planner strategy `local-adult`.
5. Only the local ComfyUI adult capability may render that request; cross-provider repair is disabled for the explicit path.
6. If the adult capability is missing or has not passed its own smoke test, the result is `local_adult_unavailable`; there is no silent cloud downgrade.

The planner and orchestrator both preserve the no-cloud fallback rule. Keep both guards.

### Explicit scratch identity

The adult workflow is reference-driven. An explicit request cannot be used as the first scratch identity seed. `plan_seed_generation()` returns `adult_identity_required` and asks Codex to establish/approve a non-explicit adult identity seed first. The original explicit request can then be retried locally against that trusted identity.

This is intentional defense-in-depth: an explicit scratch description must never fall through to built-in image generation or the unrelated Qwen text-to-image bootstrap.

## 3. Intent classification

`src/aice/intent.py` is deliberately compact and deterministic rather than a second NLP system.

It recognizes English and Turkish conversational phrases. Matching is case/accent-insensitive (including Turkish dotted/dotless-i normalization), so e.g. `çıplak`, `ciplak`, `15 yaşında`, and their English equivalents reach the same deterministic routing layer.

Decision order:

1. disallowed categories
2. explicit adult
3. suggestive
4. normal

`wants_local_adult` is independent and recognizes phrases such as “use LUSTIFY”, “yerel +18 model”, or “image gen kullanma”. The orchestrator treats this as a local-adult routing request even when the rest of the prompt is not itself explicit.

When extending vocabularies, add regression cases to `tests/test_adult_backend.py` or `tests/test_orchestrator.py` and keep `python -m aice.intent` passing.

## 4. Capability-specific validation

v0.5.1 replaces the old single global ComfyUI validation bit with a validation ledger:

```text
validated_capabilities:
  identity:       {ok, validated_at, source, report}
  bootstrap:      {ok, validated_at, source, report}
  adult_explicit: {ok, validated_at, source, report}
```

`validated` remains only as a backward-compatible mirror of **identity** validation.

A local capability is ready only when all of these are true:

- managed ComfyUI runtime exists;
- target hardware profile is usable;
- its declared model bundle is present;
- required workflow/custom nodes are present;
- **that capability itself has passed its smoke test**.

This prevents a successful Qwen identity smoke from accidentally advertising LUSTIFY or bootstrap as ready.

`aice comfy doctor --smoke` now records separate real executions for installed capability stacks:

- identity — reference-driven Qwen edit workflow;
- bootstrap — no-reference Qwen T2I workflow;
- adult_explicit — LUSTIFY + IP-Adapter workflow.

Optional capabilities that are not installed remain unvalidated rather than inheriting another capability's state.

### Migration

Config schema is v2. A legacy v1 `validated=true` migrates only to identity validation. If an old smoke record already contains a successful adult smoke result, that adult evidence is preserved. Bootstrap is never inferred from a global legacy bit.

## 5. Model registry

`src/aice/comfy/registry.json` declares:

```text
adult_explicit:
  lustify_sdxl_v4
  ip_adapter_plus_sdxl_vith
  clip_vision_vith
```

LUSTIFY is stored as an SDXL checkpoint; identity conditioning uses IP-Adapter Plus SDXL (ViT-H) and CLIP-ViT-H. Model files live outside Git under the AICE-managed runtime/model directory.

Model metadata includes exact byte size and SHA-256. Setup is resumable and idempotent.

### Integrity guarantee

Installer/setup paths verify the pinned SHA-256 before declaring an existing model file intact. A same-sized corrupted file is not trusted. Fast runtime presence probes may use size checks, but installation and redownload decisions use exact hashes.

## 6. Installation and disk behavior

Adult setup is requested through the existing capability mechanism:

```text
aice comfy setup --capabilities adult_explicit
aice comfy doctor --smoke
```

The adult-only model payload is roughly **10.3 GB**. That number is the incremental adult capability size when the base identity runtime/models already exist. On a fresh machine, setup also includes the required identity stack and runtime dependencies; the installer preflight computes actual missing bytes and required temporary headroom before downloading.

Downloads are `.part`-based, resumable, hash-verified, and outside the repository.

## 7. Workflow graph

Versioned assets:

```text
src/aice/workflows/lustify_sdxl_adult/profile.json
src/aice/workflows/lustify_sdxl_adult/workflow_api.json
```

Core graph:

```text
CheckpointLoaderSimple (LUSTIFY SDXL)
      ├─ CLIPTextEncode positive
      ├─ CLIPTextEncode negative
      └─ model
           ↓
IPAdapterAdvanced
  ↑ IPAdapterModelLoader
  ↑ CLIPVisionLoader
  ↑ ImageBatch(reference 1, reference 2)
           ↓
KSampler
           ↓
VAEDecode
           ↓
SaveImage
```

Calling code patches semantic slots through `WorkflowAdapter`; it does not depend on node IDs.

`ImageBatch` expects two inputs. When AICE selects only one trusted identity reference, the provider duplicates that reference for the two workflow inputs. This duplicates the embedding input, not character evidence or trust.

## 8. 8 GB target profile

The committed defaults prioritize identity consistency, photorealism, reliability, then speed:

| setting | default |
|---|---|
| checkpoint | LUSTIFY SDXL v4 |
| portrait / full body | 832×1216 |
| square | 1024×1024 |
| sampler | `dpmpp_2m` |
| scheduler | `karras` |
| steps | 30 |
| CFG | 5.0 |
| batch | 1 |
| references | 1–2 golden/trusted |
| IP-Adapter weight | 0.75 portrait, 0.72 square, 0.55 full-body/wide |
| server policy on 8 GB | `--lowvram`, PyTorch cross-attention, reserve VRAM, CPU VAE |

The server process is shared across Comfy capabilities, so server flags are process-global. A future workflow-specific process pool would be a separate architectural feature; do not fake per-workflow flags in metadata today.

## 9. Target-machine smoke evidence

The existing developer reference recorded real target-machine smoke measurements after the v0.5 work:

- identity smoke: approximately **183 s** at roughly 864×1184;
- adult smoke: approximately **63 s** at 832×1216.

These numbers are historical measurements, not performance guarantees. Hardware load, driver/runtime changes, thermal state, and future model pins can change them. `doctor --smoke` is the source of truth for the current machine and pins.

The adult smoke deliberately uses a non-explicit adult portrait prompt: its purpose is to validate graph compatibility, model loading, IP-Adapter wiring, VRAM fit, and output production—not to benchmark content semantics.

## 10. Reference and provenance contract

Only golden/trusted references may condition normal generation. A trusted reference created by Codex can condition LUSTIFY; a trusted reference created locally can condition another provider. Provider origin is recorded but does not increase trust.

Adult reproducibility metadata includes:

- explicitness level;
- model file + SHA-256;
- workflow name/hash/version;
- reference IDs/roles/origins;
- IP-Adapter model/hash/weight;
- CLIP-Vision file;
- seed, resolution, free VRAM at start;
- output SHA-256.

A failed image used as a repair target is never identity evidence by virtue of being consumed by a workflow.

## 11. Failure behavior

Expected user-facing states:

| status | meaning |
|---|---|
| `ok` | render completed |
| `needs_backend_choice` | normal request needs one conversational provider choice |
| `needs_backend_setup` | requested normal/bootstrap local capability is unavailable |
| `local_adult_unavailable` | explicit local capability is missing/unvalidated |
| `adult_identity_required` | explicit scratch request needs a trusted neutral identity seed first |
| `refused` | disallowed category; no provider touched |
| `failed` | provider execution failed after bounded recovery |

Normal `auto` may plan a fallback where permitted. Explicit adult generation never silently falls back to built-in image generation.

## 12. Tests and CI

Hosted CI runs package install, compile, plugin validation, unit tests, doctor, and interactive guide smoke on:

```text
Ubuntu: Python 3.11 / 3.12 / 3.13
Windows: Python 3.11 / 3.12 / 3.13
```

Important regression coverage includes:

- trust/provenance invariants;
- candidate leakage prevention;
- capability-aware planning;
- explicit local-only routing;
- explicit scratch identity guard;
- Turkish/English intent behavior;
- model download resume + same-size corruption detection;
- per-capability validation migration/invalidation;
- pinned ComfyUI/custom-node checkout repair;
- workflow slot rendering and missing-node validation;
- plugin install/update/version consistency.

Large-model GPU smoke is local/opt-in because hosted runners do not provide the target GPU/model files.

## 13. Remaining engineering limitations

These are real trade-offs, not hidden blockers:

1. The adult checkpoint currently has one configured Hugging Face download mirror plus canonical source metadata. A mirror outage can block first-time setup until the registry is updated.
2. CPU VAE improves 8 GB reliability at a latency cost.
3. ComfyUI server arguments are process-global across workflows.
4. The built-in smoke validates execution and compatibility, not perceptual identity quality. A separate repeatable visual benchmark suite is still the right tool for measuring identity drift/anatomy/repair rate across many scenes.

Do not claim a local capability is production-ready solely because files exist or hosted CI is green; its own current-machine smoke validation remains authoritative.
