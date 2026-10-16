"""Pinned offline reference documents and their redistribution notices.

Loading verifies every original and license notice before callers may import it.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

PACK=Path(__file__).with_name('research_knowledge')/'manifest.json'


def _json(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def load_pack(manifest=PACK):
    """Verify every supplied original/notice before any upload or mutation."""
    path=Path(manifest).resolve();data=_json(path);seen=set()
    for entry in data['documents']:
        if entry['id'] in seen:raise ValueError('Duplicate source name')
        seen.add(entry['id'])
    for item in data['assets']:
        source=path.parent/item['path']
        if (source.is_symlink() or not source.resolve().is_relative_to(path.parent)
                or not source.is_file()):raise ValueError('Missing or escaped pack asset: '+item['path'])
        raw=source.read_bytes()
        if len(raw)!=item['bytes'] or hashlib.sha256(raw).hexdigest()!=item['sha256']:
            raise ValueError('Pack original/notice hash differs: '+item['path'])
    assets={v['path']:v for v in data['assets']}
    for entry in data['documents']:
        if entry['availability']=='BUNDLED':
            if entry['file'] not in assets or not entry['license']['redistribution_permitted']:
                raise ValueError('Bundled source requires its original pin and document permission')
            for notice in entry['license']['local_notices']:
                if notice not in assets:raise ValueError('Document license notice is not pinned')
    return data
