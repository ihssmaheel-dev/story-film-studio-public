# Part 001 — Written shots

Revision: r1
Status: draft
Single complete video or part within a series:
Scene coverage / source story revision:
Opening purpose / exact opening line if spoken:
Plot and emotional progression:
Ending / exact final line if spoken:
Target runtime / range / flexibility:
Provisional runtime assumptions:
Image-count / pacing rationale (`shots.json.image_planning`):
Shared references / reused images / repair allowance (separate from story shots):
Frame dimensions / FPS:
Camera approach (static / selective gentle movement):
Approved visual bible path / style ID and revision:
Performance mode / speakers:
Sound plan revision:

| Shot | Scene IDs / provisional time | Exact narration or dialogue / speaker | Written visual / action / emotion | Style / CHAR / LOC / PROP IDs | Setup / reveal | Camera move / story reason / poses / protected details | Sound requirement IDs / onset-exit intent | Subtitle intent |
|---|---|---|---|---|---|---|---|---|
| SHOT-001 | | | | | | | | |

Fast reviews the selected part against whole-story dependencies; Strict reviews every written shot across all parts. Preserve intentional action/silence; select image count and hold lengths from story purpose. After real performance/alignment, authoritative intervals and sound mix cues live in `timeline.json`.

Follow root `instructions/shot-planning.md`. Record each shot's narrative purpose and entry reason in `shots.json.image_planning`, bound to the current final-story hash. Choose images for actual changes of action/state, emotion, information or framing need; combine redundant views, preserve reactions and earned reveals, and leave room for the ending. Do not use an images-per-minute preset or cut on every line. Check the actual measured holds and full preview for rushed cuts, dragging frames, subtitle legibility and visual continuity. This is internal agent work within scope.

Choose static, zoom_in, zoom_out or pan for a story reason. Put the exact optional `motion` object in `shots.json`; it carries through to the timeline. Moving shots need safe start/end poses, protected normalized boxes and timing fractions. Check the actual image against the boxes before approval; a coordinate declaration is not visual QA. See `docs/12-camera-motion.md` in the studio. Do not use motion to replace needed story beats or reveal clues early.
