# Live production monitor

The local monitor shows actual studio records across checkouts and Git worktrees. Its compact React 19 interface uses Vite, Tailwind CSS, shadcn/Base UI, TanStack Table, React Flow and Lucide React. It includes a production data table, live **Production Progress** workflow with a details drawer, a custom film player, measured shot/speech/caption/sound tracks, voice revisions, pending decisions and measured time estimates. Light/dark themes, mobile layouts, keyboard controls and reduced motion are supported. There is no external service.

## Open it

Build the frontend once with Node 22.12 or newer, then start the monitor:

```powershell
npm --prefix apps/monitor ci
npm --prefix apps/monitor run build
.\.venv\Scripts\python.exe tools/studio.py monitor --workspace . --port 8765
```

Node is not needed to view an existing build. Rebuild after changing frontend source; `apps/monitor/dist/` is ignored by Git. The server explains a missing build with a 503 while leaving its API available. [Frontend structure and development commands](../apps/monitor/README.md).

Open the printed loopback address. `--workspace` is repeatable; related Git worktrees are discovered automatically. Use `--no-discover` to watch only the named directories. `--port 0` chooses an available port. Leave the monitor process running; stop it with Ctrl+C. This process only reads the watched projects and serves the bundled interface. It starts no production job, model, download or provider request and does not switch branches.

The monitor can run in a separate worktree while a story is produced in another. It lists initialized `stories/<slug>/` projects from their real intake/branch records. Identical story names in separate paths remain separate projects. It does not create sample stories or populate missing fields with fictional progress. The observer checkout does not need speech models: cached performance is compared against current voice/model/script settings without production-runtime readiness checks. Actual synthesis keeps its normal readiness checks.

For a terminal snapshot:

```powershell
.\.venv\Scripts\python.exe tools/studio.py status ./stories/my-story
.\.venv\Scripts\python.exe tools/studio.py status ./stories/my-story --json
```

## Read the status

**Production Progress** replaces the earlier Production History view. Each flow node represents a currently recorded step; select it to inspect live task fields and its timestamped evidence in the side drawer. Running tasks show a loader, while submitted provider requests are labeled as awaiting the provider. Reported, stale, blocked and offline activity do not masquerade as verified running work. The graph and open drawer refresh with the API without repeatedly resetting the viewport. Connectors express workflow order rather than a timing scale or strict dependency. Unknown counters/durations remain unreported, and earlier media is marked stale after relevant changes. Older progress bookmarks remain compatible.

- **Running** means a local instrumented operation has a recent heartbeat. A heartbeat proves the reporter is alive; measured counter changes are shown separately. Missing heartbeats become stale, rather than continuing an invented progress bar.
- **Reported activity** comes from older job records or an agent milestone without a live reporter. Older producers remain visible, but only production launched with the updated tools emits the new heartbeats/counters. Do not interrupt an existing production just to upgrade its telemetry.
- **Provider waiting** means a request was actually submitted. A provider without progress/ETA reporting has an unknown remaining duration. Unknown outcomes still require reconciliation; the monitor never retries them.
- **Your decision** is distinct from an agent task. A current complete preview without its matching recorded acceptance is shown for review. Listening, image inspection and other existing workflow requirements stay in force.
- **Available** counts real files. Image counts are separate from recorded visual reviews, and voice clip counts are separate from listening/QA. Local step counts cover the selected run, not an invented percentage of all creative work.

The page polls every two seconds while visible and less often in the background. A connection failure keeps the last snapshot and marks it disconnected. Partial JSON writes retain the last readable record with a warning. Missing, stale or older records are identified explicitly.

## Cast sheets and requested character changes

**Cast sheets** lists real registered characters with current sheet files, requested view/expression/pose coverage, revision, linked-shot counts and inspection state. Select a row to open the profile and full reference images in a side drawer. Missing profiles/sheets, pending or stale inspection, submitted provider requests and unknown results remain distinct. Production Progress includes a project-wide Cast sheets node with actual verified/registered counts; no future characters or completion estimates are invented.

**Request change** queues the user's exact notes for the production agent against the displayed design version. It does not edit the character profile, generate media, spend budget or approve anything. The agent applies the real request through the revision workflow, which preserves earlier sheets and identifies affected shots. Earlier images remain available in the drawer. Stale forms, a different story branch, cross-origin requests and missing tokens are rejected. [Profile, inspection and revision commands](18-cast-sheets.md).

## Preview, timeline and voice revisions

The overview keeps current activity, a small metrics strip and the task data table in view. Search tasks, filter by status, sort columns, choose a page size or expand a row for actual task evidence. Production Progress groups measured durations, telemetry, voice changes, preview decisions and delivery events into compact workflow steps. Search or filter the steps and inspect their timestamped evidence in the side drawer. Stable event IDs suppress duplicate completion entries. A completed production clock ends at a current part delivery; time spent monitoring afterward is not added to that duration. Measured timers take precedence over whole-second legacy timestamps.

The player streams the actual local MP4 with byte-range seeking. Timeline tracks use measured `timeline.json` and speech chunk anchors, including narration onset, rather than evenly spaced placeholders. Click a shot or spoken line, scrub, or zoom the timeline. A changed preview is offered with **Load updated preview**; polling does not repeatedly reload an in-progress viewing.

Voice cards show the current cast override, generated voice IDs and the real recorded change request. A new voice selection remains pending until matching speech exists. Changed speech sources, mix bytes, shot images, caption bytes or presentation timing make the earlier preview visibly stale. Synchronized timeline seeking is disabled for a stale preview whose timing is not verified. Unaffected images and clips are not regenerated by monitoring.

A preview is marked accepted only when its exact current input hashes match a real `production/preview-decisions.json` decision with a quotation and source reference. The monitor records no approvals. Watch the preview here and give the actual decision or requested changes to the production agent; the agent uses the existing workflow commands. A displayed voice ID does not establish performance quality or listening evidence.

## Report real creative milestones

Automatic telemetry covers local runner stages, speech clips, FFmpeg encoded time and image request/import boundaries. The agent can report meaningful creative milestones from the story's own checkout/branch:

```powershell
.\.venv\Scripts\python.exe tools/studio.py progress stories/my-story --stage world --state running --message "Inspected 2 of 3 recurring character designs" --completed 2 --total 3 --unit characters
.\.venv\Scripts\python.exe tools/studio.py progress stories/my-story --stage review --state waiting --actor user --message "The current complete preview is ready for your listening and picture decision"
```

Use only actual stage changes and measured counts. Omit counts when the total is unknown. Agent notes are reports, not continuously running timers or approval evidence. They become stale if not updated. Do not run a second coordinator or generate unnecessary media to make the dashboard move. Runtime telemetry is ignored by Git under `production/progress/`; canonical story/voice/approval records remain authoritative.

## Time estimates and scope

The monitor estimates the **current operation** from actual completed units and elapsed time, or at least two successful recorded runs of that same operation. Cached/failed samples are excluded. First runs without enough evidence show that the estimate is unavailable. An operation that exceeds its historical range returns to an unknown estimate until new progress is available.

A remaining-local-pass range is shown only when all unfinished selected steps have evidence. Creative decisions, unreported provider queues, missing image work and human review are not included in a promised completion time. Time since intake includes waiting and is labeled separately. These estimates are useful ranges, not a film delivery SLA.

The server binds only to `127.0.0.1`, rejects other Host headers, exposes only allowlisted static files and registered project media, and has no cloud telemetry. Snapshot/media access is read-only. Its sole write endpoint records explicit character-change requests using same-origin checks, a per-server token, bounded JSON, design-version checks and the story's branch guard. Other write methods/routes cannot mutate production or canonical records. It is a local single-user monitor, not an authenticated hosted collaboration service.
