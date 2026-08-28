# Local explicit-adult backend (LUSTIFY SDXL) — developer reference

Everything you need to keep working on the adult image path added in **v0.5.0**
(PRs #5 and #6). Read `AGENTS.md` and `.agents/skills/ai-char-engine/SKILL.md`
first for the product contract; this file is the engineering map.

---

## 1. What v0.5.0 added

A dedicated **local-only** ComfyUI profile that generates explicit adult images of
a fully adult synthetic / user-authorized character, using **LUSTIFY! SDXL v4** for
the scene and **IP-Adapter Plus SDXL (ViT-H)** for identity from the character's own
trusted references. Explicit adult requests are routed here and **never** to Codex
built-in cloud generation.

It is a *provider/backend extension only*. Character Brain, trust tiers, provenance,
reference selection, hybrid planning and the conversational UX are unchanged and
stay provider-neutral. A LUSTIFY output is an ordinary generated result — it enters
as `candidate` and is never auto-promoted.

### Files

| Area | File | Change |
|---|---|---|
| Intent | `src/aice/intent.py` | **new** — deterministic explicitness classifier |
| Registry | `src/aice/comfy/registry.json` | `+capability_models.adult_explicit`, 3 models, `custom_nodes[1]` (IPAdapter_plus), `model_profiles.lustify_sdxl_v4` |
| Models | `src/aice/comfy/models.py` | `+model_profiles()`, `+model_profile_state()` |
| Policy | `src/aice/comfy/policy.py` | `+SDXL_*` constants, `+adult_ipadapter_weight()`, `+resolve_adult_settings()` |
| Workflow | `src/aice/workflows/lustify_sdxl_adult/` | **new** — `workflow_api.json` + `profile.json` |
| Adapter | `src/aice/comfy/workflow.py` | `render()` gains `ipadapter_weight/ipadapter_file/clip_vision_file` kwargs |
| Provider | `src/aice/providers/comfyui.py` | `+adult_available()`, `+_adult_node_present()`, adult branch in `_workflow_and_model()` / `_generate_once()` |
| Base | `src/aice/providers/base.py` | `GenerationRequest.explicit`, `ProviderCapabilities.adult_explicit_generation`, `EffectiveSettings.ipadapter_weight`, `VALID_EXPLICITNESS` |
| Planner | `src/aice/providers/planner.py` | `+local-adult` strategy branch |
| Orchestrator | `src/aice/providers/orchestrator.py` | intent classification, `_refused_result()`, `local_adult_unavailable` |
| Installer | `src/aice/comfy/installer.py` | ipadapter/clip_vision extra-model paths; `_ensure_pinned_repo` worktree fix (#6) |
| CLI ops | `src/aice/comfy/cli_ops.py` | adult capability in `backend_health`/`doctor`; `_adult_smoke()` |
| CLI | `src/aice/cli.py` | `refused` / `local_adult_unavailable` UX flags in `_generation_payload` |
| Docs | `SKILL.md`, `AGENTS.md`, `README.md`, `.agents/skills/ai-char-engine/references/adult.md` | routing contract + cold-path reference |
| Version | `__init__.py`, `pyproject.toml`, `.codex-plugin/plugin.json` | `0.5.0` + keyword + default prompt |

---

## 2. Where it sits in the architecture

```
user text (Codex)
   |
   v
aice generate <char> "<text>" --progress          cli.py
   |
   v
orchestrator.plan_and_generate()                  providers/orchestrator.py
   |  1. intent.classify_explicitness(text)  ----> normal | suggestive | explicit | disallowed
   |  2. disallowed  -> GenerationResult(status="refused")           [STOP, no provider]
   |  3. build_context()  (Character Brain, reference selection)
   |  4. _request_from_context(explicit=<level>) -> GenerationRequest
   |  5. explicit -> mode="comfyui"  (forced, bypasses backend dialog)
   |
   v
orchestrator._execute()
   |  build_plan("comfyui", req, ...)              providers/planner.py
   |     explicit -> strategy "local-adult", primary "comfyui",
   |               allow_cross_provider_repair=False
   |  provider = ComfyUIProvider (from ux.safe_comfy_probe)
   |  if not provider.adult_available()[0]:
   |       -> GenerationResult(status="local_adult_unavailable", handoff=...)   [STOP, no cloud]
   |  else provider.generate(req)
   |
   v
ComfyUIProvider._generate_once()                  providers/comfyui.py
   |  workflow = WorkflowAdapter("lustify_sdxl_adult")
   |  settings = policy.resolve_adult_settings(hw, aspect, scene_tags)
   |  negative = policy.SDXL_NEGATIVE_BASELINE + user negative
   |  refs     = req.capped_reference_inputs(ADULT_MAX_REFERENCES=2)  (golden/trusted only)
   |  upload refs -> ComfyUI; if 1 ref, duplicate it (ImageBatch needs 2)
   |  graph = workflow.render(... ipadapter_weight, ipadapter_file, clip_vision_file ...)
   |  workflow.validate(client.object_info_keys())
   |  submit -> wait -> fetch image
   |
   v
GenerationResult(status="ok", output_path=<png>, reproducibility={... adult metadata})
```

The **planner never downgrades** an explicit request and the **orchestrator fallback
guard** (`_execute`, the `result.status == "failed"` block) is explicitly gated on
`not explicit_adult`. Two independent locks; keep both.

---

## 3. Request lifecycle — inputs and outputs

### Input: `GenerationRequest` (providers/base.py)

Built by `orchestrator._request_from_context()`. Adult-relevant fields:

| field | source | meaning |
|---|---|---|
| `explicit` | `intent.classify_explicitness()` -> `"explicit"` if `is_explicit or wants_local_adult` | routing key; validated against `VALID_EXPLICITNESS = {normal, suggestive, explicit}` |
| `references` | `build_context()` reference selector | `ReferenceInput[]`, only `golden`/`trusted` reach the provider |
| `prompt` | `render_generation_prompt(context)` | scene text (Character Brain-composed) |
| `negative` | user | appended after `SDXL_NEGATIVE_BASELINE` |
| `aspect` / `scene_tags` | `selector.infer_tags()` | pick resolution bucket + IP-Adapter weight |
| `seed` | caller or random | reproducibility |

`disallowed` never becomes a request — the orchestrator returns before `_request_from_context`.

### Output: `GenerationResult` (providers/base.py)

| status | when | `handoff` |
|---|---|---|
| `ok` | render succeeded | - |
| `refused` | intent = `disallowed` | `{policy, matched}` |
| `local_adult_unavailable` | explicit + `adult_available()` false | `{setup, then, reason, non_explicit_alternative}` |
| `failed` | ComfyUI error after recovery | - (no cloud fallback for adult) |

`result.reproducibility` for an adult run additionally carries:
`explicit`, `identity_method="ip-adapter-plus-sdxl-vit-h"`, `ipadapter_file`,
`ipadapter_sha256`, `clip_vision_file`, `ipadapter_weight`, plus the standard
`model_file`/`model_sha256`/`workflow_hash`/`reference_ids`/`output_sha256`/`seed`.

`result.effective_settings` carries `explicit` and `ipadapter_weight` on top of the
usual model/steps/cfg/sampler/scheduler/width/height/batch_size.

---

## 4. Intent classification (`src/aice/intent.py`)

**Deliberately not an NLP subsystem** — a word/phrase matcher over frozen
vocabularies. `classify_explicitness(text) -> IntentVerdict`.

```
IntentVerdict(level, matched: tuple, wants_local_adult: bool, reason: str)
  level in {normal, suggestive, explicit, disallowed}
  .is_explicit / .is_disallowed / .as_dict()
```

Decision order (first hit wins):
1. **disallowed** — `_MINORS`, `_AGE_RE` (under-18 "N yo/years old"), `_INCEST`,
   `_NONCONSENT`, `_SEXUAL_VIOLENCE`, `_DEEPFAKE`, `_VOYEUR`, or (`_FAMILY` term **and**
   an explicit term together).
2. **explicit** — `_EXPLICIT` vocab.
3. **suggestive** — `_SUGGESTIVE` vocab.
4. **normal** — nothing matched.

`wants_local_adult` is set independently from `_WANTS_LOCAL_ADULT` ("use the local
adult model", "not the built-in generator", ...). The orchestrator treats
`wants_local_adult` as equivalent to `explicit` for routing.

Matching (`_hits`): phrases (containing space/`-`/`+`) match as substrings on a
space-padded lowercased haystack; single tokens match on `(?<![a-z])term(?![a-z])`.

**To extend:** add strings to the relevant tuple. Keep `demo()` asserts passing
(`python -m aice.intent`), and add a case to `tests/test_adult_backend.py::IntentClassifierTests`.
Do not add regex-heavy logic — if a case needs real parsing it probably belongs in
the disallowed bucket by conservative default.

---

## 5. Routing rules

### Planner (`planner.build_plan`)

The **first** branch, before any mode handling:

```python
if getattr(req, "explicit", "normal") == "explicit":
    return GenerationPlan(strategy="local-adult", primary_provider="comfyui",
        stages=(PlanStage("primary","comfyui",req.operation,True, ...),),
        allow_cross_provider_repair=False,
        allow_cross_provider_reference_reuse=True,   # a Codex/user ref can still condition LUSTIFY
        reason="... if it is unavailable the request is not downgraded to cloud generation.")
```

This wins even when the user forced `--backend codex_builtin`.

### Orchestrator (`plan_and_generate`)

- `verdict.level == DISALLOWED` -> `_refused_result(verdict)`, `context=None`, emits
  `request_refused`. Same in `plan_seed_generation`.
- else `explicit_level = "explicit" if (is_explicit or wants_local_adult) else verdict.level`
- `req.explicit == "explicit"` -> emit `adult_routing`, `mode = "comfyui"` (skips the
  backend-choice dialog entirely).

### `_execute`

`explicit_adult = req.explicit == "explicit"`. If `chosen == "comfyui"` and the
provider is missing / not `local_request_ready`:
- adult -> `status="local_adult_unavailable"` + handoff, emit `backend_setup_required`;
- non-adult -> existing `status="failed"`.

The cloud fallback block is `if result.status == "failed" and mode in {"auto","hybrid"} and not explicit_adult`.

### Progress events added

`intent_classified`, `request_refused`, `adult_routing`, `backend_setup_required`
(reused). Surfaced through the normal `trace` / `progress` callback.

---

## 6. The ComfyUI adult path

### Provider readiness (`ComfyUIProvider`)

```
_base_available()        runtime installed + usable GPU profile
adult_available()        _base_available
                         AND models.capability_missing(models_dir, "adult_explicit") == []
                         AND _adult_node_present()   (cfg.pins.custom_nodes has "ComfyUI_IPAdapter_plus")
capabilities().adult_explicit_generation = adult_available()[0]
available_for(req)       req.explicit == "explicit" -> adult_available()
```

### Workflow adapter (`comfy/workflow.py` + `workflows/lustify_sdxl_adult/`)

`WorkflowAdapter` loads `workflow_api.json` (ComfyUI API-format graph) + `profile.json`
(semantic slots). Calling code never references node ids.

**Node graph** (`workflow_api.json`):

```
4  CheckpointLoaderSimple        -> MODEL[0], CLIP[1], VAE[2]   (LUSTIFY .safetensors)
6  CLIPTextEncode  clip=[4,1]    positive
7  CLIPTextEncode  clip=[4,1]    negative
5  EmptyLatentImage              width/height
10 LoadImage                     reference 1
11 LoadImage                     reference 2
20 ImageBatch  image1=[10,0] image2=[11,0]        <- needs exactly 2 inputs
30 IPAdapterModelLoader          ipadapter_file
31 CLIPVisionLoader              clip_name
32 IPAdapterAdvanced  model=[4,0] ipadapter=[30,0] clip_vision=[31,0] image=[20,0]
                      weight=<scene>, weight_type="linear", combine_embeds="concat",
                      embeds_scaling="V only"
3  KSampler  model=[32,0] positive=[6,0] negative=[7,0] latent=[5,0]
             seed/steps/cfg/sampler_name/scheduler
8  VAEDecode samples=[3,0] vae=[4,2]
9  SaveImage images=[8,0]       filename_prefix
```

**Slots** (`profile.json`) map friendly names -> `{node, input}`. `render()` patches:
`model_path, positive_prompt, negative_prompt, width, height, seed, steps, cfg,
sampler, scheduler, ipadapter_weight, ipadapter_file, clip_vision_file, output_prefix`.

`reference_slots` = `[{load:"10"...},{load:"11"...}]`; `render()` sets
`graph[load].inputs.image = reference_names[i]`, and **prunes** the slot (pops the
LoadImage node + the `image{N}` input on the `text_encoder_nodes` = `["20"]` = the
ImageBatch node) when fewer refs are supplied.

**Because `ImageBatch` requires 2 inputs**, the provider duplicates a lone reference:
`if is_adult and len(render_refs) == 1: render_refs = render_refs * 2`. The adapter is
therefore never asked to prune in the adult path. If you rework the reference count,
keep ImageBatch fed with 2, or switch to a single-image IP-Adapter node.

### Settings (`policy.resolve_adult_settings`)

```
resolve_adult_settings(hw, *, aspect="portrait", scene_tags=(), free_vram_mb=None) -> EffectiveSettings
  model_id  = "lustify_sdxl_v4"
  steps=30  cfg=5.0  sampler="dpmpp_2m"  scheduler="karras"  batch_size=1
  (w,h)     = SDXL_BUCKETS[_aspect_from_scene(aspect, scene_tags)]      # portrait 832x1216
              then _fit_pixels(w,h, min(profile.max_pixels, 1_048_576))  # never tile on 8 GB
  vram_flags = profile.server_args   # shared, see section 8
  ipadapter_weight = adult_ipadapter_weight(aspect, scene_tags)
                     portrait .75 / square .72 / full_body .55 / landscape .55
```

The **negative baseline** (`policy.SDXL_NEGATIVE_BASELINE`) is prepended in
`_generate_once`; the user's own negative is appended after `; `.

---

## 7. Model registry & install

### `registry.json` (schema_version 2)

```
custom_nodes[1] = {name:"ComfyUI_IPAdapter_plus", repo, pin:"a0f451a...",
                   required_class_types:["IPAdapterModelLoader","IPAdapterAdvanced"],
                   license:"MIT", capability:"adult_explicit"}

capability_models.adult_explicit = ["lustify_sdxl_v4",
                                    "ip_adapter_plus_sdxl_vith",
                                    "clip_vision_vith"]

models.lustify_sdxl_v4        checkpoints/  6 938 042 770 B  sha256 8440379417...  CreativeML-OpenRAIL-M  required:false
      .ip_adapter_plus_sdxl_vith  ipadapter/    847 517 512 B  sha256 3f5062b840...  Apache-2.0             required:false
      .clip_vision_vith          clip_vision/ 2 528 373 448 B  sha256 6ca9667da1...  Apache-2.0             required:false

model_profiles.lustify_sdxl_v4 = machine-readable card (display_name, architecture:"sdxl",
      adult_capable:true, explicit_adult_profile:true, recommended_resolution:[832,1216],
      approximate_vram_class:"8gb-sdxl", workflow_profile:"lustify_sdxl_adult",
      identity_method:"ip-adapter-plus-sdxl-vit-h",
      source:civitai 573152, download_mirror:HF KamCastle/lustify4, license, notes)
```

`models.py` API: `model_specs()` (key->`ModelSpec`), `model_profiles()`,
`model_profile_state(models_dir, id)` (profile + `{known,installed,missing_models,local_path}`),
`capability_model_keys("adult_explicit")`, `capability_missing()`, `capability_ready()`.

`ModelSpec.dest(models_dir)` = `models_dir / dest_subdir / filename`. Downloads are
resumable (`.part` rename), sha256+size verified. `verify()` short-circuits an
already-present file so re-runs never re-download.

### Install

```
aice comfy setup --capabilities adult_explicit      # ~10.3 GB, one-time
aice comfy doctor --smoke                            # validates + marks cfg.validated
```

`cli_ops.setup`: `expanded = [required specs] + capability_model_keys(cap)`, so a
capability install **extends** the base runtime, never replaces it.
`ComfyInstaller.ensure_custom_nodes()` iterates **all** `registry.custom_nodes`
(GGUF + IPAdapter_plus), pins each with `_ensure_pinned_repo`, and
`pip install -r requirements.txt` if present (IPAdapter_plus has none — pure torch).
`ensure_extra_model_paths()` writes `extra_model_paths.yaml` with `ipadapter:` and
`clip_vision:` entries and `mkdir`s those subdirs.

Storage: everything under `cfg.models_dir` = `~/.aice/runtime/models` (checkpoints in
`~/.aice/runtime/models/checkpoints`, **not** inside `ComfyUI/`). `~/.aice/` and
`~/.aice/runtime` are gitignored; never commit them.

---

## 8. Hardware policy (8 GB)

`comfy/policy.py`. The ComfyUI **server is process-global**, so server flags cannot
vary per request — `resolve_adult_settings` reuses `profile.server_args`.

`PROFILES["rtx_5070_laptop_8gb"]` -> `server_args = ("--lowvram",
"--use-pytorch-cross-attention", "--reserve-vram", "0.9", "--cpu-vae")`,
`max_pixels = 1_048_576`.

The SDXL checkpoint + CLIP-Vision + IP-Adapter only fit with sequential CPU offload
(`--lowvram`) and a **CPU VAE decode** (`--cpu-vae`). Priorities baked into the
defaults: **identity > photorealism > reliability > speed**.

Per-scene knobs (the only ones that vary): resolution bucket and `ipadapter_weight`.
Everything else (`SDXL_STEPS/CFG/SAMPLER_NAME/SCHEDULER`) is a module constant.

Measured on an RTX 5070 Laptop 8 GB: identity smoke ~183 s (864x1184), adult smoke
~63 s (832x1216, weight 0.75), ~645 KB PNG.

---

## 9. Health / doctor / smoke

- `cli_ops.backend_health()` -> `capabilities.adult_explicit` (bool: installed AND no
  missing AND `cfg.validated`) and `capabilities.adult_explicit_missing` (list).
  Surfaced by `aice doctor` under `comfyui.capabilities`.
- `cli_ops.doctor(smoke=False)` -> node checks; if `capability_ready("adult_explicit")`
  it also runs `WorkflowAdapter("lustify_sdxl_adult").validate(object_info_keys)` and
  reports `adult_workflow_nodes`.
- `cli_ops.doctor(smoke=True)` -> `_smoke_test` (identity) **plus** `_adult_smoke`.
- `_adult_smoke(rt, hw)`: skips with `{"ok":false,"skipped":...}` if models absent;
  otherwise runs one real `ComfyUIProvider.generate(GenerationRequest(explicit="explicit",
  reference_paths=(tiny png,), seed=1234))` with a **non-explicit** prompt (validates
  the graph + 8 GB fit, not uncensored behaviour). Returns
  `{ok,status,error,duration_s,model_id,workflow_version,resolution,ipadapter_weight,output_bytes}`.

CI never runs ComfyUI — the smoke is local/opt-in.

---

## 10. Tests

| File | Covers |
|---|---|
| `tests/test_adult_backend.py` | 22 cases: explicit->local routing; no built-in fallback (generate-fails + missing); `local_adult_unavailable` handoff; disallowed->`refused` (generate + seed) with no provider call; suggestive/normal regression; `wants_local_adult` forcing; trusted refs feed adult + provenance; no auto-promotion; `intent_classified`/`adult_routing` events; planner `local-adult` lockdown; registry (`required:false`, OpenRAIL license, capability bundle, profile flags); workflow render/validate; `resolve_adult_settings` determinism; intent 4-bucket + disallowed categories |
| `tests/test_comfy_installer.py` | `test_exact_pinned_checkout_is_network_noop` (now requires a materialized worktree), `test_pinned_sha_with_empty_worktree_is_repaired` (#6 regression) |
| `tests/test_comfy_workflow.py` | `test_all_models_have_known_license` relaxed to `{Apache-2.0, CreativeML-OpenRAIL-M}` |
| `tests/test_install.py` | version assertion reads `plugin.json` instead of a hardcoded string |

Run: `python -m unittest discover -s tests`. Full suite is green on CI.
**Two failures on a dev box that has a live validated ComfyUI runtime**
(`test_engine.test_ready_state_skips_repeated_optional_anchor_question`,
`test_orchestrator.test_falls_back_to_codex_when_comfy_unavailable`) are **pre-existing
env noise** — both assume no local backend and don't stub `safe_comfy_probe`. Verified
identical on `534dd7a`. CI (no runtime) passes them.

---

## 11. Gotchas / known issues

1. **`_ensure_pinned_repo` worktree bug (fixed in #6).** `git clone --no-checkout`
   then an early `return` when the freshly-cloned default HEAD already equalled the
   pin left a bare `.git` with zero files — exactly the IPAdapter_plus case (its pin
   `a0f451a` *is* current `main`). Fix: no `--no-checkout`, fast path gated on
   `_worktree_populated()`, `--force` on the detached checkout. A broken clone
   self-heals on the next `aice comfy setup`.
2. **ImageBatch needs 2 images.** The provider duplicates a single reference. Don't
   remove that without changing the node.
3. **LUSTIFY download = single point of failure.** Only the HF mirror
   `KamCastle/lustify4` is wired (token-free). Canonical Civitai `573152` is recorded
   in `model_profiles` but needs an API token and is not auto-used. If the mirror
   dies, add another `url` or implement a Civitai-token path in `models.download`.
4. **Server args are global.** Any new per-request VRAM behaviour must be a workflow
   knob, not a server flag.
5. **`explicit` has two independent guards** (planner branch + `_execute` fallback
   gate). A refactor that removes either can silently route adult content to the
   cloud. Keep both; the tests enforce it.
6. **CPU VAE decode** is why the smoke takes ~1-3 min. Expected on 8 GB.
7. **`_adult_smoke` uses a non-explicit prompt** on purpose. It is a graph/VRAM check.
8. The classifier is English-only vocab. Non-English explicit requests fall through to
   `normal`; the engine-wide adult-only restriction (`storage.save_profile`) and
   Codex's own judgement are the backstops.

---

## 12. How to extend

**Add another local adult model:** add a `models.<key>` entry (filename, dest_subdir,
url, size, sha256, license, `required:false`), add it to
`capability_models.adult_explicit` if it's mandatory for the capability, add a
`model_profiles.<key>` card. If it needs a different graph, add
`src/aice/workflows/<name>/{workflow_api.json,profile.json}` and select it in
`ComfyUIProvider._workflow_and_model()`.

**Change a default (steps/cfg/sampler/resolution/weight):** edit the `SDXL_*`
constants / `SDXL_BUCKETS` / `_IPADAPTER_WEIGHT` in `policy.py`, update
`test_resolve_adult_settings_deterministic` and the profile card + `references/adult.md`.

**Bump the workflow:** edit `workflow_api.json` / `profile.json`, raise
`profile.json.version`. `workflow.workflow_hash()` and `workflow.version` flow into
reproducibility automatically.

**Add an intent category:** extend the vocab tuples in `intent.py`; if it needs new
routing, add a branch in `orchestrator.plan_and_generate` and `planner.build_plan`,
and cover it in `test_adult_backend.py`.

**After any change:** `python -m compileall -q src scripts && python scripts/validate_plugin.py
&& python -m unittest discover -s tests`, then `python -m aice.intent`, then (if a GPU
box) `aice comfy doctor --smoke`.
