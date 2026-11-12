# Studio command reference

## Cast sheets and revisions

Author `world/cast.json` through `prepare`; its generated character Markdown is a readable view of the canonical profile. `studio cast <project> status` exposes current designs and request-base versions. `images <project> reference --entity CHAR-001 --sheet complete|identity|expressions|poses|variants` compiles a full or focused sheet request inside the existing tool/call/budget scope. It does not itself generate pixels.

Use `cast <project> review-template --character CHAR-001 --images <actual-project-image-paths>` to capture a pending inspection with current design and image hashes. Inspect the real images, fill every required view/expression/pose/variant coverage entry and the actual checks/verdict/reviewer/notes, then record it with `cast <project> review --file <record.json>`. This is agent inspection, not another Fast user approval. Missing cast profiles, identity sheets, coverage or structured shot/state bindings block new visual production, including direct runner calls. [Detailed contract and examples](../docs/18-cast-sheets.md).

The Cast sheets UI records explicit, version-bound character-change requests only. The agent uses the actual request with `cast <project> revise --character CHAR-001 --file <complete-profile.json> --request <UUID>`. Previous profiles/sheets remain preserved, changed designs require new inspected references, and affected shots/presentation are checked before delivery. The monitor cannot directly edit canonical data, launch providers or approve anything; other write routes remain blocked.

Use `studio.py prepare <project> --snapshot`, author the canonical records in its bundle, then `prepare --file <bundle>` for batch planning. `studio.py next <project>` reads a focused current work packet; `continue <project> --part auto` performs reusable local work and advances through genuine image/inspection/preview/playback/export boundaries. [Resumable workflow and part continuity](../docs/17-resumable-production.md).

## Fast configuration and preview

New projects default Fast; existing projects without `production/workflow.json` remain Strict. Read [the Fast contract](../docs/13-fast-workflow.md). G1–G6 descriptions below are the Strict reference. Both modes retain genuine image, sound, alignment and playback checks.

```powershell
.\.venv\Scripts\python.exe tools/studio.py init "My Story" --preset default --task film
.\.venv\Scripts\python.exe tools/studio.py configure stories/my-story --file configuration.json
.\.venv\Scripts\python.exe tools/studio.py authorize stories/my-story --decision "ACTUAL USER AUTHORIZATION" --decision-reference "actual source"
.\.venv\Scripts\python.exe tools/studio.py run stories/my-story --part part_001 --profile preview
.\.venv\Scripts\python.exe tools/studio.py approve-preview stories/my-story --part part_001 --decision "ACTUAL PREVIEW DECISION" --decision-reference "actual source"
.\.venv\Scripts\python.exe tools/studio.py preset save my-usual-look --from-project stories/my-story
```

The quote placeholders are not permission. Fast records one real scoped authorization and one real preview decision; it creates no gate approvals. `configure --mode strict` selects Strict. `--task story` or `storyboard` prevents media production. `preset list/show/save` reuses preferences, never permission. `record-revision` records delegated minor-edit scope or actual issue-specific permission. `review_pack.py --audit` generates the concise Fast report; `--full-audit` requires the real full procedure.

Selected-part checks permit unfinished future shot lists; whole-story dependencies remain current. Master/export needs the current preview decision plus actual image/alignment/playback evidence. `next_actions` distinguishes user decisions from agent work: a queued image or listening check is not a signoff request. Hash reuse stays within one operation, with file metadata checked on reuse; output bytes still control cache validity.

Use `studio preflight <project> --part part_001 --live-local` before new media work. It performs local configuration/dictionary checks and an optional loopback model-info request, with no synthesis, cloud calls or downloads. Cached speech can resume offline. [Measured anchors, cache/remux behavior, one-preview listening and capped built-in images](../docs/13-fast-workflow.md#avoid-unnecessary-production-work).

`studio approve-preview <project> --part part_001 --decision "ACTUAL DECISION" --decision-reference "ACTUAL SOURCE" --listening-reviewed` records real complete-preview listening when that was explicitly included in the human's decision. It does not auto-pass images, uncertain words, rights or unused sound ranges.

`studio images <project> queue --part part_001 --shot SHOT-001 --estimated-cost <known-price>` queues a request. Omit the estimate only under an actual explicit capped built-in/unreported-cost authorization. Use `reference --entity STYLE-001` for a canonical proof, `start --request <file>` at the actual tool-call boundary, then `import --request <file> --image <actual-output> --provider <actual-provider>`. Unknown outcomes cannot automatically retry. All creative inspection remains required.

Intake `mode: single` means one complete film using only `part_001`. For new multipart requests, `mode: parts` with `continuous_edition: true` includes individual videos and a continuous full-film cut; use false for an explicit parts-only request. The field is a saved preference and is bound to authorization when it affects multipart outputs. `studio review` shows the requested deliverables. A legacy missing field does not silently add a full cut. Write the complete part narratives and continuation/payoff plan before generating media, then produce parts in order. `run` processes part timelines; the agent also executes and records the configured full edit/assembly using `creative/continuous-edit.md` and local media tools, with a separate full-film clock and genuine preview/playback evidence.

Use `.\.venv\Scripts\python.exe tools/studio.py <command>` from the studio root. `studio.ps1` is an optional launcher. These small CLI helpers implement the existing document-first workflow; Codex performs the real editorial read, creative decisions, image-tool execution and inspection.

## Live progress and preview monitor

Build the React frontend once with `npm --prefix apps/monitor ci` and `npm --prefix apps/monitor run build`; Node 22.12+ is needed for that build. The Python command then serves the compiled interface and read-only API together, with no Node service required.

```powershell
.\.venv\Scripts\python.exe tools/studio.py monitor --workspace . --port 8765
.\.venv\Scripts\python.exe tools/studio.py status stories/my-story --json
.\.venv\Scripts\python.exe tools/studio.py progress stories/my-story --stage shots --state running --message "Measured 4 of 6 planned shots" --completed 4 --total 6 --unit shots
```

The loopback dashboard is read-only and can watch another checkout plus related worktrees. It streams actual previews and measured timeline tracks, shows selected/generated voices and revision requests, and distinguishes user preview decisions from agent work. Updated local jobs emit heartbeats, real clip/FFmpeg counters and cache events. Older producers show recorded activity without claiming live liveness. ETA ranges require actual pace/history; the page never starts production or records approval. See [the complete monitor guide](../docs/16-progress-monitor.md).

## Speech provider and cast selection

Choose [Kokoro, Chatterbox, ElevenLabs, Inworld, Cartesia, a custom gateway or imported recordings](../docs/14-speech-providers.md). `audio/narrator.json` stores provider/model/default voice and provider setup; `cast` assigns each story's speaking character. `parts/part_###/speech.json` holds the exact spoken turns, speaker IDs, supported directions and pauses, matching narration.txt. The same engine is used by `run` and `speech`.

```powershell
.\.venv\Scripts\python.exe tools/studio.py providers
.\.venv\Scripts\python.exe tools/studio.py doctor --project stories/my-story
.\.venv\Scripts\python.exe tools/studio.py speech stories/my-story --part part_001
.\.venv\Scripts\python.exe tools/studio.py speech stories/my-story --part part_001 --purpose audition --text-file stories/my-story/audio/audition.txt --output stories/my-story/audio/auditions/voice-r1.wav
.\.venv\Scripts\python.exe tools/studio.py speech stories/my-story --purpose audition --speaker CHAR-001 --text-file stories/my-story/audio/audition.txt --output stories/my-story/audio/auditions/character-r1.wav
.\.venv\Scripts\python.exe tools/studio.py voice status stories/my-story
.\.venv\Scripts\python.exe tools/studio.py voice set stories/my-story --speaker NARRATOR --voice ACTUAL_VOICE_ID --reason "Actual story-specific selection reason"
```

The selected provider must be inside actual tool scope; cloud routes also require configured upload scope, environment credentials, a verified current rate/currency and remaining shared provider budget. No fallback selects another provider. Explicit choices are bound; new delegated cast voices inside scope do not repeat authorization. Chatterbox uses an optional separately prepared loopback server/checkpoints, with no inference-time downloads. Unknown cloud outcomes block automatic retries; `speech-resolve` records actual evidence/cost and optionally imports recovered audio. See the provider guide for setup, supported controls, custom endpoint contract and exact recovery examples. Existing `tts_kokoro.py` stays a Kokoro-specific compatibility tool.

Follow [story-specific casting](../instructions/voice-casting.md) and keep the performance brief, shortlist, actual listening evidence and choice rationale in `audio/voice-plan.json`. `voice set` makes no provider calls. Replacing a bound choice adds `--decision "ACTUAL USER CHANGE REQUEST" --decision-reference "actual source"`; that request amends only the voice choice within a current Fast scope and retains original authorization/history. It cannot authorize unrelated stale changes or new tool/upload/budget scope. Exact prior profiles and affected-part records support later changes without restarting intake; regenerate affected speech/timing/mixes/previews and reuse unchanged assets. `speech --purpose audition` supports speaker/provider/voice/model overrides without changing the chosen profile.

## Start and resume

```powershell
.\.venv\Scripts\python.exe tools/studio.py doctor
.\.venv\Scripts\python.exe tools/studio.py sample
.\.venv\Scripts\python.exe tools/studio.py init "My Story" --style "Painted cinematic anime" --story-file C:/stories/source.txt
.\.venv\Scripts\python.exe tools/studio.py resume stories/my-story
.\.venv\Scripts\python.exe tools/studio.py add-part stories/my-story part_002
.\.venv\Scripts\python.exe tools/studio.py review stories/my-story
.\.venv\Scripts\python.exe tools/studio.py run stories/my-story --profile preview
.\.venv\Scripts\python.exe tools/studio.py run stories/my-story --part part_002 --stages mix,render,qa
```

`init` creates and switches to `story/<safe-title-slug>` from the studio base, then publishes `stories/<safe-title-slug>/` with exact source bytes and `production/git.json`. Title agreement precedes scaffolding. Free-form style and repeatable `--style-reference <image>` are optional draft inputs. Global examples are never inherited automatically. Unicode titles get safe stable paths. Existing projects/branches are never overwritten. The selected source and its staged bytes survive a base switch; unrelated changes block the switch without being discarded. `--base <committed-studio-ref>` selects a different studio base. `resume` returns to a committed existing story, including when its folder is absent on the current branch. See [story branches](../docs/15-story-branches.md). Git and standard Python are sufficient for initialization; setup of media dependencies can follow it.

On a fresh Windows checkout use `python tools/setup_studio.py`; exact dependency versions are in `requirements.lock.txt`. `--verify-only` verifies binaries/models/packages and writes runtime manifests. Setup downloads free public runtime files; it does not call media providers. Project settings override global `studio.json` where documented, with gate invalidation when approved settings change.

`run` requires G1–G6 and canonical consistency. Supported local stages: narration, alignment, timeline, sound, mix, subtitles, images, render, qa. Only request a later stage once its prerequisites exist. A missing prerequisite fails clearly or produces a waiting action. `--force` rebuilds selected local stages; it does not bypass approvals or repeat paid image calls. Exact stage input/code/parameter/output hashes control reuse. One narrator instance serves the batch; unchanged chunks, sounds and prepared frames are reusable. Record files are atomic and local job failures/timings survive interruption. Separate simultaneous runs on the same project are unsupported; finish or stop one runner before resuming.

## Editorial records and gates

| Tool | Responsibility |
|---|---|
| `review_pack.py <project> [--audit]` | Generate intake, full audit and compact decision views from completed canonical records |
| `project_records.py <project> check` | Current gates, changed snapshots and continuity issues |
| `project_records.py <project> refresh` | Mark affected gates/jobs stale and write entity/shot/audio impact map |
| `project_records.py <project> record --gate G1 --revision r1 --decision <actual quote> --decision-reference <actual source>` | Record a real gate decision after required review; never infer approval |

Read the full story, complete all twelve audit areas and scene/second-pass records, present the A–I report, then obtain issue-specific permission before revising. No script audits or rewrites a story automatically. Gate definitions and preconditions are in `docs/01-workflow-and-approvals.md`. `approvals.json` is authoritative; Markdown is generated.

## Speech, timing and sound

| Tool | Responsibility |
|---|---|
| `tts_kokoro.py --text-file <txt> --output <wav> [--purpose audition]` | Approved local CPU voice, sentence caching and measured chunk manifest |
| `align_audio.py <wav> [--profile <narrator.json>]` | Actual English word alignment and explicit uncertainty; sentence cache |
| `align_audio.py <wav> --review-indices <indices> --reviewer <name> --review-notes <actual notes> [--corrections <json>]` | Preserve raw alignment and add a checksum-scoped manual overlay |
| `build_timeline.py <project> --part part_001` | Match exact approved speech to real words; derive cuts/subtitles and shot-anchored cues |
| `generate_sound.py --kind wind --duration 12 --output <wav> [--purpose audition]` | Limited streamed procedural wind/rain-like textures, hums or tones with provenance |
| `audio_assets.py <project> add/search/loop/review` | Import/download actual audio, retain evidence, search tags, prepare crossfaded loop revisions, record real rights/listening review |
| `mix_audio.py <timeline> [--dry-run] [--profile final]` | Cue placement, source coverage, unique input reuse, fades, speech ducking, exact duration and two-pass loudness |
| `validate_timeline.py <timeline> [--check-assets]` | Schema/coverage/format/cues/assets; no artistic claims |
| `make_srt.py <timeline> [--output <srt>]` | Export the timeline subtitle clock |

Final speech settings come from G5-approved `audio/narrator.json`; conflicting CLI overrides fail. Earlier auditions need explicit tool/expense authorization. Automatic batch narration uses the locked narrator; separately performed dialogue/multiple speakers need an agreed voice plan and compatible imported performance/alignment rather than an implied multi-speaker feature. English alignment is exercised; unsupported languages need a suitable aligner/manual workflow.

`audio/requirements.json` defines acquisition routes; the registry starts unverified/pending. Mixer use requires matching SHA-256, actual source metadata, verified usage evidence and passed listening. A loop's crossfade is a technical preparation, not proof its seam sounds natural. `shots.json.timing_mode: "manual"` preserves explicitly inspected silent/action timing; automatic timing refuses text mismatches.

## Image requests and actual imports

```powershell
.\.venv\Scripts\python.exe tools/image_jobs.py stories/my-story reference --entity STYLE-001 --estimated-cost 0 --currency USD
.\.venv\Scripts\python.exe tools/image_jobs.py stories/my-story queue --part part_001 --shot SHOT-001 --estimated-cost 0 --currency USD
.\.venv\Scripts\python.exe tools/image_jobs.py stories/my-story import --request <request.json> --image <actual-result.png> --provider <actual-provider>
```

Zero is valid only when the actual authorized cost estimate is zero; never invent a price. Reference work requires G1/G2, completed whole-story dependencies, written specifications and its explicit tool/budget/upload authorization. Final requests require G1–G6 and real approved canonical images. Prompts combine written shots, camera geography, entity specifications, state and checked reference paths.

Each queued record contains an exact `image_gen.imagegen` tool request. The agent reads the imagegen skill, inspects every target/reference, executes the actual available approved tool, reviews the output and imports its file. Queueing itself makes no provider call. Imports validate real pixels, preserve an immutable version/checksum and leave unreported model/job/cost null. Record actual metadata when returned. Requests reserve cumulative budget, require explicit external-upload scope and are idempotent. Use `failed --request <file> --reason <actual error> [--outcome-known]`; an unknown outcome or three failures requires attention before another call.

## Review, render and deliver

```powershell
.\.venv\Scripts\python.exe tools/studio.py image-review stories/my-story --part part_001 --shot SHOT-001 --verdict passed --reviewer <actual-reviewer> --notes <actual-inspection>
.\.venv\Scripts\python.exe tools/studio.py run stories/my-story --profile final
.\.venv\Scripts\python.exe tools/studio.py playback-review stories/my-story --part part_001 --reviewer <actual-reviewer> --notes <actual-full-playback>
.\.venv\Scripts\python.exe tools/studio.py export stories/my-story --part part_001 --revision r1
```

`render_part.py <timeline> --output <mp4> [--profile preview|final] [--srt <srt>] [--dry-run]` renders stills with direct cuts and optional G4-authored `motion` at approved frame/FPS. Missing motion remains static. `camera_motion.py` validates bounded static/zoom_in/zoom_out/pan plans, protected regions, easing and timing fractions, then compiles the continuous FFmpeg framing filter. Moving shots require the delivery aspect; nearest-neighbor pixel-grid projects keep static holds. Common-size cached stills prevent decoder resolution changes from dropping holds; moving parts prepare at twice render dimensions and read long filters from a file using the configured FFmpeg 9.x `-/filter:v` option. Video start, duration, frame count, audio and output hashes are checked before replacing an output. Preview/master are separate. See [camera-motion instructions and examples](../docs/12-camera-motion.md).

`quality.py <timeline> --video <mp4> --sheet <jpg>` writes paginated comparison sheets and measured technical QA. It flags corrupt/undersized images, aspect issues, camera crop-resolution/short-move concerns, uncertain alignment, black ranges and audio measurements. Artistic identity/geography, real protected-detail visibility, motion smoothness/sharpness/reveal timing/subtitle safety, sound match and full playback still require direct review. Image reviews include the written motion plan and current canonical context; playback/export checks actual image, narration, mix, subtitle and master bytes. `--accept-warnings` is for warnings actually inspected and accepted. Export creates a new `delivery/<part>-<revision>/` with manifest and portable source paths; it refuses stale/missing reviews or overwriting a delivery revision.

## Verification and technical fixture

```powershell
.\.venv\Scripts\python.exe -B -X utf8 -m unittest discover -s tests -v
.\.venv\Scripts\python.exe tools/studio.py sample
```

Tests use isolated synthetic fixtures. Actual FFmpeg checks skip only if the binary is unavailable. The neutral sample writes actual CPU speech, word times, sound, SRT, preview/master and technical QA under `.runtime/checks/technical-demo/`, with warm-cache timings. Its existing example images and unreviewed sound/word ranges are explicitly technical fixtures. `--technical-check` on the mixer is confined to `.runtime/checks`, cannot bypass a real story's gates and never authorizes release. No test or helper fabricates a real user's approval, listening or media rights.
