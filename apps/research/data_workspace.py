"""Data-only local history and atomic view recovery; Core remains authoritative."""
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import tempfile

from PySide6.QtCore import QStandardPaths
from PySide6.QtWidgets import QTableWidgetItem


class SourceItem(QTableWidgetItem):
    def __lt__(self, other):
        try:
            return float(self.text()) < float(other.text())
        except ValueError:
            return self.text() < other.text()


class DraftHistory:
    def __init__(self, draft):
        self.states = [deepcopy(draft)]
        self.index = 0

    def push(self, draft):
        if draft != self.states[self.index]:
            self.states[self.index + 1:] = [deepcopy(draft)]
            self.index += 1

    def move(self, offset):
        self.index = max(0, min(len(self.states) - 1, self.index + offset))
        return deepcopy(self.states[self.index])


def view_path(client, identifier):
    service = hashlib.sha256(str(getattr(client, 'url', 'local')).encode()).hexdigest()[:16]
    root = Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppLocalDataLocation))
    return root / 'caelab' / 'data-views' / service / (identifier + '.json')


def saved_binding(document):
    from caelab.storage import canonical_hash
    return {**{key: document.get(key) for key in ('id', 'saved_revision', 'input_revision')},
            'input_sha256': canonical_hash(document['draft']), 'data_id': document['draft'].get('data_id')}


def write_view(path, payload):
    """Replace only after a complete flushed write; retain the old view on error."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=path.parent,
                                         prefix=path.name + '.', suffix='.tmp', delete=False) as stream:
            temporary = Path(stream.name)
            json.dump(payload, stream, ensure_ascii=False, allow_nan=False)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()
