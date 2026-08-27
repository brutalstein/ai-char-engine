# AI Character Engine — Codex operating rules

This repo is a Codex plugin and repo-scoped skill. Treat the user as non-technical unless they explicitly ask for developer details.

## When the user says "install/setup this repo"

1. Inspect `.codex-plugin/plugin.json` and `.agents/skills/ai-char-engine/SKILL.md`.
2. Run `python scripts/install.py` to install/update the personal Codex plugin and editable local package.
3. Run `aice doctor` and `python -m unittest discover -s tests -v`.
4. If both pass, tell the user setup is complete and that Codex may need a restart to refresh plugin discovery.
5. Do not ask the user to type shell commands unless installation actually fails and manual intervention is necessary.

## Interaction rules

- Begin/resume with `aice guide`; surface its friendly question, not its internal commands.
- Users can upload unlimited reference photos; keep accepting them until they say done.
- Do not expose CLI mechanics in normal use.
- Image generation is auto-routed: local ComfyUI backend when installed+validated, else built-in `image_gen` (never a paid Image API). The local runtime/models live in `~/.aice/runtime` and are private. See `.agents/skills/ai-char-engine/references/comfyui.md` for setup/debug only.
- `.aice/` is private runtime state and must never be committed.
- Prefer evidence/provenance over guesses. User-approved sources outrank generated ones.
- Generated refs are candidates until quality-gated; no recursive untrusted lineage.
- Optimize for one image generation and at most one targeted repair.
- Keep normal context small; use progressive skill references only when the current stage requires them.
- Add tests for any state/brain/reference/install behavior change.
