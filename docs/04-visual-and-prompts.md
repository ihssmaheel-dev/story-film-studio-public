# 04 — Visual style, still-image design and prompts

> **Workflow:** Fast is the new-project default; see [Fast workflow](13-fast-workflow.md). G1–G6 and separate reference/audition signoffs in this guide describe Strict mode. Fast uses scoped delegation and internal review; technical, continuity and genuine QA requirements still apply. Existing projects without a workflow record remain Strict.

## Open style selection, precise execution
Every story chooses its own visual treatment. Accept anime, manga, stickman, realistic cinematic imagery, 3D-rendered looks, comics, watercolor, pixel art, collage or any custom direction. This list is illustrative, not a set of allowed values. The look applies to still images; an anime or 3D request alone does not authorize animation or change the production format.

Genre/theme describe the story; style describes how it looks. Ask a material question only when the user's intent cannot be inferred from their description or selected references. When undecided, present two or three distinct directions with concrete differences in emotion, detail, legibility and available tool capability. Do not silently choose stickman or blend incompatible references.

User-supplied references and existing saved selections are optional inspiration. They do not establish canonical characters or settings. Any style can start from text alone or newly supplied references.

Use the [eight-look curated catalog](../references/style/visual-preferences/README.md) and [comparison board](../references/style/visual-preferences/comparison-sheet.png) for a focused starting point: Realistic Cinema, Detailed Cinematic Anime, Cel-Shaded Anime, Feature 2D Animation, Stylized 3D Animation, Painted Storybook, Storybook Stickman and Cinematic Graphic Novel. Every active example was replaced during the 2026-10-29 refresh. The shared station reunion demonstrates expressions, light, staging and different mediums; its people, setting, palette and mood are not a default for every film. Suggested genres are starting points, not restrictions. Other media remain custom directions, and explicit existing selections keep their exact snapshots.

Compare silhouettes, face/anatomy construction, line/edge behavior, shading, materials and background design, not just color or a surface filter. For requested minimal/stick figures, define whether simple characters sit inside a richer illustrated environment or whether the whole world uses sparse line art. These are distinct custom treatments. Artistic quality depends on the actual story, design and provider result; inclusion in the chooser does not approve story-specific canon. Preserve previous path/hash evidence and never silently replace an earlier chosen sample with refreshed pixels.

Show the sheet when useful, accept a descriptive name/ID/custom refinement and record the exact file/hash and intended role. Keep a manifest hash or Git commit internally for provenance; the chooser has no version-selection step. Only selected images are snapshotted into a story; their demo character and location are not reused unless independently requested and approved. The library was explicitly requested as global style-selection material. Story-specific generated proofs and sheets still follow the inventory/dependency review, tool authorization and G3 workflow below.

## Visual bible and reference selection
Record `STYLE-001`, revision and approval status in the story's `world/visual-bible.md`. Specify:
- Intended visual treatment and emotional effect; the qualities that make it distinctive.
- Medium, realism level, shape/silhouette language and anatomy/proportion rules.
- Face/expression system, linework or edge treatment, materials, textures and detail density.
- Palette, contrast, lighting, depth, lens/perspective and composition rules.
- What remains constant across characters, locations, props and every part; permitted state variations.
- Selected references, the role of each, provenance/checksums and known usage permissions.
- Style-specific acceptance criteria, exclusions and any intentionally mixed styles.

Select references for specific purposes: a palette reference need not supply character design or architecture. Resolve conflicts with the user, then state reference priority in the bible. Keep story snapshots and `references/style/manifest.json` inside the story project. `--style` and `--style-reference` in the scaffold express draft preferences only. No specific image filenames are required.

## Exact reference bindings and current prompts

The image bridge attaches available canonical style/identity/geometry references and selected treatment snapshots to both reference-sheet and final-shot requests. `reference_bindings` numbers every attached file in tool order, records its exact SHA-256 and lists its entity/contribution roles. The same cast sheet or copied snapshot is attached once when its bytes are identical, retaining all actual roles. The prompt names those roles so an identity sheet, location map and treatment example are not blended indiscriminately. Reference entities in a multi-style story need an explicit registered `style_id`; their correct style bible is used instead of a generic global bible.

Keep a style's chosen snapshot paths in `continuity/entities.json` under its existing `inspiration_paths` when selection would otherwise be ambiguous. One project snapshot can be inherited automatically; multiple historical snapshots require explicit mapping unless selected snapshot paths are already in that style's `reference_paths`. A recorded original source alias resolves to its own preserved snapshot/hash, never today's different image with the same filename. Unselected images remain unattached. Missing, changed, malformed or non-image selected inputs stop the request for agent repair; do not substitute a new treatment silently. Custom directions without gallery examples remain valid.

The [observed treatment record](../references/style/visual-preferences/fidelity.json) describes the eight current images by their exact bytes. It distinguishes detailed painted anime from broad cel shading and records the accepted Storybook Stickman anatomy: clothed bodies/legs, thin black line arms and rounded black hands in rich scenery. The historical VIS-22 generation prompt asked for line legs; it remains unchanged as provenance. Its text does not override the actual selected image. Explicit visual-bible refinements remain valid, and gallery actors, scenery, daylight and palette do not become story facts.

New requests also bind the current written shot, delivery aspect and scoped entity/reference context. Queue/start/import refuse a changed context rather than applying an old shot prompt to a new visual plan. Unrelated unseen entity edits do not invalidate it. If an actual result arrives after a material change, preserve that output and actual provider receipt, reconcile the known outcome with `studio images ... failed --outcome-known`, then compile the current work; never retry an unknown outcome. Legacy receipts keep their original evidence; recompiling adopts the current contract. Additional selected style inputs are included in visual-review currency with portable artifact paths, without changing existing review hashes when all references were already bound. Export retains every attached reference used by the part and the selected-style provenance manifest; release inputs must be snapshotted inside the project.

Before a real tool call, inspect the numbered files and check the written prompt against their actual medium/anatomy, identity, orientation, scene state, palette/light intent, composition and reveal order. After generation, inspect those same criteria in the returned pixels. A style proof should demonstrate the authored story designs requested in its brief; do not copy the gallery's sample cast or generate unused sheet views. Correct a concrete mismatch with a targeted repair within scope, retaining successful references. Structure, hashes and prompt wording alone cannot guarantee a perfect generated match.

## Quality criteria depend on the chosen look
| Example direction | Define and keep consistent | Look for during review |
|---|---|---|
| Anime / manga | Character construction, eye/hair shapes, line weights, cel or painted shading, background treatment | Stable face model, controlled expressions, coherent perspective and line/shading treatment |
| Stickman / minimal figures | Head/limb ratios, expression vocabulary, clothing simplification, environment detail | Readable poses, stable silhouettes and deliberate contrast between characters and settings |
| Realistic / photographic | Identity, anatomy, skin/material texture, plausible light, lens and depth | Faces/hands where visible, coherent reflections/shadows, believable scale and consistent identity |
| 3D-rendered look | Model proportions, materials, surface roughness, lighting and render treatment | Stable character models, consistent materials and contact shadows |
| Watercolor / painterly | Brush/pigment behavior, edges, paper/canvas texture, simplification and palette | Consistent paint treatment and readable actions/reveal details |
| Comics / graphic novel | Inking, shape language, shading/halftones and panel-like composition | Consistent ink treatment, focal clarity and intentional readable text only |
| Pixel art | Source pixel grid, palette, silhouette and scaling method | Consistent pixel scale and intentional edges; avoid accidental smoothing or mixed resolutions |
| Custom / mixed | Explicit rules for each component, scene mapping and transitions | The defined combination stays consistent; a change of style remains intentional and approved |

Use the applicable criteria and add others for the actual request. Simplified anatomy, exaggerated proportions or abstract materials are valid when canonical. Technical errors and unplanned changes remain defects. For styles with a native grid or unusual texture, agree how the source will be fitted to the approved delivery frame; preserve its defining features and inspect the final resized image.

## Style proof and provider fit
After the full-story dependency matrix exists, show a representative reference scene containing a character, an environment and an important prop in the intended look. It can use selected existing imagery or newly generated draft references. For generation, first disclose the provider, required inputs, privacy, costs and alternatives and obtain the required tool/expense authorization. Compare identity, geometry, emotion and style fidelity across a wide view and a closer view when useful.

Do not approve a look from a style label alone. Review the bible, style proof and canonical sheets together at G3. If the tool cannot sustain the design, propose stronger references, simpler framing or another tool with disclosed tradeoffs. Do not promise universal provider support or quietly change the user's style.

## Reference generation order
1. Complete the whole-story inventory and foreshadowing/dependency matrix before any generated reference sheet.
2. Establish the draft visual bible and representative style proof.
3. Character model sheets, canonical outfit and expressions in that style.
4. Each recurring location: labeled layout map and master wide establishing view, then consistent directional views.
5. Props and attachment relationships (e.g. pole and mounted speaker), reference sheets with stable IDs and matching materials/design treatment.
6. Optional lighting/weather state variations **without changing geometry or visual style**; complete G3 review.
7. Finish G4–G6 before production shot images.

## Choose the shot count from the story

Use [story-driven image planning](../instructions/shot-planning.md) before final-shot generation. The agent decides the count from the complete narrative and the selected part's action, emotions, discoveries and reveals. An interesting opening, readable progression and earned ending matter more than a numeric quota. Combine redundant coverage; split a necessary action/state change or reaction that one still cannot carry. Dialogue does not require a new image for every line, and a camera move does not replace a missing story beat.

Keep the source-bound `image_planning` record in `shots.json`, following [the example](../templates/image-planning.example.json): one overall count/pacing rationale and an ordered purpose/entry reason for each written shot. Check holds against measured speech and actual preview playback, rather than an equal-duration grid. Record final story images separately from shared references/reused files/repairs. No fixed image count or extra approval is introduced; artistic engagement still requires actual judgment.

## Per-shot prompt compiler structure
- **Identity:** part/shot ID, one-sentence narrative purpose and exact narration interval.
- **Style lock:** approved `style_id` and `style_revision`, visual bible path, applicable treatment rules and any approved scene-specific variation.
- **World lock:** location ID/version, precise camera compass direction or local axis, spatial anchor points and persistent landmark positions.
- **Characters:** IDs, appearance, costume state, expression, pose, on-screen position and relationships.
- **Props:** IDs, fixed coordinates/mount orientation, active story state; show required foreshadowing where actually visible.
- **Composition:** wide/medium/close, foreground/midground/background, focus and negative space, eye line.
- **Camera framing:** static hold or G4-authored gentle zoom/pan, story reason, safe start/end poses, timing fractions and protected normalized boxes. Compose a single full-frame still for the whole path, with adequate source resolution and subtitle space; see `12-camera-motion.md`.
- **Atmosphere:** time of day, weather, lighting, palette, continuity from adjacent shots.
- **Avoid:** violations of the chosen style, changed architecture, misplaced props, mirrored layout, unintended anatomy/duplicates, unreadable text, wrong outfits and inconsistent aspect ratio. Add concrete style-specific defects; never prohibit the requested style through a copied negative prompt.
- **References:** attach actual approved images if provider supports it. Never assume text-only prompts guarantee continuity.

## Image production
Produce one shot at a time, save original provider output, record model/version/seed if supported, resize/fit to the approved timeline dimensions without cutting narrative essentials, and QC immediately. Keep image filename `shot_001.png` etc. Camera movement is optional authored framing over a still, governed by `12-camera-motion.md`; do not ask image generation to draw motion frames or blur. Default to static when no move is recorded. Cuts remain direct cuts; the renderer does not implement transition fades.

## Image acceptance
Check style ID/revision and the visual bible's acceptance criteria, reference matching, character identity, scene geography, object placement, story-time state, expression, focal narrative detail, artifact absence, crop and visual-to-narration correspondence. For moving frames, verify the actual protected details and margins throughout the path; source aspect must match delivery and the largest crop needs enough detail. Record the criteria checked, result, failed detail and repair decision in the shot QA log. Compare adjacent images and recurring entities across parts, not only each image in isolation. If failed, write a targeted repair prompt and retry; after three provider failures to maintain the required style or geometry, stop and propose concrete alternatives rather than silently accepting.
