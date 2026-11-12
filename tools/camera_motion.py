"""Validate and compile bounded camera movement over still images; never invent shot direction."""
import math


MAX_ZOOM = 1.20
TYPES = ('static', 'zoom_in', 'zoom_out', 'pan')


def number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def normalize_motion(value=None):
    """Return explicit poses. Missing motion preserves the historical full-frame static hold."""
    if value is None:
        value = {'type': 'static'}
    if not isinstance(value, dict):
        raise ValueError('motion must be an object or null')
    allowed = {'type', 'reason', 'start', 'end', 'easing', 'start_at', 'end_at', 'protected_regions'}
    if set(value) - allowed:
        raise ValueError('Unknown motion fields: ' + ', '.join(sorted(set(value) - allowed)))
    kind = value.get('type', 'static')
    if kind not in TYPES:
        raise ValueError('motion.type must be static, zoom_in, zoom_out or pan')
    reason = value.get('reason', '')
    if not isinstance(reason, str) or (kind != 'static' and not reason.strip()):
        raise ValueError('Moving shots require a written story reason')
    defaults = {
        'static': ((1.0, [0.5, 0.5]), (1.0, [0.5, 0.5])),
        'zoom_in': ((1.0, [0.5, 0.5]), (1.08, [0.5, 0.5])),
        'zoom_out': ((1.08, [0.5, 0.5]), (1.0, [0.5, 0.5])),
        'pan': ((1.10, [0.47, 0.5]), (1.10, [0.53, 0.5])),
    }
    poses = {}
    for index, edge in enumerate(('start', 'end')):
        pose = value.get(edge, {})
        if not isinstance(pose, dict) or set(pose) - {'zoom', 'center'}:
            raise ValueError(f'motion.{edge} accepts only zoom and center')
        zoom = pose.get('zoom', defaults[kind][index][0])
        center = pose.get('center', defaults[kind][index][1])
        if not number(zoom) or not 1 <= zoom <= MAX_ZOOM:
            raise ValueError(f'motion.{edge}.zoom must be between 1 and {MAX_ZOOM}')
        if not isinstance(center, list) or len(center) != 2 or not all(number(v) for v in center):
            raise ValueError(f'motion.{edge}.center must be two finite normalized coordinates')
        half = 0.5 / zoom
        if any(c < half - 1e-9 or c > 1 - half + 1e-9 for c in center):
            raise ValueError(f'motion.{edge}: crop leaves the image; adjust zoom/center')
        poses[edge] = {'zoom': zoom, 'center': list(center)}
    start, end = poses['start'], poses['end']
    if kind == 'static' and (start != {'zoom': 1.0, 'center': [0.5, 0.5]} or start != end):
        raise ValueError('static motion must preserve the complete frame')
    if kind == 'zoom_in' and end['zoom'] <= start['zoom']:
        raise ValueError('zoom_in requires end.zoom greater than start.zoom')
    if kind == 'zoom_out' and end['zoom'] >= start['zoom']:
        raise ValueError('zoom_out requires end.zoom smaller than start.zoom')
    if kind == 'pan' and (start['zoom'] != end['zoom'] or start['center'] == end['center']):
        raise ValueError('pan requires constant zoom and different start/end centers')
    easing = value.get('easing', 'smoothstep')
    if easing not in ('smoothstep', 'linear'):
        raise ValueError('motion.easing must be smoothstep or linear')
    first, last = value.get('start_at', 0.0), value.get('end_at', 1.0)
    if not all(number(v) for v in (first, last)) or not 0 <= first < last <= 1:
        raise ValueError('motion start_at/end_at must satisfy 0 <= start_at < end_at <= 1')
    regions = value.get('protected_regions', [])
    if not isinstance(regions, list) or (kind != 'static' and not regions):
        raise ValueError('Moving shots require protected_regions for details that must stay visible')
    ids = set()
    for region in regions:
        if not isinstance(region, dict) or set(region) - {'id', 'box'}:
            raise ValueError('Each protected region accepts only id and box')
        identity, box = region.get('id'), region.get('box')
        if not isinstance(identity, str) or not identity.strip() or identity in ids:
            raise ValueError('Protected regions require unique nonempty IDs')
        ids.add(identity)
        if not isinstance(box, list) or len(box) != 4 or not all(number(v) for v in box):
            raise ValueError('Protected box must be [left, top, right, bottom] normalized coordinates')
        left, top, right, bottom = box
        if not (0 <= left < right <= 1 and 0 <= top < bottom <= 1):
            raise ValueError('Protected box must have positive area inside the image')
        for pose in poses.values():
            x, y = pose['center']
            half = 0.5 / pose['zoom']
            if left < x - half - 1e-9 or right > x + half + 1e-9 or top < y - half - 1e-9 or bottom > y + half + 1e-9:
                raise ValueError(f'Protected region {identity} is cut by the camera path')
    # Center and inverse zoom interpolate with the same monotonic parameter. Crop edges
    # therefore interpolate linearly, so containment at both endpoints covers the full path.
    return {'type': kind, 'reason': reason, **poses, 'easing': easing, 'start_at': first,
            'end_at': last, 'protected_regions': regions}


def active_motion(shot):
    return normalize_motion(shot.get('motion'))['type'] != 'static'


def source_motion_issues(size, width, height, motion):
    """Separate frame-safety errors from resolution warnings; coordinates use the full frame."""
    errors, warnings = [], []
    if motion['type'] == 'static':
        return errors, warnings
    source_width, source_height = size
    if abs(source_width / source_height - width / height) > max(1 / source_height, (width / height) * 0.001):
        errors.append('moving shots require a source matching the delivery aspect; recompose before rendering')
    zoom = max(motion['start']['zoom'], motion['end']['zoom'])
    if source_width / zoom < width or source_height / zoom < height:
        warnings.append('source resolution is below the largest camera crop; inspect enlarged detail/sharpness')
    return errors, warnings


def camera_filter(data, width, height):
    """Compile one continuous zoompan filter, preserving the concat clock and shot boundaries."""
    fps = data['fps']
    values = []

    def literal(value):
        return format(value, '.15g')

    for shot in data['shots']:
        motion = normalize_motion(shot.get('motion'))
        first, stop = round(shot['start'] * fps), round(shot['end'] * fps)
        if stop <= first or (motion['type'] != 'static' and stop - first < 2):
            raise ValueError(f'{shot["id"]}: camera timeline needs at least one frame per hold and two per move')
        raw = f'((on-{first})/{max(1, stop-first-1)})'
        t = f'clip(({raw}-{literal(motion["start_at"])})/{literal(motion["end_at"]-motion["start_at"])},0,1)'
        if motion['easing'] == 'smoothstep':
            t = f'({t}*{t}*(3-2*{t}))'

        def interpolate(a, b):
            return literal(a) if a == b else f'({literal(a)}+({literal(b-a)})*{t})'

        start, end = motion['start'], motion['end']
        inverse_zoom = interpolate(1 / start['zoom'], 1 / end['zoom'])
        zoom = f'(1/({inverse_zoom}))'
        x = interpolate(start['center'][0], end['center'][0])
        y = interpolate(start['center'][1], end['center'][1])
        values.append((first, zoom, x, y))

    def piecewise(items, index):
        if len(items) == 1:
            return items[0][index]
        middle = len(items) // 2
        return f'if(lt(on,{items[middle][0]}),{piecewise(items[:middle],index)},{piecewise(items[middle:],index)})'

    zoom, x, y = (piecewise(values, index) for index in (1, 2, 3))
    return (f'fps={fps},format=yuv444p,'
            f"zoompan=z='{zoom}':x='max(0,min(iw-iw/zoom,iw*({x})-iw/(2*zoom)))':"
            f"y='max(0,min(ih-ih/zoom,ih*({y})-ih/(2*zoom)))':d=1:s={width}x{height}:fps={fps},"
            'setsar=1,format=yuv420p')
