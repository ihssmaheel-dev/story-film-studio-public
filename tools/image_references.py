"""Resolve exact style snapshots and label the role of every attached reference image."""
from pathlib import Path

from project_records import artifact_path
from studio_common import ROOT, fingerprint, read_json, sha256_file


ROLES = {'styles': 'visual treatment only; use the written story for cast, setting, palette and mood',
         'characters': 'canonical character identity, silhouette, face and costume; apply the written shot state',
         'locations': 'canonical location geometry and landmarks; preserve the written camera orientation',
         'props': 'canonical prop design, scale and attachments; apply the written ownership and state'}


class References:
    def __init__(self, project):
        self.project = Path(project).resolve()
        self.bindings = []
        self.scoped = {}
        self.traits = read_json(ROOT / 'references/style/visual-preferences/fidelity.json', {}).get('styles', [])

    def add(self, name, identity, role, expected=None):
        from PIL import Image
        path = artifact_path(self.project, name)
        if not path.is_file():
            raise ValueError('Missing image reference: ' + name)
        digest = sha256_file(path)
        if expected is not None and digest != expected:
            raise ValueError('Selected style snapshot changed; restore its exact recorded path/hash: ' + name)
        if path.suffix.lower() not in ('.png', '.jpg', '.jpeg', '.webp'):
            raise ValueError('Unsupported image reference: ' + name)
        with Image.open(path) as picture:
            picture.verify()
        # A shared cast sheet or copied style snapshot is attached once, with every actual role retained.
        binding = next((item for item in self.bindings if item['sha256'] == digest), None)
        if binding is None:
            binding = {'index': len(self.bindings) + 1, 'path': str(path), 'artifact_path': name,
                       'sha256': digest, 'roles': []}
            self.bindings.append(binding)
        use = {'entity_id': identity, 'role': role}
        if use not in binding['roles']:
            binding['roles'].append(use)
        traits = next((item for item in self.traits if item['sha256'] == digest), None)
        if traits and identity.startswith('STYLE-'):
            binding['style_traits'] = traits['traits']

    def entity(self, identity, group, record):
        self.scoped[identity] = {'group': group, 'record': record}
        if group == 'characters':
            from cast import profiles
            profile = profiles(self.project).get(identity)
            if profile:
                self.scoped[identity]['cast_profile'] = profile
        for name in record.get('reference_paths', []):
            row = next((row for row in self.snapshots() if row.get('snapshot_path') == name), None)
            expected = self.snapshot_hash(row) if row else None
            self.add(name, identity, ROLES[group], expected)

    def snapshot_hash(self, row):
        expected = row.get('sha256')
        if not isinstance(expected, str) or len(expected) != 64:
            raise ValueError('Selected style snapshot needs its exact recorded SHA-256')
        return expected

    def snapshots(self):
        return read_json(self.project / 'references/style/manifest.json', {}).get('references', [])

    def inspiration(self, identity, record, is_style=False, allow_default=False):
        snapshots = self.snapshots()
        names = record.get('inspiration_paths', [])
        if is_style and not names and allow_default:
            mapped = [row for row in snapshots if row.get('snapshot_path') in record.get('reference_paths', [])]
            if mapped:
                names = [row['snapshot_path'] for row in mapped]
            elif len(snapshots) > 1:
                raise ValueError('Map the selected style inspiration_paths explicitly; multiple historical snapshots are ambiguous')
            else:
                names = [row['snapshot_path'] for row in snapshots]
        for name in names:
            normalized = name.replace('\\', '/')
            matches = [row for row in snapshots if row.get('snapshot_path') == name
                       or row.get('source_path', '').replace('\\', '/').endswith('/' + normalized)
                       or row.get('source_path', '').replace('\\', '/') == normalized]
            # Never reinterpret an old filename/ID as today's gallery file. Its recorded snapshot wins.
            if len(matches) > 1:
                raise ValueError('Ambiguous style source; bind its exact snapshot_path: ' + name)
            row = matches[0] if matches else None
            role = ROLES['styles'] if is_style else 'design inspiration only; the written canonical identity takes precedence'
            if row:
                role += '; selected contribution: ' + str(row.get('role', 'visual treatment only'))
                self.add(row['snapshot_path'], identity, role, self.snapshot_hash(row))
            else:
                self.add(name, identity, role)

    def contract(self):
        lines = ['REFERENCE IMAGE ROLES (numbers match the attached image order):']
        for item in self.bindings:
            lines.append('Image ' + str(item['index']) + ': ' + '; '.join(
                use['entity_id'] + ' — ' + use['role'] for use in item['roles']))
            if item.get('style_traits'):
                lines.append('Observed treatment to retain, except explicit visual-bible refinements: ' + '; '.join(item['style_traits']))
        lines.append('Use canonical written facts for story identity, action, chronology and current state. '
                     'Use each image only for its stated contribution. A treatment example does not supply its people, '
                     'wardrobe, letter, station, pose, daylight or color palette to this story. '
                     'Keep the selected medium/anatomy/material rules throughout characters and scenery. '
                     'Apply explicit story-driven costume, injury, aging, lighting and prop-state changes without changing identity. '
                     'Resolve a real canonical conflict before generation; do not average incompatible references.')
        return '\n'.join(lines)

    def hashes(self):
        return {item['path']: item['sha256'] for item in self.bindings}


def collect(project, request):
    project = Path(project).resolve()
    registry = read_json(project / 'continuity/entities.json')
    entities = {identity: (group, record) for group in ROLES for identity, record in registry.get(group, {}).items()}
    refs = References(project)
    shot = frame = None
    if request['kind'] == 'final':
        part = artifact_path(project, 'parts/' + request['part_id'])
        matches = [s for s in read_json(part / 'shots.json')['shots'] if s.get('id') == request['shot_id']]
        if len(matches) != 1:
            raise ValueError('Image request must identify exactly one current written shot')
        shot = matches[0]
        style_id = shot.get('style_id')
        ids = [style_id, shot.get('location_id'), *shot.get('character_ids', []), *shot.get('prop_ids', [])]
        timeline = read_json(part / 'timeline.json')
        frame = {key: timeline[key] for key in ('width', 'height')}
    else:
        target = request['entity_id']
        if target not in entities:
            raise ValueError('Register the entity before requesting its reference')
        group, record = entities[target]
        style_id = target if group == 'styles' else record.get('style_id')
        if style_id is None and len(registry.get('styles', {})) == 1:
            style_id = next(iter(registry['styles']))
        ids = [style_id, target]
    if style_id not in registry.get('styles', {}):
        raise ValueError('Bind the reference entity to its exact registered style_id before generation')
    for identity in dict.fromkeys(filter(None, ids)):
        if identity not in entities:
            raise ValueError('Unknown canonical entity ' + identity)
        group, record = entities[identity]
        if record.get('style_id') not in (None, style_id):
            raise ValueError(identity + ': reference style_id conflicts with the written shot style')
        refs.entity(identity, group, record)
        if group == 'styles':
            if refs.snapshots() and not record.get('inspiration_paths') and len(registry['styles']) > 1:
                raise ValueError('Map selected inspiration_paths to the exact style_id; do not mix multiple styles')
            refs.inspiration(identity, record, is_style=True, allow_default=True)
        elif request['kind'] == 'reference':
            refs.inspiration(identity, record)
            for name in record.get('revision_reference_paths', record.get('previous_reference_paths', [])):
                refs.add(name, identity, 'previous character identity; preserve unaffected traits and apply the explicit revised design')
    context = fingerprint({'kind': request['kind'], 'shot': shot, 'frame': frame,
                           'entities': refs.scoped, 'reference_bindings': refs.bindings})
    return refs, context


def require_current(project, request):
    if request.get('prompt_context_sha256'):
        _, current = collect(project, request)
        if current != request['prompt_context_sha256']:
            raise ValueError('Image prompt context changed; preserve any actual result and compile a current request')
