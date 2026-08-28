# AI Character Engine — Codex operating rules

This repository is a Codex plugin and repo-scoped skill. Treat the normal user as non-technical: conversation outside, deterministic tooling inside.

## Install / update

Treat natural-language requests such as **"install/setup this repo"**, **"update/refresh this plugin"**, **"bu repoyu güncel plugin olarak güncelle"**, or **"make this repository my current AI Character Engine plugin"** as permission to perform registration/update yourself. Do not ask for shell commands or a second confirmation.

1. Inspect `.codex-plugin/plugin.json` and `.agents/skills/ai-char-engine/SKILL.md`.
2. Normal install from the open checkout: `python scripts/install.py`.
3. latest/current/güncel/newest/refresh/update: `python scripts/install.py --latest`. This uses a clean shallow latest-main checkout without rewriting the user's worktree.
4. Run `aice doctor`, plugin validation, and the unit suite against the installed/current plugin. Verify the version before reporting success.
5. Local ComfyUI is optional. Only advertise a capability whose required files/runtime are present **and whose own smoke validation is green**. Identity, bootstrap and adult-explicit validation are independent.
6. Optional bootstrap/adult models are installed only when relevant.
7. Never discard uncommitted user changes. Ask for manual action only for genuine external blockers such as auth/elevation/restart.

## Conversation and state

- Begin/resume with `aice guide`; surface its friendly question, not internal hints.
- Accept unlimited user references until they say done.
- Do not expose CLI, ComfyUI nodes/settings, paths, model filenames, JSON or raw traces in normal conversation.
- Do not re-ask supplied facts.
- `.aice/` and `~/.aice/runtime` are private runtime/model state and must never be committed.

## Provider architecture

AICE owns identity. Providers are workers.

- Character Brain, golden/trusted/candidate lineage, reference selection and history are provider-neutral.
- Provider origin is provenance only. It never increases trust.
- A trusted reference created by either provider may condition the other.
- Generated derivatives from either provider enter as candidates and require the same quality gate before promotion.
- Candidate/rejected images never enter normal conditioning and never parent generated references.
- A failed image supplied for repair is an edit target, not identity truth.

## Image strategy contract

User-facing persistent choices stay simple: local ComfyUI, Codex built-in image generation, automatic intelligent choice, or ask each time. A one-shot request may explicitly allow `hybrid` cooperation; do not persist hybrid unless the product schema later adds it.

Rules:
- if both relevant normal providers are viable and preference is unset/ask-each-time, ask one short natural-language question;
- if only one relevant capability is viable, do not ask a pointless question;
- explicit current-turn provider intent overrides saved preference for that request unless the user clearly says default/from now on;
- `auto` chooses one primary provider and may authorize one repair/reference-expansion stage after validation; it must not double-generate by default;
- explicit/saved `comfyui` never silently falls back;
- explicit/saved `codex_builtin` never starts ComfyUI;
- explicit adult synthetic content routes only to the **validated** local `adult_explicit` profile (LUSTIFY SDXL); never built-in generation and no silent downgrade;
- `local_adult_unavailable` means setup/smoke is required or a non-explicit alternative may be offered;
- `adult_identity_required` means an explicit scratch request needs a neutral adult identity seed approved first. Do not send that explicit scratch request to built-in generation or Qwen bootstrap; establish identity, then retry the original request locally;
- `refused` means a disallowed category—relay it and never retry around it;
- a new non-explicit seed may be created by built-in generation or by the separately validated local bootstrap capability;
- after seed approval, either provider may reuse it through the shared trusted reference fabric.

Use `aice seed-generate` for first-seed planning and provider-neutral `aice generate ... --progress` for normal work. `aice comfy generate` is compatibility/debug only.

## Progress / repair

- Progress events are factual coarse state, never fake percentages/ETAs.
- Read `result.plan` before invoking an optional second provider.
- `repair_if_needed` is permission only; use it exactly once and only after visual validation finds a hard/localized failure.
- Normal target remains one primary generation plus at most one targeted repair.

## Character invariants

- Prefer evidence/provenance over guesses; explicit user locks outrank generated evidence.
- Keep context/reference budgets small and deterministic.
- Load cold skill references only for the relevant stage.
- Add tests for every change to trust, provider capability/planning, installer/runtime, state migration or conversational behavior.
