"""File and native reader differences for an explicit fresh Post project."""
from pathlib import Path


def content_set(record):
    entry = Path(record['entry_path'])
    return {Path(pin['path']).relative_to(entry.parent).as_posix(): (pin['bytes'], pin['sha256'])
            for pin in record['source_pins']}


def preview_change(original, replacement, metadata):
    old = {item['relative']: (item['bytes'], item['sha256']) for item in original['files']}
    new = content_set({'entry_path': replacement['path'], 'source_pins': replacement['source_pins']})
    files = [{'name': name, 'change': 'added' if name not in old else 'missing' if name not in new
              else 'same' if old[name] == new[name] else 'changed'} for name in sorted(set(old) | set(new))]
    prior = original.get('metadata') or {}
    keys = lambda data: {(row['association'], row['name']): row for row in data.get('arrays', [])}
    a, b = keys(prior), keys(metadata)
    arrays = [{'association': key[0], 'name': key[1], 'before': a.get(key), 'after': b.get(key)}
              for key in sorted(set(a) | set(b))]
    return {'files': files, 'content_changed': any(row['change'] != 'same' for row in files),
        'arrays': arrays, 'before': prior, 'after': metadata}
