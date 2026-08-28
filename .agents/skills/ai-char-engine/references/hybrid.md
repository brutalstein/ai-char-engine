# Hybrid provider orchestration

Load this only when planning cross-provider generation, reference expansion, or repair. Character identity belongs to AICE; ComfyUI and Codex built-in image generation are interchangeable workers with different capabilities.

## Core invariants

- Provider origin is provenance, never trust.
- Only golden/trusted references may condition identity generation.
- A generated output becomes a reference only after explicit registration as `generated`/`candidate` with trusted parent IDs, followed by identity/anatomy/stable-traits validation.
- Never promote a provider's output merely because that provider produced it.
- A failed image used for repair is an edit target, not identity truth.
- Default to one primary generation. A second provider call is allowed only for one justified repair or reference-expansion stage.

## Operations

AICE plans four operations:

- `generate`: normal saved-character photo generation.
- `bootstrap`: create the first no-reference seed.
- `reference_expand`: derive a missing trusted view from existing trusted anchors.
- `repair`: targeted correction of a failed output while trusted references remain identity anchors.

Provider capabilities determine which worker can perform each operation. Built-in image generation can always plan bootstrap and general generation. Local ComfyUI can bootstrap only when its optional text-to-image capability is installed and validated; its identity/edit workflow supports multi-reference generation, expansion, and repair.

## Strategy semantics

- `codex_builtin`: use built-in image generation only; never start ComfyUI.
- `comfyui`: use local ComfyUI only; never silently fall back.
- `auto`: choose the strongest viable primary provider for the requested operation. One bounded recovery/fallback is allowed where policy permits.
- `hybrid`: one-shot cooperative intent. Choose one primary provider, then expose at most one optional cross-provider follow-up stage if validation later shows a real need. Do not run both providers speculatively.

Saved preferences remain `auto`, `comfyui`, `codex_builtin`, or `ask_each_time`. Treat `hybrid` as a one-shot strategy unless a future schema explicitly adds a persistent hybrid preference.

## Bootstrap

For a scratch character, compile a provider-neutral seed contract from the user's natural description. If local bootstrap capability is unavailable, built-in generation is the safe default. If local bootstrap is installed and validated, AICE may choose it when explicitly requested or when automatic planning judges it appropriate.

Do not register the generated seed as trusted before user approval. On approval, register it through the dedicated approved-seed path with its true `origin_provider`. The user approval is what makes it golden.

After approval, either provider may reuse the same golden seed. Optional expansion can derive side/full-body anchors, but each derived image must enter as candidate and pass the quality gate.

## Reference expansion

Use `--operation reference_expand` only for a genuinely missing angle/geometry that improves future generation. The normal selector still supplies only golden/trusted parents. Register the result with:

- `source=generated`
- `tier=candidate`
- `origin_provider=<actual provider>`
- trusted `parent_ids`

Then validate identity, anatomy, and stable traits before promotion.

## Repair

Use `--operation repair --repair-of <image>` only after visual validation identifies a localized hard failure. The repair target is supplied separately from identity references. Trusted references remain the identity anchors.

If the plan exposes `repair_if_needed`, invoke it only when needed and only once. A passing image gets no extra call.

## Cross-provider examples

Built-in seed -> user approval -> golden -> ComfyUI reference expansion -> candidate -> quality gate -> trusted -> either provider for normal generation.

ComfyUI generation -> visual validation finds localized face drift -> built-in targeted repair using the failed image as edit target plus the same trusted AICE references.

Built-in generation -> localized detail problem -> ComfyUI targeted repair if local capability is validated and the plan allows it.

## Progress / handoff

Planner-level events include `seed_contract_compiled`, `context_compiled`, `plan_resolved`, `backend_selected`, `backend_choice_required`, and `backend_setup_required`. Provider-level events remain factual (`rendering`, `builtin_planned`, `provider_complete`, etc.). Never invent percentages or ETAs.

Built-in results are `planned`; Codex must call built-in `image_gen` using the returned handoff/effective settings and selected references. ComfyUI `ok` results point to a local output file for visual validation.
