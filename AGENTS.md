# AI Character Engine contributor rules

Keep this project small, deterministic, and Codex-native.

- The default image path is Codex built-in `image_gen` via the system `imagegen` skill. Do not add an API-key requirement to the default workflow.
- Python runtime code must remain standard-library-only unless a measurable requirement justifies a dependency.
- `.aice/` is private runtime state and must stay gitignored.
- User-uploaded/explicitly approved references outrank generated references.
- Generated references must enter as candidates and pass the quality gate before normal use.
- Never recursively trust an unvalidated generated reference.
- Never invent invisible permanent traits.
- Optimize normal generation for one image call; allow at most one targeted repair in balanced/quality modes.
- Prefer compact machine-readable state over long prose prompts.
- Add/update tests for deterministic behavior before changing selection, storage, promotion, or budgeting logic.
- Do not claim scientific identity-similarity percentages; use pass/warn/fail quality signals.
