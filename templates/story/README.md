# Story workspace

New projects use Fast: configure the work once, create an inspected preview, record the actual user preview decision, then finish and export after genuine agent QA. Read root `docs/13-fast-workflow.md`; Strict projects retain individual G1–G6 signoffs.

This project belongs to the `story/<safe-title-slug>` branch recorded by initialization in `production/git.json`. Keep its work on that branch; `studio resume stories/<safe-title-slug>` returns to a committed project. New stories start from the studio base rather than this story's canon. See root `docs/15-story-branches.md`.

Keep the exact original/source record, structured intake/audit/scene ledger, complete permitted revision/change log, canonical world/dependencies, selected-part written shots, actual timelines and media evidence here. A scaffold is draft, never proof of reading, permission or inspection.

`production/workflow.json` stores configuration, `production/delegation.json` actual scoped authorization, `creative/revision.json` revision permission, and `production/preview-decisions.json` the actual preview decision. None is copied as permission to another story. `approvals.json` and its generated Markdown view are the Strict gate records.

Generate concise review views with `studio review` and `review_pack.py --audit`. Use full A–I audit only for Full/Strict after the real complete procedure. Reuse known answers/preferences. For multipart work plan all dependencies/boundaries, then detail the next selected part in Fast mode. Source/identity/state, rights/listening, measured timing, image/alignment and final playback checks remain required agent work.

A single full-length request creates one complete film using only `part_001`. New multipart requests include individual videos and a continuous full film unless parts only is explicit (`creative/intake.json` → `continuous_edition`). Write every part narrative before production, with opening hooks, earned endings and paid-off continuation promises; then produce parts in order and complete the included full cut using `creative/continuous-edit.md`. Cast designs must fit the specific roles and remain identifiable across every output.

Speech is selectable through root `docs/14-speech-providers.md`: free/local engines, cloud APIs, custom gateways or imported performances. Keep provider/model/default narrator and story-specific cast in `audio/narrator.json`, with exact speaker turns/directions/pauses in each part's `speech.json`. Credentials remain outside the project in environment variables. Presets reuse provider/narrator preferences and selected global voice snapshots, never another story's character mappings or authorization.

`audio/voice-plan.json` records this story's narrator/character performance briefs, actual audition evidence and selection reasons. Root `instructions/voice-casting.md` guides story-fit choices and later user changes. `studio voice set` retains exact old profiles and records the actual change request without restarting full configuration inside scope; rebuild the affected audio/timing/previews and preserve previous deliveries.
