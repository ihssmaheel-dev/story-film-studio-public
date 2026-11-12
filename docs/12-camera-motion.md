# 12 — Story-directed camera movement over stills

> **Workflow:** Fast is the new-project default; see [Fast workflow](13-fast-workflow.md). G1–G6 and separate reference/audition signoffs in this guide describe Strict mode. Fast uses scoped delegation and internal review; technical, continuity and genuine QA requirements still apply. Existing projects without a workflow record remain Strict.

The AI plans how many images tell the story and whether each image should hold still, move closer, move away or pan. Choose from the actual beat, performance, emotional attention, spatial information and reveal map. Keep static shots when they serve the scene. There is no movement quota, fixed image count, random alternation or automatic zoom on every image.

This is local camera framing over an existing still. It does not animate characters, generate unseen scenery or change story geography. The existing FFmpeg renderer handles it; no video-generation provider is added. Cuts between shots remain direct cuts. Different shot counts, sound and performance still need their own deliberate planning.

## Planning and approval

1. Reuse the author's camera preference. Intake `camera_motion` may be `static`, `selective` or null while undecided. A static-only choice prevents moving shots. If selective movement is suitable, propose the exact moves in the complete G4 shot review; preference alone is not shot approval.
2. Choose each shot and hold length for comprehension. Record `static`, `zoom_in`, `zoom_out` or `pan`, a story reason and any required reveal/subtitle space in the storyboard and `shots.json`.
3. A moving shot needs start/end poses, protected boxes for details that must remain visible, and movement timing. Review the plan with the full written storyboards at G4. Existing projects with no `motion` field remain static; template updates do not add moves to approved work.
4. After actual speech alignment, the timeline builder copies the approved motion plan and applies its timing fractions to the measured shot interval. Check the actual spoken cue and dramatic timing. Changes to the move or its fractions are changes to the written plan: update `shots.json`, renew affected approvals and rebuild affected outputs.
5. Generate a single still composed for the delivery ratio and the full camera path. Inspect its real details against the protected boxes. Requests include the movement purpose, crop poses and suggested source resolution; these prompt directions do not guarantee provider compliance.

## Shot format

`motion` is optional in each written shot and its corresponding timeline shot. Omitted or null means a complete-frame static hold. Explicit static can be `{ "type": "static", "reason": "Let the emotional reaction settle." }`.

Example **planning data**, not an approved shot or generated asset:

A complete structural timeline example is available in [templates/timeline.motion.example.json](../templates/timeline.motion.example.json). The normal timeline template remains static. Neither example supplies real images, audio or approval evidence.

```json
{
  "motion": {
    "type": "zoom_in",
    "reason": "Bring attention to the character's reaction after the admission.",
    "start": {"zoom": 1.0, "center": [0.5, 0.5]},
    "end": {"zoom": 1.10, "center": [0.54, 0.48]},
    "easing": "smoothstep",
    "start_at": 0.15,
    "end_at": 0.85,
    "protected_regions": [
      {"id": "CHAR-001-face-and-important-gesture", "box": [0.30, 0.20, 0.75, 0.85]}
    ]
  }
}
```

| Field | Meaning / limits |
|---|---|
| `type` | `static`, `zoom_in`, `zoom_out` or `pan` |
| `reason` | Nonempty story purpose for moving shots; a reason for static holds is useful too |
| `start`, `end` | Each pose has `zoom` and `center: [x, y]` in normalized full-frame coordinates |
| `zoom` | 1 is the complete frame; allowed range 1–1.20. Start with restrained changes when appropriate |
| `center` | Crop center; the entire crop must fit inside the source. At zoom 1 the center must be `[0.5, 0.5]` |
| `easing` | `smoothstep` by default, or `linear`; the chosen easing drives center and inverse zoom together |
| `start_at`, `end_at` | Fractions of the measured shot interval; `0 <= start_at < end_at <= 1`. Hold the initial pose before `start_at` and final pose after `end_at` |
| `protected_regions` | Required nonempty list for moving shots. Each has a unique `id` and `[left, top, right, bottom]` box inside `[0,1]`. These boxes must fit throughout the path |

Defaults when poses are omitted:

| Type | Start | End |
|---|---|---|
| `static` | Zoom 1, center `[0.5,0.5]` | Same complete frame |
| `zoom_in` | Zoom 1, center `[0.5,0.5]` | Zoom 1.08, center `[0.5,0.5]` |
| `zoom_out` | Zoom 1.08, center `[0.5,0.5]` | Zoom 1, center `[0.5,0.5]` |
| `pan` | Zoom 1.10, center `[0.47,0.5]` | Zoom 1.10, center `[0.53,0.5]` |

Defaults never supply a story reason or protected boxes. A pan has constant zoom and different centers; a zoom's endpoints must follow its declared direction. Unknown fields, nonfinite values and unsafe crops are rejected. Static holds preserve the full frame. At least two output frames are required for a move; very short moves receive a speed/comfort QA warning.

Protected boxes describe important content that must stay visible **throughout** the shot. Do not mark intentionally concealed content as always visible; plan and inspect reveal timing separately. Boxes are declarations, not automatic face detection or proof that the pixels contain the expected detail. Leave margin around them for raster rounding and subtitles.

## Rendering, ratios and resolution

- Any supported delivery aspect can use movement. Source artwork for a moving shot must match that aspect, allowing only minor pixel-rounding differences. A substantial mismatch blocks rendering so a pan does not expose padded borders. Recompose or obtain a suitable source instead of stretching it.
- Prefer source width/height of at least delivery dimensions multiplied by the largest zoom. QA warns when the crop needs enlargement. Preparation cannot invent missing detail; inspect the actual sharpness at the closest pose.
- Pixel-art projects locking `scale_filter: "neighbor"` use static holds. The current FFmpeg zoom/pan path resamples pixels and is rejected for that setting. A change to another treatment/scaler needs review rather than silently softening a canonical pixel grid.
- A moving part uses cached frames at twice its render dimensions to reduce crop stepping, with one continuous FPS/zoompan pipeline. Static shots within that part remain full-frame holds. Purely static parts retain the previous rendering path.
- The full path is bounded by interpolation of the crop edges: center and inverse zoom share the same monotonic progress. Valid endpoint crops and protected-box containment therefore cover the intermediate path mathematically. Rasterization and perceived quality still need playback inspection.
- Audio timing, subtitle timing, shot count and total presentation clock remain authoritative in `timeline.json`. Burned subtitles are added after camera framing, so they are not zoomed with the artwork. Check that the final placement does not obscure a face, gesture or clue.
- Long expressions are read from a filter file, avoiding Windows command-line length limits. This uses FFmpeg's `-/filter:v` option supported by the configured 9.x runtime; older replacements must support that option and `zoompan`.

The render log retains the exact filter, normalized motion plan, working dimensions, command, concat contents and asset hashes. The stage cache includes the motion compiler, renderer, validator, project render settings and timeline. A changed plan invalidates its render/review evidence; unchanged images are not regenerated merely to change a safe camera path.

## Review and limitations

Review first, middle and final poses plus full-speed playback. Check subject/clue visibility, margins, no unintended borders, sharpness, smooth starts/stops, jitter, comfortable speed, continuity, narration/SFX sync, reveal timing and subtitle space. Image review remains required before the master; playback review and accepted/fixed technical warnings remain required before export.

Geometry checks cannot establish emotional effectiveness or truthful protected-box annotations. Do not mark playback passed from a JSON validator or command exit. Generated character movement, parallax, depth warping, shakes, spins and transition effects are outside this feature.

Implementation references: [FFmpeg zoompan](https://ffmpeg.org/ffmpeg-filters.html#zoompan) and [loading option arguments from files](https://ffmpeg.org/ffmpeg.html#Options). This extension was authored without running a motion render or the regression suite in this change; no new playback verification is claimed.
