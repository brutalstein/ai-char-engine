# Interactive onboarding reference

Use this file only during onboarding.

## Goal

Make onboarding feel like a guided creative assistant. The user never needs to know commands or schemas.

## From scratch

1. Create state with origin `scratch`.
2. Ask for a natural-language appearance description only if the conversation does not already contain one.
3. Generate one primary seed with built-in `image_gen`.
4. Because a generated initial seed has no trusted parent yet, save the image to a workspace path and register it by first creating a user-facing approval checkpoint. The CLI intentionally forbids ordinary parentless generated references; for the seed, once the user says they want this exact generated person, treat that explicit approval as user evidence and register the file as `user_uploaded`/golden with notes stating `approved generated seed`. This is a semantic trust transition: the user's approval, not the model output itself, makes it source-of-truth.
5. Build the brain from the approved seed.
6. Expand face angles lazily.
7. If body geometry is missing, propose exactly one full-body front anchor and require approval before side/back expansion.

Do not regenerate repeatedly. If the user rejects a seed, ask for the smallest correction and try again once at a time.

## From existing references

The user can upload 1, 5, 20, or more images. There is no artificial cap.

For every image:
- inspect before registering;
- tag only what is visible (`face`, `front`, `side`, `back`, `upper_body`, `full_body`, `hands`, `arms`, `legs`);
- use a descriptive role such as `user_face_front`, `user_full_body_back`, `user_detail_left_wrist`;
- register as `user_uploaded` + `golden`;
- cache a compact analysis keyed by image SHA;
- never infer hidden permanent traits from a single crop.

After each batch say something lightweight such as: "Added 4 references. You can send more, or say done when you're ready." Do not recite filenames or internal IDs unless asked.

When the user says done, close reference collection and synthesize the brain.

## Analysis cache

Before visually analyzing a reference that may already have been processed, run `aice analysis-get`. On a hit, reuse it. On a miss, inspect once and save a compact payload with `aice analysis-set`.

Recommended cached shape:

```json
{
  "tags": ["face", "front", "upper_body"],
  "observations": [
    {"path": "identity.hair.color", "value": "jet black"}
  ],
  "notes": "clear daylight portrait"
}
```

Do not cache speculative facts.
