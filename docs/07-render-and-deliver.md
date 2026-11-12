# 07 — Render and deliver parts

> **Workflow:** Fast is the new-project default; see [Fast workflow](13-fast-workflow.md). G1–G6 and separate reference/audition signoffs in this guide describe Strict mode. Fast uses scoped delegation and internal review; technical, continuity and genuine QA requirements still apply. Existing projects without a workflow record remain Strict.

## Assemble from approved assets

Validate the timeline before mixing and with `--check-assets` when images/final mix are ready. `tools/mix_audio.py` creates the declared final mix; the renderer reads `audio_file` and never guesses cue placement. A speech-only or deliberately silent mix is valid when planned.

```powershell
python tools/validate_timeline.py stories/my-story/parts/part_001/timeline.json --check-assets
python tools/render_part.py stories/my-story/parts/part_001/timeline.json --output stories/my-story/parts/part_001/final.mp4
```

The renderer uses stills with direct cuts, optional per-shot authored camera movement, timeline dimensions/FPS, H.264/yuv420p and AAC. Intervals come from the timeline, without built-in duration/still-count limits. Missing `motion` stays static; see [camera motion](12-camera-motion.md) for zoom/pan fields, crop safety and G4 review. Moving shots need matching source aspect and protected detail boxes; static shots retain their fitting/padding behavior. Optional `--srt <path>` burns verified subtitles after camera framing when FFmpeg supports libass; keep the standalone SRT too.

## Per-part deliverables

Deliver MP4, timeline, written storyboard, performance text, narration WAV when speech is used, final-mix WAV, requested SRT, shot images, QA report and a manifest with actual provenance/checksums, commands, runtime and revision references. Include the sound plan and source/generation records. Provide a readable summary with exact paths, format, duration and material limitations.

Include the complete story audit, authorized full revision/change log and approvals. A successful process exit or written plan alone cannot establish release quality.

## Continuous edition and final checks

Single-video delivery uses only `part_001` and supplies one complete film. New multipart configuration normally includes both the individual part videos and one continuous full film (`continuous_edition: true`); an explicit false means parts only. Existing projects with no recorded full-cut scope are not silently expanded.

For an included full cut, finish the parts and continue to actual assembly using `creative/continuous-edit.md` and `full-film/`. Keep clean images/audio stems. Record measured source time ranges and output order, remove repeated release titles/recaps/teaser or subscription packaging while preserving essential story hooks, and rebuild joins, continuous audio, subtitles and their timing. Use compatible sources or re-encode deliberately. Inspect joins for abrupt ambience/music changes, repeated speech, dropped actions and subtitle overlap; watch/listen to the whole full-length file and record its own provenance, render/QA/playback evidence and immutable delivery. Reuse the cast and assets rather than generate a different full-film version of the story.

The current `studio run` coordinator processes selected part timelines. The agent also performs the configured continuous edit/assembly with local media tools and records the actual commands/results; running the part coordinator alone does not create the full cut. Present actual part/full previews together when practical and record exactly which versions the user's decision covers. A full-cut preview is distinct from the already accepted part previews; do not ask again for unchanged part content or invent a full-cut acceptance. See the [continuous edit template](../templates/story/creative/continuous-edit.md).

Measure dimensions/aspect/FPS/duration/codecs/audio streams; inspect first/last frames, unwanted black frames/freezes, padding, subtitle sync, clipping/true peaks, intelligibility, narrative payoff and continuity. Watch/listen to the whole file. Keep a master and requested distribution copies, commands and actual versions.

For moving shots, inspect start/middle/end crops and the complete movement for jitter, sharpness, speed, easing, unintended borders, clue visibility, reveal timing and subtitle overlap. A protected-box validator is not proof that the real face or clue was correctly annotated. No camera movement is added implicitly and no character animation is generated.

## Preview, master and immutable delivery

The preview profile uses a maximum 640-pixel dimension, ultrafast encoding and CRF 28; final uses approved dimensions, medium/CRF 19. `studio.json` and G6-reviewed project overrides control these. Before concat, stills are cached at a common frame size with the selected scaling/padding and EXIF orientation. This prevents changing source dimensions from resetting the frame filter and dropping an opening shot. Render checks include dimensions, audio stream, zero video start, full stream duration and frame count.

```powershell
.\.venv\Scripts\python.exe tools/studio.py run stories/my-story --profile preview
.\.venv\Scripts\python.exe tools/studio.py image-review stories/my-story --part part_001 --shot SHOT-001 --verdict passed --reviewer "actual reviewer" --notes "actual style/identity/geography inspection"
.\.venv\Scripts\python.exe tools/studio.py run stories/my-story --profile final
.\.venv\Scripts\python.exe tools/studio.py playback-review stories/my-story --part part_001 --reviewer "actual reviewer" --notes "actual full playback observations"
.\.venv\Scripts\python.exe tools/studio.py export stories/my-story --part part_001 --revision r1
```

These notes are placeholders; never record inspection that did not happen. Each image review covers its bytes and current shot/canonical references. A master waits for those reviews and unresolved alignment checks. Final playback review recomputes technical QA, checks current source/mix/render hashes and requires explicit acceptance of remaining warnings (`--accept-warnings` only after actual inspection).

Export refuses missing/stale reviews and writes a new `delivery/part_001-r1/` with portable relative paths, master/WAV/SRT where applicable, images, written shots, canonical references, audit/change log/approvals, QA and checksummed manifest. Existing delivery revisions are never overwritten. Later changes require a fresh render/review/delivery revision. Source performance/provenance and runtime manifests are included where available.
