#!/usr/bin/env python3
"""Render concise review views from authoritative intake and audit records."""
import argparse
from pathlib import Path

from studio_common import atomic_text, read_json, sha256_file


def intake_view(project):
    from workflow import delivery_outputs, policy
    project = Path(project)
    data = read_json(project / 'creative/intake.json')
    lines = ['# Story and video intake', '', 'Generated from `creative/intake.json`; unanswered values remain undecided.', '']
    if policy(project)['task'] == 'film':
        outputs = delivery_outputs(project)
        lines.append('- **Delivery outputs:** ' + ('; '.join(outputs) if outputs else 'unanswered'))
    for key, value in data.items():
        if key != 'schema_version' and (key != 'continuous_edition' or data.get('mode') == 'parts'):
            lines.append(f'- **{key.replace("_", " ")}:** {value if value is not None else "unanswered"}')
    atomic_text(project / 'creative/intake.md', '\n'.join(lines) + '\n')


def audit_view(project):
    project = Path(project)
    audit = read_json(project / 'creative/audit-issues.json')
    ledger = read_json(project / 'continuity/story-ledger.json')
    source = sha256_file(project / 'creative/original.md')
    coverage = ledger.get('review_coverage', {})
    scenes = ledger.get('scenes', [])
    if not coverage.get('full_read_complete') or not coverage.get('second_pass_complete') or not scenes:
        raise ValueError('Full source read, scene coverage and second pass must actually be completed before publishing a full audit')
    if audit.get('source_sha256') != source or ledger.get('source_sha256') != source:
        raise ValueError('Audit and ledger must identify the exact preserved source')
    scene_ids = [scene['id'] for scene in scenes]
    if set(scene_ids) != set(coverage.get('reviewed_scene_ids', [])):
        raise ValueError('Some scenes are missing from actual review coverage')
    required = ('assessment', 'global_continuity', 'runtime_assessment', 'verdict')
    if any(not audit.get(field) for field in required):
        raise ValueError('Complete the assessment, global continuity, runtime and verdict records first')
    findings = audit.get('findings', [])
    severity = {'CRITICAL': 0, 'HIGH': 1, 'MEDIUM': 2, 'LOW': 3}
    identities = set()
    for finding in findings:
        if finding.get('id') in identities or finding.get('severity') not in severity:
            raise ValueError('Audit finding IDs must be unique and severity valid')
        identities.add(finding['id'])
        for field in ('classification', 'scene_ids', 'problem', 'evidence', 'impact', 'recommended_fix', 'confidence'):
            if field not in finding or finding[field] is None:
                raise ValueError(f'{finding["id"]}: missing {field}')
        if not set(finding['scene_ids']).issubset(set(scene_ids)):
            raise ValueError(f'{finding["id"]}: unknown scene reference')
    ordered = sorted(findings, key=lambda finding: severity[finding['severity']])
    critical = [finding['id'] for finding in ordered if finding['severity'] == 'CRITICAL' and finding['classification'] == 'confirmed issue']
    lines = ['# Complete story audit', '', f'Revision: {audit.get("revision", "r1")}',
             f'Source SHA-256: {source}', f'Coverage: {len(scene_ids)}/{len(scene_ids)} scenes; full read and second pass recorded.', '',
             '## A. Overall Assessment', '', audit['assessment'], '', '## B. Critical Issues', '',
             ', '.join(critical) if critical else 'No confirmed critical issues were identified within the completed review.', '',
             '## C. Complete Issue List', '']
    if not ordered:
        lines.extend(['No issues were identified within the recorded scope. This is not a guarantee of perfection.', ''])
    for finding in ordered:
        lines.extend([f'### {finding["id"]} — {finding["severity"]} — {finding["classification"]}', ''])
        for field in ('scene_ids', 'problem', 'evidence', 'impact', 'recommended_fix', 'example', 'assumptions', 'confidence', 'disposition'):
            if field in finding:
                lines.append(f'**{field.replace("_", " ")}:** {finding[field]}')
        lines.append('')
    lines.extend(['## D. Scene-by-Scene Analysis', ''])
    reviews = audit.get('scene_reviews', {})
    for scene in scenes:
        review = reviews.get(scene['id'])
        if not review:
            raise ValueError(f'Missing scene analysis for {scene["id"]}; do not silently omit it')
        lines.extend([f'### {scene["id"]} — {scene.get("heading", "Source scene")}', '', review, ''])
    lines.extend(['## E. Global Continuity Report', '', audit['global_continuity'], '',
                  '## F. Unresolved Questions', ''])
    lines.extend(['- ' + question for question in audit.get('unresolved_questions', [])] or ['No material unresolved question recorded.'])
    lines.extend(['', '## G. Target Runtime and Part Structure Assessment', '', audit['runtime_assessment'], '',
                  '## H. Prioritized Correction Checklist', ''])
    for optional in (False, True):
        lines.extend(['Optional improvements:' if optional else 'Essential corrections:', ''])
        selected = [finding for finding in ordered if bool(finding.get('optional', False)) == optional]
        lines.extend([f'{index}. {finding["id"]}: {finding["recommended_fix"]}' for index, finding in enumerate(selected, 1)] or ['None recorded.'])
        lines.append('')
    lines.extend(['## I. Final Verdict', '', audit['verdict'], '',
                  'Correction proposals remain unapplied. Explicit permission for selected fixes is required; G1 is separate.'])
    atomic_text(project / 'creative/audit-report.md', '\n'.join(lines) + '\n')


def decision_pack(project):
    from project_records import approval_status
    from workflow import policy
    project = Path(project)
    if policy(project)['mode'] == 'fast':
        return fast_decision_pack(project)
    log, stale = approval_status(project)
    lines = ['# Review summary', '', 'Full reports and canonical records remain authoritative.', '',
             '| Gate | Status |', '|---|---|']
    for gate in ('G1', 'G2', 'G3', 'G4', 'G5', 'G6'):
        lines.append(f'| {gate} | {"stale" if gate in stale else log.get("gates", {}).get(gate, {}).get("status", "draft")} |')
    lines.extend(['', 'Full audit: `creative/audit-report.md`', 'Intake: `creative/intake.md`',
                  'Selected fixes/permission: `creative/editorial-decisions.md`',
                  'Part plan: `creative/part-plan.md`', 'Visual bible: `world/visual-bible.md`',
                  'Written shots: `creative/all-parts-review.md`', 'Sound: `audio/sound-plan.md`', '',
                  'Ask only for material unanswered choices or the particular gate/revision ready for review.'])
    atomic_text(project / 'production/review-summary.md', '\n'.join(lines) + '\n')


def focused_audit_view(project):
    from workflow import audit_problems
    project = Path(project)
    errors = audit_problems(project, block_findings=False)
    if errors:
        raise ValueError('; '.join(errors))
    audit = read_json(project / 'creative/audit-issues.json')
    ledger = read_json(project / 'continuity/story-ledger.json')
    lines = ['# Story review', '', audit['assessment'], '',
             f'Coverage: {len(ledger["scenes"])} scenes; complete read and focused cross-check recorded.',
             f'Source SHA-256: {audit["source_sha256"]}', '', '## Material findings', '']
    findings = [item for item in audit.get('findings', []) if item.get('disposition') != 'resolved']
    for item in findings:
        lines.extend([f'- **{item["id"]} ({item["severity"]}):** {item["problem"]} '
                      f'Proposed action: {item["recommended_fix"]}'])
    if not findings:
        lines.append('No unresolved finding recorded within the reviewed scope.')
    if audit.get('unresolved_questions'):
        lines.extend(['', '## Decisions needed', '', *['- ' + item for item in audit['unresolved_questions']]])
    lines.extend(['', '## Runtime and outcome', '', audit.get('runtime_assessment') or 'Runtime remains provisional.',
                  '', audit['verdict'], '', 'Detailed evidence remains in audit-issues.json and story-ledger.json. '
                  'This is a focused review, not a claim of a complete second pass or an A–I audit.'])
    atomic_text(project / 'creative/audit-report.md', '\n'.join(lines) + '\n')


def fast_decision_pack(project):
    from workflow import audit_problems, delegation_status, delivery_outputs, policy, questions
    project = Path(project)
    value = policy(project)
    intake = read_json(project / 'creative/intake.json')
    status, _ = delegation_status(project)
    lines = ['# Studio review', '', f'Mode: Fast · Output: {value["task"]} · Configuration authorization: {status}', '',
             '## Your configuration', '']
    for label in ('mode', 'duration_policy', 'language', 'performance', 'visual_style', 'frame_format', 'subtitles'):
        if value['task'] == 'film':
            lines.append(f'- {label.replace("_", " ")}: {intake.get(label) if intake.get(label) is not None else "unanswered"}')
    if value['task'] == 'film':
        lines.append('- Deliver: ' + ('; '.join(delivery_outputs(project)) or 'unanswered'))
        profile = read_json(project / 'audio/narrator.json')
        from speech_providers import voice_config
        narrator = voice_config(profile)
        providers = sorted({narrator['provider'], *[voice_config(profile, speaker)['provider'] for speaker in profile.get('cast', {})]})
        lines.append('- Speech providers: ' + ', '.join(providers))
        lines.append('- Narrator: ' + str(narrator['voice'] or 'agent selects within configured scope') + '; model: ' + str(narrator['model']))
        lines.append(f'- Character voice assignments: {len([name for name in profile.get("cast", {}) if name != "NARRATOR"])}; see audio/narrator.json')
    lines.extend(['', f'Tool/budget/upload scope: {value["scope"]}',
                  f'Minor edits: {value["minor_edits"]}; major story changes always need a decision.', '',
                  '## Important questions', ''])
    lines.extend(['- ' + item for item in questions(project)] or ['No configuration question remains.'])
    lines.extend(['', '## Studio work', ''])
    lines.extend(['- ' + item for item in audit_problems(project)] or ['Story review is current. Continue the configured work.'])
    lines.extend(['', 'Image comparisons, sound listening, alignment checks and playback are agent tasks. '
                  'Ask the user only for an unresolved creative choice, changed scope or the finished preview decision. '
                  'Fast mode does not create G1–G6 signoffs.'])
    atomic_text(project / 'production/review-summary.md', '\n'.join(lines) + '\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('project', type=Path)
    parser.add_argument('--audit', action='store_true')
    parser.add_argument('--full-audit', action='store_true', help='Generate the complete A–I report only after a real full second pass')
    args = parser.parse_args()
    try:
        from story_git import require_story_branch
        require_story_branch(args.project)
        intake_view(args.project)
        if args.audit or args.full_audit:
            from workflow import policy
            if args.full_audit or policy(args.project)['mode'] == 'strict' or policy(args.project)['audit'] == 'full':
                audit_view(args.project)
            else:
                focused_audit_view(args.project)
        decision_pack(args.project)
        print(args.project / 'production/review-summary.md')
    except (ValueError, OSError, KeyError) as error:
        parser.error(str(error))


if __name__ == '__main__':
    main()
