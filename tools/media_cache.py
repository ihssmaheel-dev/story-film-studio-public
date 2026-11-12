"""Cache technical measurements by actual media/tool bytes; never cache human approval."""
from pathlib import Path

from studio_common import ROOT, atomic_json, executable, fingerprint, read_json, sha256_file


def measured(kind, source, calculate, tools=('ffmpeg',), parameters=None):
    source = Path(source).resolve()
    inputs = {'source': sha256_file(source), 'parameters': parameters,
              'cache_code': sha256_file(__file__), 'quality_code': sha256_file(Path(__file__).with_name('quality.py')),
              'tools': {name: sha256_file(path) if (path := executable(name)) else None for name in tools}}
    key = fingerprint(inputs)
    target = ROOT / '.runtime/cache/measurements' / kind / (key + '.json')
    try:
        record = read_json(target, {})
        if record.get('key') == key and record.get('checksum') == fingerprint(record['measurement']):
            return record['measurement']
    except (OSError, ValueError, KeyError, TypeError):
        pass
    result = calculate()
    atomic_json(target, {'key': key, 'measurement': result, 'checksum': fingerprint(result)})
    return result
