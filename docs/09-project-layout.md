# 09 — Project layout and ownership

> **Workflow:** Fast is the new-project default; see [Fast workflow](13-fast-workflow.md). G1–G6 and separate reference/audition signoffs in this guide describe Strict mode. Fast uses scoped delegation and internal review; technical, continuity and genuine QA requirements still apply. Existing projects without a workflow record remain Strict.

## Reusable root

```text
story-film-studio/
  AGENTS.md
  README.md
  START_HERE.md
  story.md
  instructions/
    project-intake.md
    story-audit.md
    source/                      # Unchanged user prompt and provenance
  docs/                          # Numbered operating guides
  references/style/              # Optional inspiration
  models/kokoro/
  templates/
  tools/
  stories/
```

## Story project

```text
stories/<safe-slug>/
  README.md
  approvals.json                 # Authoritative decision quotes, hashes and history
  approvals.md                   # Generated view
  creative/
    original.md                  # Exact snapshot; never fix in place
    source.json                  # Source path, checksum, pending audit status
    intake.json                  # Authoritative known answers
    intake.md                    # Generated view
    audit-issues.json            # Findings and completed analyses
    scene-map.md
    audit-report.md              # Full A–I, source revision/hash
    editorial-decisions.md       # Permission for specific fixes
    story-revised.md             # Created only after permission
    change-log.md
    story-approved.md
    reveal-map.md
    part-plan.md
    continuous-edit.md           # Required full-cut plan when multipart scope includes it
    all-parts-review.md
  world/
    visual-bible.md
    characters/CHAR-001.md
    locations/LOC-001.md
    props/PROP-001.md
  references/
    style/manifest.json
    characters/
    locations/
    props/
  continuity/
    story-ledger.json            # Draft audit chronology/knowledge/setup evidence
    entities.json
    dependencies.json
    state-ledger.json
  audio/
    narrator.json                # Exact voice/model, pronunciation and pacing
    voice-references/            # Selected local voice snapshots, exact hashes and usage evidence
    narrator.md
    voice-plan.json              # Story performance briefs, actual auditions and selection reasons
    voice-decisions.json         # Actual scoped voice changes and affected parts
    voice-revisions/             # Exact previous voice profiles for review/rollback
    requirements.json            # Approved acquisition routes
    sound-plan.md
    assets.json                  # Files/provenance/rights/QA
    auditions/
    ambience/
    sfx/
    music/
  parts/
    part_001/
      part.json                  # Per-part duration/title
      shots.json                 # Approved written input
      storyboard.md
      narration.txt
      speech.json                # Speaker IDs, exact spoken turns, supported acting directions and pauses
      timeline.json
      images/shot_001.png
      audio/narration.wav
      audio/final_mix.wav
      subtitles.srt
      qa.md
      preview.mp4
      final.mp4
      final-technical-qa.json
      playback-review.json
  full-film/                     # Create actual media only for an included multipart full cut
    edit.json                    # Measured source ranges and one continuous presentation clock
    preview.mp4
    final.mp4
    final_mix.wav
    subtitles.srt                # When requested
    qa-report.json
    manifest.json
  production/
    git.json                     # New story's branch, committed studio base and source hash
    plan.md
    settings.json
    workflow.json                # Fast/Strict, task and configuration scope
    delegation.json              # Actual Fast authorization, not gate signoffs
    preview-decisions.json       # Actual user decisions on displayed previews
    authorizations.json
    status.json
    image-jobs/
    speech-jobs/                 # Provider request/response IDs, reserved costs and actual reconciliation
    review/
    impact.json
    cache/
    logs/
  delivery/part_001-r1/           # Immutable export with checksummed manifest
```

Use lowercase ASCII hyphenated slugs, zero-padded part/shot numbers and stable `SCENE-001`, `AUDIT-001`, `STYLE-001`, `CHAR-001`, `LOC-001`, `PROP-001`, `EVENT-001`, `SHOT-001`, `AUD-001` and cue IDs. Preserve IDs across revisions. One canonical entity record and one presentation clock per part; use revision manifests instead of `final_final_v2` names. Generated machine paths avoid spaces.

After title agreement, `tools/init_story.py` creates planning templates and the exact original snapshot. Free-form `--style` and repeatable PNG/JPG/JPEG/WebP `--style-reference` inputs remain draft. Global examples are not copied automatically. Populate reports/ledgers from actual review; create `story-revised.md` only after permission. Template updates do not automatically migrate existing story projects.

Authoritative JSON records feed readable review views and downstream stages; avoid independently changing a generated view. Descriptive bibles, storyboards, source text and explicit editorial permission remain authored documents. `production/cache/` is disposable derived data; original sources, approved revisions and delivery records are not. Ignore delivery/cache/media binaries in Git and retain actual user deliverables separately. Use `studio.py add-part <project> part_002` to create another planned part and refresh dependent gates.
