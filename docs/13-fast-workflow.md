# Fast workflow

New projects use **Fast** mode: configure the work once, let the agent create and inspect a complete preview, review that preview, then finish and export. Strict mode keeps the individual G1–G6 signoffs. Projects without `production/workflow.json` remain Strict; nothing is silently migrated.

Each new story is initialized on its own `story/<safe-title-slug>` branch from the studio base. When a user pastes a story after cloning, the agent uses its supplied title and runs `studio init` automatically before project writes, then continues the workflow below. No extra branch approval is needed. `studio resume stories/<safe-title-slug>` returns to an existing committed story. See [branch behavior and recovery](15-story-branches.md).

## Ask only for decisions

Reuse preferences already stated in chat or saved in a selected preset. Bundle missing material choices into one message: output and length; language/performance; look/frame; tools, budget and uploads. Ask about protected story choices only when unclear. Explicitly flexible length is valid; never invent a fixed runtime. For story-only work, skip film questions and media production. A request to use a preset and produce the film can provide authorization if it actually covers the displayed scope; do not ask again for the same decision.

The user configures `production/workflow.json`, intake, voice preferences and project settings together. `studio review` writes a concise view of the current choices, missing decisions and remaining agent work. A preset saves preferences and exact selected treatment snapshots, never a source story, characters, gate signoffs or permission to spend/upload for another project.

```powershell
.\.venv\Scripts\python.exe tools/studio.py init "My Story" --preset default --task film
.\.venv\Scripts\python.exe tools/studio.py configure stories/my-story --file configuration.json
.\.venv\Scripts\python.exe tools/studio.py review stories/my-story
```

The configuration file may contain `workflow`, `intake`, `narrator`, `settings` and `style_references`, following the example in `templates/fast-configuration.example.json`. Existing answers are preserved when scaffolding from a preset. Explicit configuration edits replace the supplied fields. Missing voice/style/duration choices remain unanswered until stated or delegated; examples are not hidden preferences.

## Deliver the chosen format

“One full-length video” sets intake `mode: single`: write and produce a complete film using only `part_001`, with its intended ending. Do not ask the format again, split it into separate releases, add part teasers or invent a duration. Ask only any material settings still missing.

For a new part-by-part request, use `mode: parts` and the new intake default `continuous_edition: true`: deliver the individual part videos and one continuous full-film cut. Explicit parts-only requests set it false. The preference is saved with presets, displayed in the configuration and bound to its authorization; it does not create an extra output in single mode. Older projects without this field retain their recorded scope until deliberately configured.

Write the entire story in explicit part sections in the authoritative final-story file before production. Plan an engaging opening, meaningful local progress, an earned ending and the next part's payoff of the continuation promise for every nonfinal part. The final part reaches the overall ending. Preserve the source plot and protected choices; major creative changes still need an actual decision. Then detail and produce each part in order, using the same cast/world. Detailed shots for later parts can remain progressive; their actual story narrative and boundary promises must already exist.

Design each character for the role's history, personality, age/design type, relationships and acting needs. Record observable identity anchors and role reasons in `world/characters/CHAR-###.md`; compare the cast and inspect representative emotions/poses in the chosen medium. Preserve these identities across parts and the full cut, with state changes tied to story events. This is normal agent design/inspection work inside scope.

When included, continue through actual continuous-film assembly after the parts. Use [the full-cut edit plan](../templates/story/creative/continuous-edit.md), measured source ranges, clean stems, rebuilt joins/audio/subtitles, an actual full-cut preview and its own playback QA/manifest. The part coordinator does not assemble this automatically: the agent executes and records the local edit/render work. Include the full film in delivery rather than offering it as an unfinished follow-up. Bundle preview decisions for actually shown outputs when practical; no extra configuration approval is needed for the already included edition.

## Monitor without interrupting production

`studio monitor --workspace <checkout>` opens a read-only local dashboard, including actual preview playback, measured timeline tracks, voice revisions and pending decisions. It can run in a separate worktree. Updated production tools emit real stage/clip/FFmpeg counters and heartbeats; older producers remain visible as recorded activity. Use `studio progress` for meaningful actual creative milestones, not simulated progress. User waiting and agent work remain distinct. Estimated ranges require measured pace or successful history and exclude unknown creative/provider/review time. [Setup, timeline behavior and telemetry limits](16-progress-monitor.md).

## One authorization, with limits

Record the actual user decision once the concrete configuration is ready:

```powershell
.\.venv\Scripts\python.exe tools/studio.py authorize stories/my-story --decision "ACTUAL USER AUTHORIZATION" --decision-reference "actual chat/source reference"
```

The placeholders are never permission. `production/delegation.json` records the real quotation/reference, source and configuration hashes, allowed tools, total spending cap, currency, upload providers and permitted sound-download hosts. The shared provider budget includes image reference/final requests and cloud speech together. Unknown provider outcomes require actual reconciliation; budget exhaustion or a new provider/upload route needs a real scope decision. HTTPS sound-source redirects must stay inside the allowed source hosts; speech API redirects are refused.

Changing source bytes, explicit intake choices, workflow scope, configured voice preferences, provider route or recorded runtime settings makes the authorization stale. An unset voice is delegated to the agent within the configured language/tool scope. Filling other previously unconfigured optional preferences, adding pronunciation entries, or updating review progress does not repeat authorization; explicit preconfigured choices stay bound. Updating technical render/mix/job settings or a verified price estimate inside the same authorized cap is execution work, not another scope approval. Generated shots, references, measured timing and internal QA do not invalidate it by themselves: those are the delegated work. Never mark G1–G6 approved to simulate Fast authorization.

[Speech provider selection](14-speech-providers.md) is part of the same configuration: Kokoro, Chatterbox, ElevenLabs, Inworld, Cartesia, a custom gateway or imported recordings. Explicit narrator/provider/model/cast choices remain bound; filling delegated cast roles or choosing their previously unset voices inside allowed tools/cost/upload scope does not repeat authorization. A custom external gateway endpoint must be included in the actual authorization. Do not force a paid service or switch providers on failure. Voice presets reuse provider/narrator choices and exact selected global voice snapshots; story-specific character-to-voice mappings are assigned for the new story. `speech.json` separates spoken turns from speaker IDs and supported directions.

Choose narration for the complete story using [the casting procedure](../instructions/voice-casting.md), actual representative listening and recorded role-fit reasons. Users can change any voice later. `studio voice set` records a bound voice change using the actual request/reference and amends only that choice inside a current authorization, preserving the original configuration/history and existing permitted story edits. It does not restart intake or authorize unrelated stale settings or new tools/uploads/budget. Unchanged speaker clips/images remain reusable; changed performances require current timing/mixes/previews and final playback. Presets save the effective current narrator without carrying story characters.

`minor_edits: delegate` permits small corrections covered by the actual configuration decision, preserving plot, voice, characters, major events, twists and ending. `ask` requires issue-specific permission. Major creative changes always need a decision before editing. Keep `creative/original.md` exact, write the complete revision and change log, then record its actual basis:

```powershell
.\.venv\Scripts\python.exe tools/studio.py record-revision stories/my-story --scope minor --summary "Actual correction summary" --issue-ids AUDIT-001
```

For a major change or `minor_edits: ask`, add the real `--decision` and `--decision-reference`. The receipt binds to the exact revised bytes. A delegated receipt does not establish that an edit was truly minor; the agent must assess and document that honestly.

## Proportional editorial work

Read the entire source through the ending. Map scenes once and keep twelve internal checks in `continuity/story-ledger.json`: `plot`, `scene_continuity`, `characters`, `chronology`, `cause_effect`, `knowledge`, `world_rules`, `dialogue`, `clarity`, `setups_payoffs`, `pacing`, `emotion`. Record complete coverage and the final story hash. Do a focused cross-check of risky events, distant knowledge, opening/ending dependencies and proposed corrections. Full sources still get a full read; do not label a focused cross-check a complete second pass.

Set `review_coverage.full_read_complete`, `audit_areas_reviewed`, `focused_check_complete` and `checked_story_sha256` only after the actual work. `audit-issues.json` identifies both the original `source_sha256` and `final_story_sha256`, with concise assessment/verdict and evidenced findings. A material unresolved story decision blocks dependent production; an accepted residual issue needs the actual user quotation/reference. Preserve detailed evidence internally and present only meaningful findings, choices and limitations.

`review_pack.py <project> --audit` generates the concise Fast report. `audit: full` or `--full-audit` uses the full A–I procedure with real complete second-pass coverage. Choose full review for complex chronology, major revisions, difficult reveals or an explicit request; it is not a routine extra approval.

## Work continuously toward the preview

Prefer [batch preparation and resumable production](17-resumable-production.md). `studio prepare --snapshot` captures a source-bound base; `prepare --file` applies actual authored records together. `studio continue --part auto` checks readiness early, establishes shared style/recurring-cast references, reuses local work across image handoffs and carries the structured part plan's current story excerpt/state/payoff. An `actor: agent` packet is internal work, never another routine permission question. `actor: user` identifies the actual material configuration/cost or complete-preview decision. Real image tools, semantic inspection, listening and master playback remain explicit work; no gate is auto-approved.

Keep whole-story inventory, important state changes and future dependencies before image work. Scale references to actual shot needs: a recurring character, returning location or important prop may need a sheet/map; a one-off background detail does not automatically need every angle. Use a representative scene and short voice sample early when they resolve uncertainty, inside the authorized scope. Reuse a configured voice when language, model and actual quality remain suitable; fresh auditions are for a changed choice or a real performance problem.

Use [structured cast profiles and inspected sheets](18-cast-sheets.md) for visible characters. Author complete source-specific identity, wardrobe, expression and pose requirements; use only useful views and split a crowded sheet when necessary within the existing call cap. Record real per-character coverage against exact design/image hashes. The runtime rejects missing shot bindings and known-state omissions before visual production. Cast planning, generation and inspection remain agent work. Monitor change requests preserve earlier designs and are handled through `cast revise`, with genuine review/rebuild of affected work and no extra routine signoff.

Plan story boundaries and future dependencies for all parts, then detail the selected part. Follow [story-driven image planning](../instructions/shot-planning.md): the agent chooses images from narrative purpose, action/state changes, emotion and reveal order, records the count/pacing rationale and each shot's purpose/entry reason in `shots.json.image_planning`, and checks the real holds/preview after measured performance. No per-minute quota, equal-duration grid or routine shot-count approval applies. Fast stage checks require its actual written shots, not finished shot lists for every future part. Use `run --part part_001` for progressive multipart production. A complete single video still uses one part.

The agent executes queued image requests, imports real results, inspects each result, records genuine reviews and resumes. A queue message or missing listening record is an **agent action**, not an instruction to ask the user for another signoff. Rebuild only affected work. Independent sound planning/acquisition and visual preparation may proceed while other work is pending; do not run competing coordinators on one project. Existing speech/sound/frame caches remain active; digest reuse is limited to one operation and rechecks file metadata before reuse.

## Avoid unnecessary production work

Run `studio preflight <project> --live-local` before new speech/image production. It checks selected speech configuration, credentials by presence, English dictionary coverage and optional loopback Chatterbox `/info` metadata; it synthesizes nothing, downloads nothing and calls no cloud API. Repair setup once and reuse it. For a complete unchanged cached speech job, `run` verifies the inputs, assembled audio and clips and skips runtime startup entirely. New/changed/corrupt work still verifies its actual runtime.

Keep brief source/continuity/cast records proportional to the story. Batch canonical edits and generate readable views. Use core commands instead of writing one-off Python utilities for each film. Image generation and creative judgment remain real work; avoid unused reference sheets and excessive auditions. Parallel tool preparation is useful only where continuity dependencies and authorization permit it.

For shots that follow utterances or an action after a line, set `shots.json` to `"timing_mode": "speech_turns"`. Keep its complete written narration and give later shots `start_anchor` values such as `{"utterance_id":"UTT-002","edge":"start"}`. A blackout after that line uses edge `end`; a speech-free final hold is allowed. `audio_tail_seconds` determines the measured end hold. Sound start/end anchors accept `utterance_id`, `shot_id`, or `{"narration":true,"edge":"end","offset":-0.4}`. The builder uses real chunk/word timestamps and validates source coverage; it does not estimate speech time. Legacy word-based and explicitly manual timing still work.

Review metadata does not change the media cache. Actual sound cues, speech bytes, images, captions, camera moves and selected render settings do. Sound-only changes with identical picture/caption timing copy the existing encoded video stream and replace audio; altered picture/timing/captions get a full render. Technical measurements/contact sheets reuse verified byte hashes, while artistic reviews and playback are never auto-passed. The mix is checked for lost non-silent sound tails before preview encoding; unsupported compressed-source signal checks remain explicit listening work.

When the built-in image tool has no reported price, the user may explicitly accept an unknown charge with a finite call cap. Optional workflow scope example:

```json
"builtin_images": {"max_calls": 14, "unreported_cost_accepted": true}
```

This is a separate explicit exception for capped built-in usage, not a zero-dollar price or a promise that all work fits a zero-cash total. Display it with the monetary/tool/upload scope and record the real authorization. Do not enable it for a user who requires a hard all-tools monetary limit. Reference/final requests and known retries consume calls; unknown outcomes block new calls. Keep `estimated_cost` and `actual_cost` null when unreported. Priced provider requests retain the shared monetary ledger. Without this explicit scope, a missing price remains blocked.

Use `studio images <project> queue --part part_001 --shot SHOT-001` (or `reference --entity STYLE-001`), then `start --request <queued-json>` immediately before using the real image tool. Import the result with `import --request ... --image ... --provider ...`; inspect it and continue. Queueing or starting alone does not generate an image. Known failures go through `failed --outcome-known`; an uncertain result must be reconciled instead of retried.

Fast complete previews can contain rights-verified sounds pending listening. Such work remains a draft; failed QA/unknown rights still block. If the agent cannot hear, casting stays provisional until the user actually listens to the complete preview. Bundle voice/sound acceptance, captions and any uncertain-word checks into that one question. After that real decision, `approve-preview ... --listening-reviewed` records an exact mix/source/cue-bound listening receipt without falsely passing unused sound-file ranges. It cannot pass alignment or image checks automatically. Changed mixes/sources/cues stale that evidence; Strict keeps its original audio approval boundary.

## One preview decision, then release

```powershell
.\.venv\Scripts\python.exe tools/studio.py run stories/my-story --part part_001 --profile preview
.\.venv\Scripts\python.exe tools/studio.py approve-preview stories/my-story --part part_001 --decision "ACTUAL PREVIEW DECISION" --decision-reference "actual chat/source reference"
.\.venv\Scripts\python.exe tools/studio.py run stories/my-story --part part_001 --profile final
```

Present the actual preview and record the user's real decision. The decision binds to the selected part’s actual presentation, preview, image/sound bytes and subtitles. Unchanged presentation does not need a new user decision because another part or internal canonical documentation progressed; current story/continuity and image-reference checks are still enforced separately. Changed content needs a changed preview; marking an inspected alignment range reviewed does not create an approval loop when presentation is unchanged. Direct master rendering and export also enforce this boundary.

Image identity/geography/state/crops, audio terms/listening, uncertain word alignment, technical checks and full final playback remain mandatory **agent work**. Do not automatically pass them or ask the user to perform every check. Record only real inspection with existing `image-review` and `playback-review` tools. A user preview decision is distinct from the agent's final playback record. Export still refuses absent/stale playback evidence and never overwrites a delivery revision. No automatic publishing/uploading beyond configured tool scope is introduced.

## Save a preference preset or choose Strict

```powershell
.\.venv\Scripts\python.exe tools/studio.py preset save my-usual-look --from-project stories/my-story
.\.venv\Scripts\python.exe tools/studio.py init "Next Story" --preset my-usual-look
.\.venv\Scripts\python.exe tools/studio.py configure stories/my-story --mode strict
```

Use `preset list`, `preset show <name>` and explicit `--replace` when updating a saved preset. Selected treatment snapshots retain their exact bytes and source hashes; they never import the example's people, props or plot. Strict uses the detailed procedures in `docs/01-workflow-and-approvals.md` and `instructions/story-audit.md`. Fast grants are never converted to Strict gate approvals.
