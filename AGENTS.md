# AI Character Engine — Codex operating rules

This repository is a Codex plugin and repo-scoped skill. Treat the normal user as non-technical: conversation outside, deterministic tooling inside.

## Install / update

When the user says "install/setup/update this repo":

1. Inspect `.codex-plugin/plugin.json` and `.agents/skills/ai-char-engine/SKILL.md`.
2. Run `python scripts/install.py` to install/update the personal Codex plugin and editable package.
3. Run `aice doctor`, `python scripts/validate_plugin.py`, and `python -m unittest discover -s tests -v`.
4. Local ComfyUI is optional. Install it only when the user asks for local generation or an existing saved preference requires it; then follow `references/comfyui.md` and require a successful smoke validation before calling it ready.
5. Tell the user setup is complete only after the relevant checks pass. A Codex restart/refresh may be needed for plugin discovery.
6. Never ask the user to type shell commands unless authentication, elevation, restart, or another genuinely external action requires them.

## Conversation and state

- Begin/resume character work with `aice guide`; surface its friendly question, not its internal command/hints.
- Accept unlimited user reference photos until the user says done.
- Do not expose CLI, ComfyUI nodes, model paths, sampler settings, JSON state, or raw traces in normal conversation.
- Do not re-ask facts the user already supplied.
- `.aice/` and `~/.aice/runtime` are private runtime/model state and must never be committed.

## Image backend contract

- The supported user choices are local ComfyUI, Codex built-in `image_gen`, automatic routing, or ask-each-time.
- If both engines are viable and the preference is unset/ask-each-time, ask one short natural-language choice before generation.
- If only one engine is viable, do not ask a pointless backend question.
- A backend named in the current user request is a one-shot override unless the user clearly says to make it the default.
- `auto` may fall back from local ComfyUI to built-in generation after one bounded local recovery.
- Explicit/saved `comfyui` must never silently fall back to built-in generation; ask permission first.
- Explicit/saved `codex_builtin` must not start ComfyUI.
- The current local Qwen Image Edit workflow needs references; create a brand-new no-reference seed with built-in `image_gen` unless a future validated text-to-image local workflow is added.
- Use provider-neutral `aice generate ... --progress` for normal generation. `aice comfy generate` exists only as a compatibility/debug alias.
- Progress is coarse factual state, never fake percentages or ETAs. Translate meaningful stages into short natural updates.

## Character invariants

- Prefer evidence/provenance over guesses. User-approved sources outrank generated ones.
- Generated references are candidates until quality-gated; no recursive untrusted lineage.
- Only golden/trusted refs may enter normal generation.
- Keep normal context small and load cold skill references only when their stage requires them.
- Optimize for one image generation and at most one targeted repair.
- Add tests for every change to state, trust, provider routing, installation, or interactive behavior.
