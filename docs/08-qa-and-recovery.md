# 08 — Quality, evidence and recovery

> **Workflow:** Fast is the new-project default; see [Fast workflow](13-fast-workflow.md). G1–G6 and separate reference/audition signoffs in this guide describe Strict mode. Fast uses scoped delegation and internal review; technical, continuity and genuine QA requirements still apply. Existing projects without a workflow record remain Strict.

## Editorial and planning QA

- [ ] Entire source read, every scene mapped and source hash recorded
- [ ] All twelve checks and actual focused cross-check (Fast), or full second pass (Full/Strict), completed
- [ ] Concise evidenced findings (Fast), or full A–I report (Full/Strict), and material questions delivered
- [ ] Actual delegation/issue-specific permission covers applied fixes; exact original preserved
- [ ] Full authorized revision, change log and re-check delivered
- [ ] Format, duration policy and all parts agreed; no hidden fixed runtime
- [ ] Fast authorization/preview decision or Strict G1–G6 are current; necessary world/dependency references complete

## Production preflight

Verify tools, model/voice/language support, image capabilities, sound acquisition routes, rights evidence, disk and approvals. Missing prerequisites do not justify inventing outputs. Global examples do not select a style.

## Image QA

- [ ] Approved style/revision, identity, proportions/abstraction, materials, palette and lighting
- [ ] Correct geography/camera axis, props/mounts, wardrobe and story-time state
- [ ] Readable action/emotion/reveal details and performance correspondence
- [ ] Approved aspect/dimensions/scaling with no unintended text/artifacts
- [ ] Camera plan matches G4, with actual protected details visible at start/middle/end and throughout playback
- [ ] Moving source matches delivery aspect and has suitable crop resolution; speed/easing/jitter/borders/reveal timing/subtitle safety inspected
- [ ] Adjacent shots and recurring designs across parts compared; repairs logged

## Sound and part QA

- [ ] All required ambience/effects/music obtained or an alternative explicitly agreed
- [ ] Provenance, actual checksums, rights evidence and listening QA recorded
- [ ] Sound matches event, acoustic perspective, story state and emotional purpose
- [ ] Starts/exits, fades/offsets correct; loops intentional and unobtrusive
- [ ] Speech clear, gains/ducking appropriate, music phrasing/silence intentional
- [ ] Available duration/peak/loudness/true-peak measurements and targets recorded
- [ ] Real performance durations and uncertain alignment ranges checked
- [ ] Timeline covers action/silence/tails; requested subtitles match speech
- [ ] Final format/audio/duration verified; complete part watched/listened on headphones and ordinary speakers
- [ ] Story payoff, transitions and final frame work

No fixed still count/duration is a quality test. Mark only checks that actually ran; templates start empty. Validators cannot establish listening, artistic quality or semantic sync.

## Resume and repair

Use immutable revisions. Local `production/status.json` jobs use `running`, `complete`, `failed` and `stale`; image requests separately track `pending`, `failed`, `needs_attention` and `generated`, with independent review status. Recheck files/checksums, not just flags. Log attempts, prompts, decisions, commands and actual QA. Rebuild the smallest dependency set: script changes affect performance/alignment; cue changes affect mixes/renders; style changes affect associated visuals. Preserve prior assets/signoffs for rollback.

After three failed style/identity/geometry attempts, propose stronger references, simpler framing, manual repair or another provider with costs disclosed. For missing/poor sound, find another source/generator or agree an alternative. Never release an invented or knowingly broken cue. Renew approvals only where changed scope/artifacts invalidate them.

## Automated evidence and bounded recovery

`quality.py` decodes images, reports aspect/resolution issues, measures WAV and encoded-audio LUFS/true peak/silence, probes stream duration/start and detects black ranges. Paginated contact sheets place canonical references alongside shots; visual identity, camera geography, event sync and artistic quality still need direct inspection. Intentional darkness/silence is a warning to review, not an automatic creative error. Reports start with playback pending and release_ready false.

`JobStore` writes atomic status/checksum records and timings under `production/logs/timings.jsonl`. Matching complete inputs/parameters/outputs reuse work. Interrupted running jobs restart locally; corrupt outputs or changed code/inputs rerun their stage. Local failures have a bounded attempt count; subprocesses have configured timeouts and are stopped on timeout. Image/provider calls are never automatically retried when their outcome is unknown. Reconcile job ID/cost first; after three known failures request a concrete alternative.

`project_records.py ... refresh` writes stale approvals and an entity/shot/audio impact map. Do not delete unaffected outputs. The runner reports blocked review/acquisition actions in `production/last-run.json`; a missing provider or listening review is not a successful render/release. For a nonzero command exit inspect saved failures before resuming the same command.

The synthetic regression suite and `.runtime/checks/technical-demo/` exercise technical behavior without fictional production approvals. Their fixture images, procedural audio and flags cannot be delivered as an approved user film.
