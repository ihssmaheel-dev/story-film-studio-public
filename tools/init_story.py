#!/usr/bin/env python3
"""Start a story on its own story/<safe-slug> Git branch with exact source snapshots."""
import argparse
import hashlib
import json
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from story_git import create_story_branch, plan_story_branch, rollback_empty_branch, slugify

ROOT = Path(__file__).resolve().parents[1]
IMAGE_SUFFIXES = {'.png', '.jpg', '.jpeg', '.webp'}


def empty_story_source(original):
    text = original.decode('utf-8-sig').strip()
    if not text:
        return True
    if '[Paste your story here.]' not in text:
        return False
    template_lines = {
        '# Your story', '[Paste your story here.]', '## Optional preferences',
        'Paste the complete story, including its ending, below. A rough outline is welcome. The studio preserves the original and reads it completely.',
        'Skip anything already known from chat or your saved preset. Missing material choices are asked together.',
        'Saved preset:', 'Output (story only, written storyboard, or film; one video or parts) and length/flexibility:',
        'Language/performance and any voice preference:', 'Visual treatment/frame/subtitles:',
        'Story details, twists or ending to preserve:', 'Sound preferences, spending cap and tool/upload restrictions:',
    }
    return all(not line.strip() or line.strip() in template_lines for line in text.splitlines())


def select_references(paths, parser):
    """Validate all selected files before creating the story directory."""
    selected = []
    for path in paths:
        path = path.expanduser()
        source = (path if path.is_absolute() else ROOT / path).resolve()
        if not source.is_file():
            parser.error(f'Style reference is not a file: {source}')
        if source.suffix.lower() not in IMAGE_SUFFIXES:
            parser.error(f'Unsupported reference type: {source.name}; use PNG, JPG/JPEG or WebP')
        if source not in selected:
            selected.append(source)
    return selected


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('title')
    parser.add_argument('--base', help='Committed studio base; defaults to main, master, or the clone default branch')
    parser.add_argument(
        '--story-file', type=Path, default=ROOT / 'story.md',
        help='Original story text/Markdown; relative paths use the studio root',
    )
    parser.add_argument('--style', help='Free-form visual direction; remains draft until G3')
    parser.add_argument('--preset', default='default' if (ROOT / 'presets/default.json').is_file() else None,
                        help='Reuse saved preferences and selected treatment snapshots; never copies permission')
    parser.add_argument('--workflow', choices=('fast', 'strict'), help='New projects default to fast')
    parser.add_argument('--task', choices=('story', 'storyboard', 'film'), help='Limit the requested output scope')
    parser.add_argument(
        '--style-reference', action='append', type=Path, default=[], metavar='IMAGE',
        help='Selected reference file; repeat as needed. Relative paths use the studio root.',
    )
    parser.add_argument('--force', action='store_true', help='Not supported for safety')
    args = parser.parse_args()
    if args.force:
        parser.error('Overwriting a story is forbidden; choose a new title')
    try:
        slug = slugify(args.title)
    except ValueError as error:
        parser.error(str(error))
    if args.style is not None and not args.style.strip():
        parser.error('--style must contain a description')
    destination = ROOT / 'stories' / slug
    if destination.exists():
        parser.error(f'Story already exists: {destination}')
    sources = select_references(args.style_reference, parser)
    preset = None
    if args.preset:
        from workflow import load_preset, reference_sources
        try:
            preset = load_preset(args.preset)
            reference_sources(preset.get('style_references', []))
        except (ValueError, OSError, KeyError) as error:
            parser.error(str(error))
    story_source = args.story_file.expanduser()
    story_source = (story_source if story_source.is_absolute() else ROOT / story_source).resolve()
    if not story_source.is_file():
        parser.error(f'Story source is not a file: {story_source}')
    original = story_source.read_bytes()
    try:
        if empty_story_source(original):
            parser.error('Paste the actual story first; the empty intake template is not a story')
    except UnicodeError:
        parser.error('Use a UTF-8 text/Markdown story source; its original bytes will be preserved')
    try:
        plan = plan_story_branch(ROOT, slug, story_source, args.base)
        staging = ROOT / '.runtime/story-init'
        staging.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix='prepared-', dir=staging) as temporary:
            prepared = Path(temporary) / slug
            prepare_story(prepared, args, original, story_source, sources, preset)
            record = create_story_branch(ROOT, plan)
            try:
                (prepared / 'production/git.json').write_text(
                    json.dumps(record, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
                destination.parent.mkdir(parents=True, exist_ok=True)
                # Same-volume rename publishes only a complete, validated scaffold.
                prepared.rename(destination)
            except (OSError, ValueError):
                rollback_empty_branch(ROOT, plan)
                raise
    except (ValueError, OSError, RuntimeError, KeyError) as error:
        parser.error(str(error))
    print(f'Branch: {record["branch"]} (base {record["base_ref"]})')
    print(destination)


def prepare_story(destination, args, original, story_source, sources, preset):
    """Prepare everything before changing the checkout; invalid input leaves Git untouched."""
    shutil.copytree(ROOT / 'templates/story', destination)
    if preset:
        from workflow import apply_preferences
        # A new scaffold has template defaults, not prior user answers. Explicit
        # saved preferences (including false) must win over those defaults.
        apply_preferences(destination, preset, replace=True)
    workflow_path = destination / 'production/workflow.json'
    workflow = json.loads(workflow_path.read_text(encoding='utf-8'))
    if args.workflow:
        workflow['mode'] = args.workflow
    if args.task:
        workflow['task'] = args.task
    workflow_path.write_text(json.dumps(workflow, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    intake = {}
    intake_path = destination / 'creative/intake.json'
    if intake_path.is_file():
        intake = json.loads(intake_path.read_text(encoding='utf-8'))
        intake['title'] = args.title
        if args.style:
            intake['visual_style'] = args.style.strip()
        intake_path.write_text(json.dumps(intake, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    (destination / 'creative/original.md').write_bytes(original)
    (destination / 'creative/source.json').write_text(
        json.dumps({
            'schema_version': 1,
            'source_path': story_source.as_posix(),
            'snapshot_path': 'creative/original.md',
            'sha256': hashlib.sha256(original).hexdigest(),
            'copied_at_utc': datetime.now(timezone.utc).isoformat(timespec='seconds'),
            'audit_status': 'pending',
        }, ensure_ascii=False, indent=2) + '\n', encoding='utf-8',
    )
    readme = destination / 'README.md'
    readme.write_text(
        readme.read_text(encoding='utf-8').replace('# Story workspace', f'# {args.title}', 1),
        encoding='utf-8',
    )
    requested_style = args.style or intake.get('visual_style')
    if requested_style is not None:
        bible = destination / 'world/visual-bible.md'
        bible.write_text(
            bible.read_text(encoding='utf-8').replace(
                'Requested visual style: TBD (choose with the user)',
                f'Requested visual style: {requested_style.strip()}', 1,
            ),
            encoding='utf-8',
        )

    # Global inspiration is never inherited automatically. All snapshots stay draft.
    manifest_path = destination / 'references/style/manifest.json'
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    for source in sources:
        if any(record['sha256'] == hashlib.sha256(source.read_bytes()).hexdigest() for record in manifest['references']):
            continue
        index = len(manifest['references']) + 1
        snapshot = destination / 'references/style' / f'ref_{index:03d}{source.suffix.lower()}'
        shutil.copy2(source, snapshot)
        try:
            source_path = source.relative_to(ROOT).as_posix()
        except ValueError:
            source_path = source.as_posix()
        manifest['references'].append({
            'id': f'REF-STYLE-{index:03d}',
            'source_path': source_path,
            'source_filename': source.name,
            'snapshot_path': snapshot.relative_to(destination).as_posix(),
            'sha256': hashlib.sha256(snapshot.read_bytes()).hexdigest(),
            'copied_at_utc': datetime.now(timezone.utc).isoformat(timespec='seconds'),
            'role': 'TBD',
            'creator': None,
            'source_url': None,
            'usage_permission': 'unverified',
            'status': 'draft',
        })
    (destination / 'references/style/manifest.json').write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8',
    )


if __name__ == '__main__':
    main()
