# AI Character Engine — Codex operating rules

This repository is a Codex plugin and repo-scoped skill. Treat the normal user as non-technical: conversation outside, deterministic tooling inside.

## Install / update

Treat natural-language requests such as **"install/setup this repo"**, **"update/refresh this plugin"**, **"bu repoyu güncel plugin olarak güncelle"**, or **"make this repository my current AI Character Engine plugin"** as permission to perform registration/update yourself. Do not ask for shell commands or a second confirmation.

1. Inspect `.codex-plugin/plugin.json` and `.agents/skills/ai-char-engine/SKILL.md`.
2. Normal install from the open checkout: `python scripts/install.py`.
3. If the user says latest/current/güncel/newest/refresh/update: `python scripts/install.py --latest`. This installs a clean shallow latest-`main` checkout without rewriting the user's worktree and replaces the existing personal plugin registration in place.
4. Run `aice doctor`, plugin validation, and the unit suite against the installed/current plugin. Verify the version before reporting success.
5. Local ComfyUI is optional. Follow `references/comfyui.md`; only advertise capabilities that are actually installed and validated. The optional no-reference bootstrap models are installed only when local character creation is requested.
6. Mention restart/refresh only if Codex discovery needs it.
7. Never discard uncommitted user changes to refresh the plugin.
8. Ask the user for manual terminal action only for a genuine external blocker such as auth/elevation/restart.

## Conversation and state

- Begin/resume with `aice guide`; surface its friendly question, not internal hints.
- Accept unlimited user reference photos until they say done.
- Do not expose CLI, ComfyUI nodes/settings, paths, model filenames, JSON or raw traces in normal conversation.
- Do not re-ask supplied facts.
- `.aice/` and `~/.aice/runtime` are private runtime/model state and must never be committed.

## Provider architecture

AICE owns identity. Providers are workers.

- Character Brain, golden/trusted/candidate lineage, reference selection and history are provider-neutral.
- Provider origin is provenance only. It never increases trust.
- A trusted reference created by Codex built-in generation may condition ComfyUI; a trusted reference created by ComfyUI may condition built-in generation.
- Generated derivatives from either provider enter as candidates and require the same identity/anatomy/stable-traits gate before promotion.
- Candidate/rejected images never enter normal conditioning and never parent generated references.
- A failed image supplied for repair is an edit target, not identity truth.

## Image strategy contract

User-facing choices remain simple:
- local ComfyUI;
- Codex built-in `image_gen`;
- automatic intelligent choice;
- ask each time.

A one-shot request may also explicitly allow `hybrid` cooperation (for example “Comfy first, ImageGen can help if needed”). Do not persist a separate hybrid preference unless the product schema later adds one; `auto` is the persistent intelligent strategy.

Rules:
- if both relevant providers are viable and preference is unset/ask-each-time, ask one short natural-language question;
- if only one relevant capability is viable, do not ask a pointless question;
- explicit current-turn provider intent overrides saved preference for that request only unless user says “from now on/default”;
- `auto` chooses the strongest viable primary provider and may authorize one cross-provider repair/reference-expansion stage after validation; it must not double-generate by default;
- explicit/saved `comfyui` never silently falls back;
- explicit/saved `codex_builtin` never starts ComfyUI;
- a new no-reference seed may be created by built-in generation or by ComfyUI when the optional local bootstrap capability is installed/validated;
- after seed approval, either provider may use it through the shared trusted reference fabric.

Use `aice seed-generate` for first-seed planning and provider-neutral `aice generate ... --progress` for normal work. `aice comfy generate` is compatibility/debug only.

## Progress / repair

- Progress events are factual coarse state, never fake percentages/ETAs.
- Read `result.plan` before invoking an optional second provider.
- A cross-provider `repair_if_needed` stage is permission only. Use it exactly once and only after visual validation finds a hard/localized failure.
- Normal target remains one primary generation plus at most one targeted repair.

## Character invariants

- Prefer evidence/provenance over guesses; explicit user locks outrank generated evidence.
- Keep context/reference budgets small and deterministic.
- Load cold skill references only for the relevant stage.
- Add tests for every change to trust, provider capability/planning, installer/runtime, state migration or conversational behavior.
