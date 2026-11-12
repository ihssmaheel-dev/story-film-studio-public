# 06 — One authoritative timeline per part

> **Workflow:** Fast is the new-project default; see [Fast workflow](13-fast-workflow.md). G1–G6 and separate reference/audition signoffs in this guide describe Strict mode. Fast uses scoped delegation and internal review; technical, continuity and genuine QA requirements still apply. Existing projects without a workflow record remain Strict.

`parts/part_###/timeline.json` controls the complete presentation clock: measured performance plus intentional action, silence, transitions and tails. Longer parts may have speech-free passages. Do not force a fixed length or arbitrary image grid.

## Fields

Use `part_id`, approved `width`, `height`, `fps`, `duration`, `narration_file` (or null for no speech), `narration_start`, `narration_gain_db`, output `audio_file`, `audio_manifest`, ordered `shots`, `subtitles` and `audio_cues`. Dimensions must be positive even integers for H.264/yuv420p; FPS must be finite and positive. Optional `scale_filter` selects `lanczos`, `neighbor` or `bicubic`; use a style-appropriate choice such as nearest-neighbor for a defined pixel grid. Paths are relative to the timeline except audio asset files, which are relative to their registry.

Shots record unique ID, image, start/end, exact speech where applicable, style ID/revision, scene/entity IDs and state. Cover presentation without unintended gaps/overlaps. Keep `alignment` evidence: actual method, source WAV/hash, confidence, uncertain ranges and manual checks. Estimated/template cues are not verified alignment.

An optional per-shot `motion` records the G4 camera plan: static/zoom_in/zoom_out/pan, story reason, normalized poses/protected boxes, easing and `start_at`/`end_at` fractions. Omitted/null stays static. The builder copies the written object unchanged; measured shot boundaries determine the move clock without adding time or images. See [camera motion](12-camera-motion.md). The renderer and continuity checks reject unsafe or unapproved plans; changed move timing needs renewed affected signoff.

Sound cues record unique ID, `asset_id`, role (`ambience`, `sfx`, `music`), start/end, `source_offset`, `gain_db`, `fade_in`, `fade_out`, `loop` and `duck_under_narration`. Fades must fit the cue. Offset plus playback must fit the actual source unless explicit looping is selected. Provenance belongs in `audio/assets.json`; timing belongs here only.

## Workflow

1. Approve written narration/dialogue, every visual and sound intent with provisional times at G4.
2. After authorization, generate speech, measure actual WAVs and obtain alignment from a real aligner or careful listening. Record confidence and uncertain words. The installed English PocketSphinx aligner produces word times plus independent-recognition disagreement flags; other languages need a suitable alternative.
3. Include intentional silence/action/tails and choose image changes at meaningful boundaries.
4. Place verified subtitle/audio cues on the same clock; inspect/register the real sound files.
5. Validate, create the declared mix, validate final assets, render and watch/listen end to end.

Structural validation is not proof of story logic, visual fidelity, permission authenticity or semantic synchronization. G3/G4 and actual QA supply that evidence.

## Subtitles

Use `HH:MM:SS,mmm --> HH:MM:SS,mmm`, sequential numbering, positive readable intervals, no overlaps and sensible line breaks. Generally use one or two lines, preserving important visuals. Match spoken words, not image cuts. `tools/make_srt.py` exports verified cues. Mixed narration/dialogue needs agreed speaker handling. Skip output only when no subtitles were requested.

`templates/timeline.example.json` is a structural example with draft alignment, not an approved/produced part. Fill it in the intended part; real files and approval evidence are needed before production.

## Actual alignment and timing tools

```powershell
.\.venv\Scripts\python.exe tools/align_audio.py stories/my-story/parts/part_001/audio/narration.wav --profile stories/my-story/audio/narrator.json
.\.venv\Scripts\python.exe tools/build_timeline.py stories/my-story --part part_001
```

Word times are forced alignment against the real measured chunk WAVs. Independent recognition disagreement and duration anomalies remain explicit uncertainty, not a calibrated probability. Numerals need approved `spoken_forms`; out-of-vocabulary names need verified ARPABET `pronunciations`. The tool fails clearly when it cannot align the selected language/text. Changed audio invalidates alignment and previous manual checks.

After actual listening/waveform inspection, record `--review-indices 3 7 --reviewer "actual reviewer" --review-notes "actual observations"` on `align_audio.py`. Optional `--corrections <json>` contains explicit `word_index`, `start`, `end` corrections. Raw engine output remains intact; a separate checksum-scoped `.alignment-review.json` applies corrections and inspection. Times must be monotonic and inside the actual audio. Regeneration cannot silently erase the manual overlay; stale overlays require renewed review.

`shots.json` is the approved written input; the timeline is the actual timing/output record. The builder requires exact coverage of the aligned spoken text, anchors cuts/cues to real words and retains explicit onset/tail policy. It refuses transcript mismatches instead of estimating. Part-specific `part.json.duration_policy` takes precedence over the global duration policy.

For action holds, silent shots, unsupported display tokens or a separately performed soundtrack, set `shots.json.timing_mode` to `manual` and author/inspect the timeline directly. The coordinator respects manual timing. It never fabricates speech or silently compresses action to a requested duration. Renew approvals if a measured runtime conflicts with the agreed constraints. Subtitles may be false, standalone (true) or `"burn-in"` in intake; a burned master also retains its SRT.
