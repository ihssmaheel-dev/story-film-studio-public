# Complete story and screenplay audit

> **Mode:** This is the complete audit and twelve-area reference. Strict or `audit: full` follows every section. Fast focused review reads the complete source, checks all twelve areas and cross-checks risky details, using the concise report and actual delegated minor-edit policy in `docs/13-fast-workflow.md`. Do not call its focused check a full second pass. Major changes always require permission before editing.

This is the mandatory editorial review procedure before G1. Apply it to prose, outlines, screenplays, short stories and long-form stories in any genre or visual style. The studio agent performs the review; no script in `tools/` can establish narrative correctness automatically. Use editorial judgment without claiming real-world credentials or a history of professional employment.

## 1. Read the entire source and establish coverage

Read from the beginning through the ending before judging individual passages. Later scenes may explain an apparent contradiction. Preserve the original source exactly in `creative/original.md` after the title is agreed, record its SHA-256, and never edit that file as a correction. If the project has not been created yet, provide the audit in chat and persist it after the title is agreed.

Confirm whether the material is complete. For a story supplied in chunks, keep an ordered receipt/coverage list, wait for the ending or the user's confirmation that all sections have arrived, then audit the full source. A requested review of an incomplete work must state its limited scope; never call it a complete audit. For long sources, maintain checkpoints and continue until every section is covered rather than dropping later scenes.

Create `creative/scene-map.md`: stable `SCENE-001` IDs, original order, headings or exact passage anchors, summary, people present, location, story time and next-scene connection. For unformatted prose, identify scene/beat units without rewriting the text. Include scene count, source ranges and any unread/unavailable material. Keep source presentation order distinct from chronological order.

Understand the premise, themes, intended ending, protagonist/antagonist pressures, goals, relationships, arcs, event chronology, fictional rules, important objects, facts, clues, secrets and setups/payoffs. Maintain evidence in `continuity/story-ledger.json`; do not promote draft observations to approved world canon.

## 2. Review every scene across all twelve areas

### 1. Plot logic and contradictions

Look for unexplained events, actions based on unavailable information, inadequate setup, unjustified decisions, coincidence solving central conflicts, obvious solutions ignored without cause, contradictions of earlier facts and last-minute rescue information/abilities. Check open questions against the ending. Distinguish a confirmed hole from an intentional mystery, cinematic convention, possible omission or a question for the author. Do not demand an explanation for every incidental detail.

### 2. Scene connections and physical continuity

Check the causal connection to the preceding scene, entry/exit conditions, character presence, travel, available time and ongoing conversations/confrontations. Track location, clothing, injuries, carried objects, weapons, evidence, vehicles, doors and environmental state. Identify impossible appearances, missing actions and abrupt/unclear transitions. Note whether each scene begins and ends at a comprehensible point and leads into the next scene.

### 3. Character consistency and motivation

For every significant character, compare goals, personality, decisions, emotions, relationships, skills, intelligence, resources and limitations across the complete story. Check consequences and earned changes. Consider fear, grief, desperation, arrogance, trauma, deception, incomplete information and mistakes before calling an action irrational. Preserve unusual behavior that is intentionally and credibly motivated; identify behavior that exists only to move the plot.

### 4. Timeline and chronology

Build the actual story chronology, including offscreen prerequisites. Test stated and implied times, travel durations, parallel actions, ages, deadlines, countdowns, day/night, weather, recovery and elapsed time. Check flashbacks/time jumps for legibility and the finale against the time available. Record contradictions and uncertain intervals separately; do not replace missing dates with invented precision.

### 5. Cause and effect

For each major development identify its cause, motivating knowledge/circumstances, character choice and consequence. Check that the next event follows from this chain. Expose missing causal steps, unearned access/resources and unrelated scenes. Consider whether the obstacle, choice and resulting cost are understandable to the audience.

### 6. Knowledge, secrets and revelations

Track who knows each fact, when/how they learn it, who tells whom, lies, false beliefs, withheld information and the audience's separate knowledge. Test conclusions against available clues and dialogue against knowledge at that scene's time. Verify that twists and later explanations preserve established truth. Intentional deception by a character is not automatically an author error.

### 7. World rules and factual plausibility

Check established abilities, technology, science, medicine, law/police/military procedures, weapons/injuries, surveillance/security/communications, geography, money, logistics and access where material to the plot. Judge fantasy and stylization by their declared rules. Separate real-world claims from fictional conventions. Verify specialized facts with actual reliable sources where available; record links and what was checked. Mark unverified claims and assumptions honestly instead of inventing evidence or rewriting around a guessed fact.

### 8. Dialogue and information

Review every supplied line for contradictions, wrong names/dates/relationships/facts, unexplained knowledge, unnatural repetition, missing replies, abrupt subject changes, unclear references, convenient explanations and conflict with visible action. Preserve intended meaning, individual voice, tone and strong dialogue. Do not rewrite effective dialogue merely to make it different.

### 9. Language, format and visual clarity

Check spelling, grammar, punctuation, capitalization, names, pronouns, missing/duplicated words, incomplete sentences and ambiguous actions. For a screenplay, check scene headings, INT./EXT., time labels, character cues, dialogue blocks, parentheticals and transitions against valid conventions. For prose/outlines, use the appropriate conventions instead of imposing screenplay formatting. Identify instructions that cannot be visualized clearly and action/dialogue contradictions.

### 10. Setups, clues and payoffs

Track important objects, promises, threats, abilities, relationships and information from introduction to use/payoff. Confirm that decisive tools and clues exist early enough, consequences are addressed, twists are earned, and the ending respects earlier setups. Identify abandoned material while allowing deliberate ambiguity and incidental texture. Recommend payoff, clarification or removal only with a stated reason and author permission for changes.

### 11. Pacing and the user's target duration

Assess the selected single-video or part-by-part format and the user's requested total/per-part duration or explicitly flexible length. There is no assumed 30-minute film or one-minute default. Consider performed dialogue/narration, action, silence, visual storytelling, transitions, scene complexity and emotional processing time. Give a justified runtime range and confidence, not a word-count-only promise. Identify repetition, excess explanation, rushed turns, underdeveloped stakes and weak openings/endings. Do not pad or cut solely to force a target; present tradeoffs when story and duration conflict. If duration is unanswered, label the runtime assessment provisional and continue the other checks.

### 12. Emotional and dramatic credibility

Check whether relationships, reactions, betrayals, sacrifices, deaths, victories and losses have adequate context. Follow emotional transitions across scenes, the character choices driving the climax and resolution, and whether logic errors undermine intended feeling. Preserve the author's genre, atmosphere, tension, themes and emotional ending. Explain craft concerns using evidence, not personal taste alone.

## 3. Record precise, actionable findings

Assign stable IDs such as `AUDIT-001`. Never renumber existing IDs simply because another issue was resolved. Each finding records:
- Source revision/hash and exact scene ID, heading or short original quotation.
- Classification: `confirmed issue`, `possible issue`, `needs verification`, or `intentional ambiguity`; optional craft proposals are labeled separately.
- Severity: `CRITICAL` (central plot/understanding fails), `HIGH` (significant logic/motivation/continuity failure), `MEDIUM` (noticeable inconsistency/confusion), `LOW` (minor wording/format/clarity).
- The exact problem, supporting/conflicting passages and any assumptions.
- Why it affects comprehension, causality, characterization, emotion or production clarity.
- The smallest practical fix, an optional short example, alternatives and tradeoffs.
- All affected scenes/entities, downstream consequences and author decisions needed.
- Confidence, external verification status and proposed disposition.

Do not invent criticism to fill a quota. Avoid duplicates by linking multiple manifestations to the underlying issue. Examples in the report are proposals, not edits to the manuscript. Keep optional improvements separate from essential corrections.

## 4. Perform a complete second pass

Re-read/cross-check the complete story after the first findings pass. Check distant scenes, finale-to-opening dependencies, small details important at the climax, true unresolved questions and anything missed earlier. Test every proposed fix against character knowledge, timeline, rules, props, setups/payoffs and ending; flag a proposed fix that introduces a new problem. Record actual coverage and second-pass completion in the report, with remaining uncertainties. Never pre-check these fields from the template or claim perfection because no error was found.

## 5. Deliver the full audit report in this order

Save `creative/audit-report.md` at a numbered revision tied to the audited source hash. Present the full report or a readable summary plus the complete local report path; never provide only a list of highlights.

A. **Overall Assessment:** scope/coverage, strengths with evidence, logical consistency, clarity, continuity and editorial readiness.

B. **Critical Issues:** confirmed critical findings first; explicitly say none were identified when appropriate to the reviewed scope.

C. **Complete Issue List:** every confirmed issue, ordered by severity, with the evidence/fix fields above. Clearly separate possible/unverified findings from confirmed ones; give totals by severity/classification.

D. **Scene-by-Scene Analysis:** every mapped scene in original order; what works, specific issue IDs, missing context, dialogue/format problems and connection to the next scene. Briefly say when no issue was identified. Reconcile reviewed scene count with the source coverage list.

E. **Global Continuity Report:** chronology, character knowledge/motives, locations/travel, objects/injuries/evidence, relationships/arcs, rules/factual verification, and setups/clues/reveals/payoffs. Link ledger entries and scene evidence.

F. **Unresolved Questions:** material omissions and required author decisions, separated from intentional ambiguity and optional curiosity. Include unanswered intake constraints that materially affect the audit.

G. **Target Runtime and Part Structure Assessment:** justified duration range, confidence, user's target/flexibility, scene/part pacing, likely split points and conflicts/tradeoffs. Recommendations remain proposals before G2.

H. **Prioritized Correction Checklist:** dependency-aware order, essential fixes and a separate optional list, issue IDs, proposed scope and smallest viable alternatives.

I. **Final Verdict:** `NOT READY`, `NEEDS REVISION`, `NEARLY PRODUCTION-READY`, or `NO SIGNIFICANT ISSUES FOUND`, justified within the reviewed editorial scope. These labels do not approve production, rights, factual claims not checked, or G1–G6. State remaining limitations.

## 6. Obtain permission before correcting the story

The attached source prompt's automatic rewrite instruction is replaced by this user's permission requirement. Finish and present the report before asking whether to apply fixes. Record the specific report revision/hash, issue IDs, scope, protected creative choices and the user's decision in `creative/editorial-decisions.md`. For example: "May I apply essential fixes AUDIT-001 and AUDIT-004 from audit r1, preserving the ending?" Permission must cover the actual fixes; silence, praise, choosing a duration or approving the audit as accurate is not permission to rewrite.

After explicit permission, create a complete `creative/story-revised.md` at a new revision, preserving the original and exact scene order unless the authorized fix changes it. Correct only authorized issues consistently throughout. Retain strong scenes, voice, language, characters, premise, twists and ending. Do not silently introduce/remove important material or apply optional changes. If a fix needs a major unapproved creative decision, present alternatives and pause that dependent edit while continuing independent authorized work.

Return the full revised work, not a synopsis, and `creative/change-log.md` mapping issue IDs to edits, affected scenes and residual/deferred issues. For long work, use ordered sections with no omissions and a continuity checkpoint. Re-audit the revised text, including a full consistency cross-check, and update finding dispositions. Then request explicit G1 approval of the final story revision. Permission to make fixes and final G1 approval are separate decisions.
