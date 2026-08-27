# AI Character Engine

A Codex-native plugin for building one persistent synthetic adult character and generating new photorealistic images of that same character with minimal user effort.

The user experience is intentionally conversational: **you do not need to learn commands, schemas, prompt engineering, or reference-management rules.** Codex guides onboarding, runs the local state engine itself, uses built-in image generation, and asks only the next useful question.

## What it does

- create a character from scratch, or start from your existing reference photos
- accept any number of reference images
- build an evidence-grounded character brain with source provenance
- surface conflicting permanent details instead of guessing
- let user-confirmed facts override ambiguous visual evidence
- maintain trusted/golden/candidate reference lineage to reduce identity drift
- expand missing angles lazily instead of generating a huge reference pack up front
- select only the references needed for each scene
- keep permanent details visibility-aware
- remember recent pose/gaze/framing patterns using tiny fingerprints instead of resending history images
- use bounded generation/repair budgets to keep model usage predictable
- cache repeated reference analysis by SHA-256

## Easiest install

In Codex, paste this repository and say:

> Install this plugin and set it up for me.

Codex is instructed by `AGENTS.md` to install the personal plugin, run diagnostics and tests, and avoid asking you to type commands unless something actually fails.

Repository:

`https://github.com/brutalstein/ai-char-engine`

After installation, restart Codex if it asks you to refresh plugin discovery.

## What onboarding feels like

### New character

You can say:

> I want to create a new character from scratch.

Codex will ask for a natural description, create one seed image, show it for approval, build the identity brain, and optionally propose missing body/reference angles only when useful.

### Existing character

You can say:

> I already have the character. I want to upload references.

Codex will invite you to upload **as many images as you want**. After each batch it keeps accepting more until you say `done`. It inspects and registers them internally, builds the brain, and asks you only about genuinely conflicting permanent details.

### Generate new photos

Once ready, just describe the image:

> old-town cafe, rainy afternoon, candid friend-taken photo

No technical prompt is required.

## Architecture

```text
Friendly Codex conversation
          |
          v
 Interactive guide/state machine
          |
          +-------------------+
          |                   |
          v                   v
 Evidence brain        Trusted reference bank
 (provenance +          golden / trusted /
 conflict resolver)     candidate / rejected
          |                   |
          +---------+---------+
                    v
        deterministic context compiler
                    |
        selective references + tiny history
                    |
                    v
           Codex built-in image_gen
                    |
              adaptive validation
                    |
             <= 1 targeted repair
                    |
                    v
               final image
```

The local Python layer is standard-library-only and owns deterministic state. Codex owns semantic interpretation and visual inspection. Built-in `image_gen` owns image creation/editing.

## Character brain

The brain is not one long prose prompt. Stable facts are stored as an evidence ledger.

Example conceptually:

```text
identity.hair.color = "jet black"
  source: user-face-front-...
  authority: golden

identity.eyes.color = conflict
  brown  <- golden reference A
  hazel  <- golden reference B
```

When evidence is near-tied, the engine asks rather than silently choosing. A direct user lock becomes authoritative.

Permanent features can include visibility metadata:

```json
{
  "kind": "tattoo",
  "location": "left_wrist",
  "description": "small minimalist crescent",
  "visibility_tags": ["hands", "arms"]
}
```

That feature is omitted from active context when the wrist/arm is not expected to be visible.

## Reference trust model

- **golden** — user-supplied or explicitly user-approved source of truth
- **trusted** — generated reference that passed identity/anatomy/stable-trait checks
- **candidate** — generated but not trusted yet
- **rejected** — failed quality gate

Generated references cannot directly enter trusted/golden state. They require trusted parents and validation; golden promotion additionally requires explicit user approval.

## Usage budgets

| mode | selected refs | recent approved history | validation | max repair |
|---|---:|---:|---|---:|
| economy | 2 | 4 | critical | 0 |
| balanced | 3 | 8 | light | 1 |
| quality | 4 | 12 | full | 1 |

`balanced` is the default.

## Local runtime data

Character data stays in `.aice/` and is gitignored:

```text
.aice/
  characters/
    <character>/
      character.json
      brain.json
      onboarding.json
      references/
      outputs/
      history/
      cache/
```

Do not commit this directory if the repository is public.

## Developer commands

Normal users should not need these. They exist so Codex and developers can operate/test the deterministic engine.

```text
aice doctor
aice guide [character]
aice begin <name> --origin scratch|references
aice characters
aice add-ref ...
aice refs-done <character>
aice observe <character> --json ...
aice brain <character>
aice lock-fact <character> <path> --value ...
aice bootstrap-plan <character>
aice context <character> "..." --compact
aice prompt <character> "..."
aice record ...
aice stats <character>
```

## Manual developer setup

Requires Python 3.11+.

```bash
python -m pip install -e .
aice doctor
python -m unittest discover -s tests -v
```

Personal plugin installation can also be invoked directly:

```bash
python scripts/install.py
```

## Design principles

1. friendly conversation outside, deterministic state machine inside
2. evidence before assumption
3. explicit conflict instead of confident guessing
4. generated refs never bootstrap trust recursively
5. smallest useful context per image
6. unlimited user references, selective model references
7. one normal generation; one bounded repair at most
8. cache unchanged visual analysis
9. keep implementation small enough to audit
10. treat visual-model consistency limits as measurable engineering constraints, not something software can magically eliminate

## Status

`v0.2.0` focuses on the interactive single-character workflow, evidence-graph brain, reference provenance, conflict handling, lazy expansion, token/call optimization, personal Codex plugin installation, and cross-platform tests.
