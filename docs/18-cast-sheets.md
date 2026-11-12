# Cast sheets and character revisions

The cast profile is the written authority; inspected images are its visual reference. A PNG should communicate identity, proportions, wardrobe, expressions and poses clearly. Keep biography, story role, protected traits and event history in the companion profile instead of squeezing paragraphs into an unreadable image. Every shot receives the written character document and the actual registered reference images.

## Author the complete cast from the source

Read the whole story and its protected choices first. Author `world/cast.json`, schema version 1, with a `characters` map keyed by stable `CHAR-###` IDs. Use `templates/cast-profile.example.json` as a structural example, not a default cast. Include:

- Name, exact story role/relationships/history, age/life stage, design type and personality.
- Face/head, hair or surface features, distinguishing details, proportions, relative height/scale, silhouette and habitual posture.
- Clothing, material/color and accessories; separate stable identity anchors from event-driven changes.
- The selected style ID and exact revision, including its real anatomy and expression system.
- Useful `views`, named `expressions` with observable performance descriptions, named `poses` for the story actions, and actual `state_variants` when needed.

Human, non-human and abstract designs remain valid. Mark inapplicable human features honestly; do not impose realistic anatomy on a simple-figure medium. Give principal characters distinct identities, not renamed copies of one generic lead. Choose only views/actions the source needs; a quiet one-scene character does not need every possible turnaround.

Apply the profile through the source-bound batch path:

```powershell
python tools/studio.py prepare stories/my-story --snapshot > cast-bundle.json
python tools/studio.py prepare stories/my-story --file cast-bundle.json
```

Put the actual `world/cast.json` object in the bundle's `artifacts`. Preparation generates `world/characters/CHAR-###.md` and synchronizes the character registry's canonical path, revision and style ID. Do not separately author conflicting character Markdown. Draft profiles can be refined through preparation; changing an inspected design uses the actual request/revision path below. Previous bytes are preserved by the planning/revision records.

## Generate a useful, legible sheet

Use a restrained neutral board, consistent scale/light, clear margins and separated study groups. Keep face, hair, anatomy/proportions, wardrobe materials/colors and accessories identical between views. Use readable full-body identity views, close face studies and distinct requested action poses. Keep needed hands, feet and costume details inside frame. Short character/view labels are sufficient; no decorative scenery, crowding, arbitrary outfits, tiny text or invented alternate identities.

```powershell
python tools/studio.py images stories/my-story reference --entity CHAR-001
```

The default `complete` request includes the authored requirements. If the board would be too dense, use focused requests without changing the character identity:

```powershell
python tools/studio.py images stories/my-story reference --entity CHAR-001 --sheet identity
python tools/studio.py images stories/my-story reference --entity CHAR-001 --sheet expressions
python tools/studio.py images stories/my-story reference --entity CHAR-001 --sheet poses
```

`--sheet variants` is available only for actual requested state variants. These compile/queue requests; the agent still starts the real request immediately before the authorized image tool, imports its actual result, inspects it and resumes. Calls share the existing budget/cap; splitting does not authorize extra expense. There is no fixed resolution promise. If the returned face/prop details are too small, fail that concrete readability check and repair the affected sheet within scope.

The image bridge attaches the exact selected treatment, available current identity sheets and, after a revision, the immediately preceding identity reference. It labels each image's role. Preserve all earlier references for history; do not mix every historical design into the next generation request. Gallery treatment examples cannot count as story-specific cast identity sheets.

## Inspect and record actual coverage

After importing real images, generate a draft inspection record:

```powershell
python tools/studio.py cast stories/my-story review-template --character CHAR-001 --images references/characters/request-id/result.png > cast-review.json
```

The template captures the current `design_version` and exact `image_sha256` values. It is **pending**, with empty notes/checks and null coverage; it approves nothing. View the actual pixels, compare them with the profile, selected treatment and relevant reference identity, and fill the record from that inspection.

A passed review must cover `identity`, `style`, `wardrobe`, `expressions`, `poses` and `readability`, with reviewer and concrete notes. `coverage.views`, `coverage.expressions`, `coverage.poses` and any `coverage.state_variants` map every requested name to the actual inspected image that demonstrates it. One image can cover many requirements; a shared cast comparison image can serve multiple characters only with separate genuine coverage records for each. Failed/partial work stays failed or pending.

```powershell
python tools/studio.py cast stories/my-story review --file cast-review.json
python tools/studio.py cast stories/my-story status
```

Recording checks current design/image hashes, registers the inspected paths and preserves earlier inspection records. Changed profile/style/image bytes stale the review. Status exposes the current profile, design-version tokens and actual pending requests. A process exit, file existence or `status: reviewed` string does not prove complete coverage. Actual visual inspection remains agent work; Fast does not add another routine human cast-sheet approval.

## Bind the shots and world state

Use structured `character_ids`, `location_id` and `prop_ids` in the written shot records. Character IDs inside prose alone do not attach identity references. Explicitly declare an empty cast/prop list when appropriate; explain a character-free frame with `no_characters_reason` and a location-independent frame with `location_note`. Use `offscreen_character_ids`/`offscreen_prop_ids` for explicitly mentioned but unseen entities.

Record finite `story_time` and `entity_states` for visible identities with visual history. Assert every known state field, not only convenient ones; the existing event ledger checks its values against the source chronology. Track planned costume, age, injury, weather and prop changes instead of silently replacing identity or geometry. Returning location layouts, landmarks, screen direction and important prop references still need their authored bibles/maps and actual image inspection.

Reference requests need a complete current character profile. Final-image/production/render/master/release paths require the visible cast's current inspected sheets in Fast and Strict. Missing bindings, profiles, coverage, files or stale styles cannot be bypassed by omitting optional-looking fields. Legacy active projects must supply this data when producing with the updated tools; the monitor reports missing data without silently migrating a story or fabricating references. Already running older producers are not interrupted merely to upgrade them.

## Request and apply a character change

Open **Cast sheets** in the monitor. Inspect current/earlier sheets, the full profile, coverage, linked shot count and revision history. **Request change** records the actual user's notes against the displayed design version. It queues work for the production agent; it does not edit canon, regenerate assets, spend a provider budget or approve a design. A stale form requires review of the newer design. The local endpoint accepts only a same-origin, token-bound JSON request and verifies the story's actual branch.

Chat requests can use the same record path with the actual request quotation and source:

```powershell
python tools/studio.py cast stories/my-story request --character CHAR-001 --change "ACTUAL REQUEST" --source "ACTUAL SOURCE" --base-version CURRENT_DESIGN_VERSION
```

`studio next` exposes pending requests as agent work; unknown provider outcomes are reconciled before a new design revision. Assess the requested scope against the story's protected choices, then author the complete changed profile. Do not treat a hairstyle request as permission to rewrite the role, premise or story. A conflicting request or new cost/provider/upload scope still needs its actual decision.

```powershell
python tools/studio.py cast stories/my-story revise --character CHAR-001 --file revised-character.json --request REQUEST_UUID
```

Revision verifies the exact request base, advances the character revision, generates matching Markdown and preserves earlier JSON, documents and reference paths under `production/cast-revisions/`. A request against a legacy character can introduce its full structured profile in this transaction. The new sheet remains unverified; previous pixels and deliveries stay preserved. The receipt identifies linked shots to inspect. Generate/inspect the revised reference, then inspect and rebuild only affected images, timing/presentation and any included full cut. A changed preview follows the existing real preview decision; no automatic approval or automatic provider retry occurs.

Production Progress includes a project-wide **Cast sheets** step with actual registered/verified counts. A loader appears only for a submitted reference request; failed/unknown outcomes, missing profiles, pending inspections and changes remain distinct. Whole-film ETA is not inferred from cast counts. The Cast sheets table and drawer refresh with the normal polling cycle. Export includes current cast profiles, inspection evidence, current/preserved references and revision receipts.
