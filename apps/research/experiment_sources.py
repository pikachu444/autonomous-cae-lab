"""Pinned local literature picker shared by Study and Report; no inference."""
from copy import deepcopy
from PySide6.QtWidgets import QDialog, QInputDialog
from caelab.storage import canonical_hash


def choose_knowledge(client, parent, selected, *, reference=None):
    from .expert_sources import SourceDialog
    initial = [{key: reference[key] for key in ('document_id', 'revision')}] if reference else []
    dialog = SourceDialog(client, {'selected_sources': initial}, parent=parent)
    if dialog.exec() != QDialog.DialogCode.Accepted or not dialog.references:
        return
    pins = dialog.references
    labels = [dialog.records[(p['document_id'], p['revision'])].get('title', '문헌') for p in pins]
    index = 0
    if len(pins) > 1:
        indexed = [str(i+1)+'. '+label for i,label in enumerate(labels)]
        chosen, ok = QInputDialog.getItem(parent, '문헌 선택', '추가할 원문', indexed, editable=False)
        if not ok:return
        index = indexed.index(chosen)
    pin = pins[index]
    payload = dialog.records[(pin['document_id'], pin['revision'])]
    # Empty locator means all archived segments at this exact revision, never latest.
    reference = {'kind': 'knowledge', 'document_id': pin['document_id'], 'revision': pin['revision'],
        'locator': {}, 'source_sha256': payload['sha256'], 'content_sha256': canonical_hash(payload)}
    selected(reference, labels[index])
