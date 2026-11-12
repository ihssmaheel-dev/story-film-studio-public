# Resumable short-film production

Use the existing initializer, complete source read and concrete configuration authorization. Then batch authored planning records and use `studio continue` for the measured local work and next agent action. Image generation, creative inspection and actual listening remain genuine work. No fixed fresh-film completion time is promised.

## Author the plan once

```powershell
python tools/studio.py prepare stories/my-story --snapshot > production-bundle.json
```

Keep the captured `source_sha256` and `base`. Fill `artifacts` with the actual canonical JSON objects and document text, then apply them together:

```powershell
python tools/studio.py prepare stories/my-story --file production-bundle.json --check
python tools/studio.py prepare stories/my-story --file production-bundle.json
```

Supported artifacts are authored world bibles, continuity records, the part plan, audio requirements/casting briefs, and part metadata/shots/spoken turns/storyboard/timeline. `narration.txt` is derived from actual `speech.json` turns or written shot narration; speaker labels/directions are excluded. For a changed `speech_turns` plan, old derived timeline tracks become pending until rebuilt from measured speech. A change only to the explanatory `image_planning` record preserves those tracks. Explicit manual timelines remain authored records.

Choose shot counts with [story-driven image planning](../instructions/shot-planning.md), without a fixed per-minute quota. New shot lists retain a final-story-bound `image_planning` rationale and each shot's purpose/entry reason; use [the structural example](../templates/image-planning.example.json). Preparation and production checks reject a stale or incomplete record when present. Existing shot lists without the record remain usable. `next` includes the guide, actual shot/source/reference counts and current measured holds (or explicitly authored manual holds); pending/stale timing is not presented as measured. These are agent context and structural checks, not artistic approval or another user gate.

This does not edit the preserved source, revised story, configuration, narrator choices, authorization, provider receipts, listening/inspection decisions or approvals. Use their dedicated commands. The batch checks the original-source hash and captured file hashes, preserves exact prior bytes under `production/plan-revisions/`, checks actual continuity after applying, and rolls back a failed batch without replacing concurrent edits. `--check` checks source/base, paths, JSON and spoken-text agreement without applying; semantic continuity is checked on apply. Source reading and semantic creative judgments are never inferred from a successful command.

Keep the bundle outside the story's canonical files, or remove it after its receipt is recorded. Canonical records remain authoritative; the bundle is an input transaction. No per-film Python timing/image/export helpers are needed.

## Continue until the next real action

```powershell
python tools/studio.py next stories/my-story
python tools/studio.py continue stories/my-story
```

`next` is read-only and can inspect another checkout. `continue` runs only on the story's own branch, follows configured tool/budget/privacy boundaries, and holds the same OS coordinator lock as `run`. A crash releases the lock; another active coordinator is rejected before its progress can be overwritten.

| Actor | Agent behavior |
|---|---|
| `agent` | Complete the internal preparation, tool call or inspection and continue; no routine user question. |
| `user` | Present the concrete missing configuration/cost choice or actual complete preview decision. |
| `none` | The selected deliverable is complete. |

Readiness is checked before reference/final-image work. A matching readiness receipt is reused; changed voice/reference/script, package or runtime-file metadata invalidates it. A complete verified speech cache passes without starting/contacting the speech provider. Damaged or changed clips require actual readiness again. No model is installed/downloaded automatically.

The shared style and recurring cast references are established before final shots. A single shared cast sheet can be registered for multiple characters; a one-off character does not automatically need another sheet. Before full speech or final-image production, each speaking role has its story-specific `performance_brief`, current `selected` provider/model/voice, and a real audition in `sample` or `candidates`. Each sample records `file`, `sha256`, `provider`, `model` and `voice`; matching actual existing auditions can be reused. A changed voice cannot reuse the old voice's sample evidence. Missing casting/sample work is an agent task, without another routine approval. Hearing/performance quality remains provisional without actual listening.

Local speech, alignment, measured timing, sound, mix, captions and technical preview work run together through the existing resumable coordinator. The next image request is returned in that invocation. Later image handoffs skip that local pass when its inputs remain valid. The returned `tool_request`, exact request file and `start` command remove the need to compile another image bridge. Execute that start immediately before the real authorized image tool, import its actual output with `studio images ... import`, inspect it and continue. Queueing itself makes no provider call. Unknown provider outcomes block another call; retries never silently spend another request.

Current image/reference inspection and technical checks precede the complete-preview question. One actual matching preview decision remains required. Internal image/alignment/sound checks are agent work; genuine final playback remains separate. After playback is recorded, `continue` exports to the next unused immutable `rN` revision and moves to the next unfinished part. It never records an approval, listening verdict or playback review itself. Repeating a completed run does not overwrite its delivery.

## Keep multipart stories coherent

For multipart production, author `creative/part-plan.json` using [the structural example](../templates/part-plan.example.json). The current final story is `creative/story-revised.md` when present, otherwise `creative/original.md`, matching the audit. Its actual hash and contiguous one-based line spans bind every part to the complete narrative through the ending.

Record each part's opening hook, dramatic progress, earned ending, stable-entity entry/exit state, nonfinal continuation promise and next-part payoff. The next part explicitly names the promise it develops. Inherited facts cannot disappear or contradict the previous ending; a time jump uses actual registered state-ledger `handoff_events`. The final part has no further continuation promise. These are structural checks, not an automatic assessment of dramatic quality.

The packet carries the selected narrative excerpt, previous ending, required inherited state, payoff, continuation and shared canonical revisions. Retain the full-source understanding and use this focused handoff instead of rereading unchanged manuals. Detailed shots for later parts can remain progressive; all part narratives/boundary promises must already exist. Direct Fast production commands also reject a stale/contradictory structured plan when present. Older projects keep their existing records; no silent migration occurs.

When a continuous full-film cut is included, the packet exposes its required assembly after part deliveries and links the measured edit plan. Continuous assembly remains an explicit agent editing/preview/playback task; part exports alone do not complete that edition.

## Verify the improvement

Measure local processing separately from image/speech provider latency, creative work and actual human waiting. Existing heartbeats/counters now include early readiness, and `production/progress/next.json` retains the latest real next-action packet for recovery. No percentage or whole-film ETA is manufactured. Regression/benchmark evidence is recorded in [the verification log](10-improvements-and-verification.md).
