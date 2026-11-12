# Workflow and decisions

New projects use **Fast**; existing projects without a workflow record remain **Strict**. [The Fast contract](13-fast-workflow.md) defines authorization, revisions and preview decisions. Mode selection is not itself permission.

## Fast

Reuse preferences and ask missing material choices together. Present concrete source/output/length/look/voice/tool/budget/upload/edit configuration and record the actual authorization once. Read the full source, perform twelve internal checks and a focused cross-check, and make only permitted corrections. Present meaningful findings and major creative choices concisely.

Complete internal world/shot/voice work and actual production inside scope. Scale references to actual needs. Whole-story dependencies stay required; detailed future-part shots can wait. Present the inspected complete preview and record one actual user decision. Then render the master, perform genuine image/alignment/sound/playback QA and export. These checks are agent work, never auto-passed.

`production/delegation.json` records scope authorization, `creative/revision.json` records revision permission, and `production/preview-decisions.json` records preview decisions. Changed configuration needs renewed authorization; changed presentation needs a changed preview. Updating internal review metadata alone does not change presentation. Fast never fabricates G1–G6 signoffs.

## Strict

Strict retains complete source reading, scene mapping, twelve audit areas, full second pass and the A–I report before issue-specific correction permission. Preserve the exact original; deliver the complete authorized revision/change log/recheck and separately approve its result.

| Gate | Concrete scope |
|---|---|
| G1 Story | Complete audited story, arcs, reveals, ending and residual decisions |
| G2 Format and parts | Video/parts, duration/flexibility, boundaries, beats and payoffs |
| G3 Visual world | Bible/style proof, characters/locations/props, geometry/states/dependencies |
| G4 Written shots | Every part's exact speech, visuals, camera/motion/crops, subtitles and sound intent |
| G5 Voice and sound | Actual auditions/configuration and sound approach, or explicit no-speech scope |
| G6 Production | Actual providers/tools, acquisition/rights, budget and privacy |

Present exact artifacts/revisions and ask “Approve Gx revision y?” Record the real quotation/reference/timestamp/membership/hashes through `project_records.py`. Status is draft/review/approved/stale. Silence, another gate, report acceptance, fix permission or selecting a format is not that signoff. Earlier reference/audition work needs its own actual scope.

`approvals.json` is authoritative; Markdown is generated. CLI checks support evidence but cannot establish authentic human permission. Changed artifacts stale dependent gates and produce an impact map; preserve history. Fast grants do not convert into these signoffs.

## Both modes

Source preservation, canonical continuity, actual expense/privacy scope, measured timing, terms/listening, image checks, alignment inspection and real playback remain required. Rebuild the smallest affected set and preserve rollback. `configure --mode strict` or `--mode fast` is explicit migration; Fast also needs actual configuration authorization. Routine maintenance and synthetic tests approve no real story.
