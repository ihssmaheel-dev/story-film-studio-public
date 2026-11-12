# 03 — World bible, fixed geometry and foreshadowing

> **Workflow:** Fast is the new-project default; see [Fast workflow](13-fast-workflow.md). G1–G6 and separate reference/audition signoffs in this guide describe Strict mode. Fast uses scoped delegation and internal review; technical, continuity and genuine QA requirements still apply. Existing projects without a workflow record remain Strict.

## Inventory the entire audited story first
Use the audited final story and `continuity/story-ledger.json` as evidence; resolve draft assumptions before canon. Extract **all** named/recurring characters, locations, objects, signage, weather, lighting, costume changes, injuries, destruction and future-reveal dependencies across every part. Assign stable IDs: `STYLE-001`, `CHAR-001`, `LOC-001`, `PROP-001`, `EVENT-001`, `SHOT-001`. IDs never change when a name changes. Register styles in `continuity/entities.json` alongside characters, locations and props; link their references and shots in `continuity/dependencies.json`.

## Story-specific visual bible
`world/visual-bible.md` is the canonical definition of the look after G3. Record its style ID, revision, status, selected reference paths and provenance. Define medium/treatment, realism, anatomy or abstraction, shape language, surface/linework, palette, light and composition, with measurable acceptance criteria. The optional global inspiration library is not canonical. Deliberate mixed styles require separate style IDs, a clear mapping to scenes/shots, stable identity rules and approved transitions.

## Canonical character records
Begin with the character's narrative job: goal, conflict, relationships, history, age/design type, personality, profession/life circumstances and the emotions/actions the role must communicate. Preserve author-specified traits. Explain how the design supports that particular role through silhouette, anatomy/proportions or abstraction, face/head shape, hair/surface features, eyes/mouth or expression system, clothing/materials/colors, accessories, relative height, posture and habitual expression. Do not substitute a generic handsome protagonist, menacing villain or the gallery cast. Separate stable identity anchors from changes caused by events.

Compare principal cast silhouettes, faces and outfit shapes/colors together so viewers can tell them apart at the actual shot size. Within the selected medium, test the expressions and poses the story truly needs: authority, vulnerability, humor, fatigue, grief, determination or other written performance. Use neutral and representative emotional/action views and only useful front/side/three-quarter angles, rather than producing every possible sheet. Inspect the actual design for role fit, readable acting, style fidelity and repeated identity before using it in shots. Fast handles these design choices/reviews within scope; Strict uses G3.

Author the complete structured profiles in `world/cast.json`; `prepare` generates matching character Markdown and registry bindings. Use [the cast-sheet workflow](18-cast-sheets.md) for legible identity/expression/pose sheets, exact inspected-image hashes and required coverage. The monitor shows current/preserved references and queues actual user change requests. Missing bindings/profiles or an uninspected sheet block updated production commands; writing `reviewed` or putting a character ID only in prose does not complete these records.

Humans, non-human beings and abstract designs are all valid; mark inapplicable fields rather than imposing human or stickman anatomy. Reuse exact character IDs/revisions/reference images across every part and the full cut. Avoid accidental changes to age, face, proportions or costume; track planned aging, injury, wet clothes and other state changes by story time, including what the next part inherits. A newly rendered angle must remain the same character.

## Canonical location records
Stable top-down layout with compass orientation or an explicit local axis; dimensions, architecture/terrain, openings, landmarks, relative scale, permanent objects, entrance/exit routes, camera-direction landmarks and lighting/weather variants. Use details appropriate to the setting, whether a street, forest, spaceship, fantasy realm or abstract stage. Maintain **location master wide image**, **annotated plan** and **camera-facing views**. A new angle must be possible given the plan; image generators may mirror scenes, so explicitly check left/right and north/south. Stylized geometry still needs consistent rules.

## Canonical prop records
Geometry, material, color, dimensions relative to character, mounts, physical location, first visible part/shot, future plot use, ownership, movable/permanent status, and state timeline. Example: `PROP-014` black lamp on **east sidewalk**, 2m south of brick store corner; `PROP-015` small gray loudspeaker mounted on lamp's **north-facing arm**. If speaker announces in part 7, it must exist in relevant earlier establishing views. Don't force it into frames where it would be offscreen.

## Foreshadowing dependency ledger
For every future event list prerequisites: `EVENT-037 announcement` → `PROP-015 speaker installed` → `PROP-014 lamp` → `LOC-001 street geometry`. Include `introduced_at`, `revealed_at`, `payoff_at`, `shots_affected`. Review backward from finale to first part. Include sound dependencies: physical emitters/events must exist or be implied when heard. Track acoustic state/perspective and sound asset IDs; actual cue times live in the part timeline.

## State ledger
Record events that change visual truth: before/after timestamps and affected entity IDs (door opened, lamp shattered, character injured, weather changed). A shot uses state at its **story timestamp**, not latest real-world asset. Never overwrite an old canonical state without versioning.

## Prompt inheritance
Each shot prompt must reference `style_id`, `style_revision`, `location_id`, `location_state`, `character_ids`, `prop_ids`, `camera_direction`, approved reference image paths, and visible/invisible objects. Inherit the style-specific anatomy, material, palette and lighting rules from the visual bible; build exclusions from those rules instead of imposing a universal negative prompt. A prompt cannot override world bible by accident. If a prompt conflicts, stop and resolve the source of truth.

## Revision blast radius
On change, scan `continuity/dependencies.json` and all shot manifests for affected IDs, including style IDs; invalidate references, prompts, generated images, alignment if script changed, renders and approvals where applicable. A global style change usually affects all visual assets using that style, while a scene-specific variation affects its mapped shots. Preserve old revisions for rollback.
