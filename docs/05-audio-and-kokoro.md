# 05 — Narration, background sound and mixing

> **Workflow:** Fast is the new-project default; see [Fast workflow](13-fast-workflow.md). G1–G6 and separate reference/audition signoffs in this guide describe Strict mode. Fast uses scoped delegation and internal review; technical, continuity and genuine QA requirements still apply. Existing projects without a workflow record remain Strict.

## Voice and performance

The user chooses the speech provider. Supported routes are Kokoro, local Chatterbox, ElevenLabs, Inworld, Cartesia, a configured custom HTTP gateway and imported audio from other providers/actors; see [provider setup, cast and contracts](14-speech-providers.md). Kokoro remains the free CPU default where its verified files/language fit, not a required engine. Cloud providers use the user's own account/environment credentials and actual cost/upload scope; Chatterbox is an optional separate runtime/checkpoint setup. Never silently substitute a paid provider or a different voice. Strict compares appropriate available voices before G5. Fast reuses a suitable configured selection and auditions changed/uncertain choices or performance problems inside scope. Record provider/model/voice IDs, actual hashes/versions, language, speed, pauses, terms and pronunciation in `audio/narrator.json`, with listening evidence in `audio/narrator.md`. Visual style does not dictate language/voice. Speech-free delivery skips voices and records the actual not-applicable scope.

Assign explicit role-appropriate voices to stable character IDs in `cast`, keeping the same identities across all parts and the full film. Write dialogue/mixed performance in each part's `speech.json`, with exact spoken `text`, separate `speaker`/supported `direction`, and intentional pauses; its concatenated words must match `narration.txt` and written shots. Do not silently use the narrator for an unmapped character or send unsupported tags as spoken words. Keep measured clip WAVs and positions. Listen for role fit, pronunciation, clicks, pauses, emotion and conversational flow. Regenerate only affected takes, then update alignment/derivatives. Avoid unnatural speed changes to force runtime. The installed automatic aligner remains English; choose compatible/manual timing before non-English dependent generation.

```powershell
python tools/studio.py providers
python tools/studio.py speech stories/my-story --part part_001
```

## Derive sound from the complete story

In `audio/sound-plan.md`, inventory ambience (room/city/forest/weather/machinery), visible/implied event effects, character/prop sounds, music and intentional silence. Link requirements to scene/shot/entity IDs, physical perspective/distance, story state, onset/exit, emotional purpose and adjacent scenes. A physical emitter/event must exist or be implied where heard. Distinguish story-world sounds from non-diegetic score. Plan recurring motifs and restraint; noise under every image is not a quality goal.

G4 approves cue intent/provisional timing; G5 approves sound approach and audition evidence; G6 approves final tools, generation/sourcing, costs and privacy. Earlier samples need permission covering those tools/expenses. After alignment, actual cue times live only in `timeline.json`.

## Generate or source actual audio

During authorized production, execute an appropriate route for every approved requirement:

- Inspect and use the user's supplied asset with actual usage permission.
- Source a suitable file with verified terms; record creator, title, original page/download URLs, license/attribution evidence and retrieval date. Use available permitted tools. A search result is not a downloaded asset.
- Generate with an available approved sound/music tool; record model/tool/version, prompt/parameters, seed when supported, date and actual terms. Do not assume a provider exists or is free.
- Use `tools/generate_sound.py` for limited local procedural wind/rain-like textures, hums or tones. These are synthesized approximations, not recordings or a general music/effects model. Audition and replace them when unsuitable.

```powershell
python tools/generate_sound.py --kind wind --duration 12 --seed 7 --output stories/my-story/audio/ambience/wind.wav
```

The helper writes a WAV and provenance sidecar, without automatically registering rights or passing QA. Complex effects, natural performances and score need appropriate sources/providers or an agreed alternative. If a sound cannot be obtained, record the gap and resolve it before release. Never invent a file, successful generation, download or rights claim.

## Asset registry and cue clock

`audio/assets.json` records reusable files/provenance with paths relative to that manifest. Each asset has a stable `AUD-001` ID, file, SHA-256, kind, source/generation evidence, rights status/evidence and listening-QA status. Keep original files immutable by revision. The mixer requires used assets to exist, match their checksums and have `rights_status: verified` and `qa_status: passed`. Set these only after actual evidence/listening; flags cannot independently establish rights or quality.

Each part's `audio_manifest` points to that registry. Its `audio_cues` contain asset IDs, start/end, source offset, gain, fades, loop and narration-ducking. Reuse files without duplicating provenance. `narration_file` is the unmixed speech input; `audio_file` is the output mix, normally `audio/final_mix.wav`. Keep one timing authority.

## Mix and listen

```powershell
python tools/mix_audio.py stories/my-story/parts/part_001/timeline.json --dry-run
python tools/mix_audio.py stories/my-story/parts/part_001/timeline.json
```

The dry run checks inputs, registry flags/checksums and probes source durations when FFprobe is available, then prints the FFmpeg command/filter graph. It does not create or approve audio. Actual mixing requires FFmpeg and verified source-duration coverage. Looping must be explicit; a short asset must not silently leave a planned cue empty. The mixer places sounds, applies gain/fades, optionally ducks selected tracks beneath narration, limits peaks and writes a stereo PCM WAV at the declared path. It refuses to overwrite an input.

Listen to assets and the full mix on headphones and ordinary speakers. Check speech intelligibility, clipping, abrupt edits, loops, acoustic perspective, background continuity, music phrasing, silence and event sync. Measure output duration, peak/loudness/true peak with available tools; record selected targets and actual measurements. Peak limiting alone does not prove a loudness target or a good mix. Revise choices/levels and rebuild derivatives, keeping commands/logs.

## Cached generation and acquisition commands

The provider-independent coordinator caches measured clips by actual provider/model/voice, text, delivery/context/take and input/runtime hashes. Legacy single-narrator Kokoro retains its existing sentence cache and one warm model instance; the optional Chatterbox server also stays loaded. Explicit turns support different voices/providers without loading Kokoro when it is unused. Chunk WAVs and relative paths/hashes form a measured `.chunks.json`; assembly writes incrementally. Cloud results are retained before decoding, so a damaged derivative can be rebuilt without paying for the same request again. Speech and image estimates share the Fast total budget; unresolved provider outcomes stop automatic retries. Local job status/timing and sound receipts remain checksummed.

`audio/requirements.json` holds approved acquisition records: `asset_id`, `kind`, `route`, `tags`, plus procedural `parameters` or a provided `file`/`source`, or sourced `filename`/`download_url`/optional `sha256`/`source`. Sources record actual creator, original page, terms and retrieval evidence. `run` obtains the specified files and registers them as unverified/pending. It never invents a suitable source or auto-passes listening.

```powershell
.\.venv\Scripts\python.exe tools/audio_assets.py stories/my-story add --file C:/audio/rain.wav --id AUD-001 --kind ambience --source-page "actual source" --creator "actual creator" --terms "actual usage terms" --tags rain exterior
.\.venv\Scripts\python.exe tools/audio_assets.py stories/my-story search --tags rain
.\.venv\Scripts\python.exe tools/audio_assets.py stories/my-story loop --file C:/audio/rain.wav --output stories/my-story/audio/ambience/rain-loop-r1.wav --crossfade 0.25
.\.venv\Scripts\python.exe tools/audio_assets.py stories/my-story review --id AUD-001 --rights-evidence "actual verified evidence" --listening-notes "actual inspection notes"
```

Crossfading prepares a new immutable loop revision; its seam still requires listening. Acquisition and review are separate. Replacing bytes requires a new asset ID/revision. Procedural generation streams one-second blocks rather than holding a long stereo array. Repeated cues share one FFmpeg input and reuse probe/hash results.

The final mix uses two-pass loudness normalization with configured targets (default -16 LUFS, -1.5 dB true peak), speech ducking and exact 48 kHz sample duration. A short flush tail prevents fractional-duration loss in the loudness filter. Measure the encoded AAC too; compression can change peaks. Preview and final video profiles share the current mix, preserving a single audio clock. Targets and measurements do not replace listening.
