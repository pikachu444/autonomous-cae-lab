"""Public embed contract for the Numerical-owned PlanVariablesWidget.

No Qt widget is implemented or reparented by this Pro lane. Numerical provides
its existing typed delegates/descriptors via this protocol; Material owns the
selection badge and the widget's Qt parent. The shared document owner stays the
sole draft/Undo/CAS authority. This adapter only transports explicitly supplied
cell buffers and previews; it does not hold another editable Plan draft.
"""
from __future__ import annotations
from copy import deepcopy
from typing import Protocol, Mapping, Any, Callable

from .related_save import input_identity


class PlanVariablesWidgetProtocol(Protocol):
    def bind_owner(self, adapter: 'PlanOwnerAdapter', document: Mapping[str, Any]) -> None: ...
    def has_unapplied_buffer(self) -> bool: ...
    def buffer_snapshot(self) -> Mapping[str, Any]: ...
    def show_patch_result(self, outcome: Mapping[str, Any]) -> None: ...
    def detach_owner(self) -> None: ...
    # Numerical supplies patchPreviewRequested(preview), dirtyChanged(bool),
    # ownerActivated(document_id) signals with its real PySide Signal objects.


class PlanOwnerAdapter:
    """Transport adapter, with caller-owned immutable snapshots and local buffers."""
    def __init__(self, client, document_id: str):
        from .storage import check_id
        self.client, self.document_id = client, check_id(document_id)

    def read(self):
        document = self.client.document_read(self.document_id)
        # Existing endpoint may return the direct document or its envelope.
        document = document.get('document', document)
        if document['kind'] != 'numerical':
            raise ValueError('The embedded variable widget requires the selected Numerical Plan')
        return document

    def preview(self, base_document, buffer):
        if base_document['id'] != self.document_id or base_document['kind'] != 'numerical':
            raise ValueError('Preview belongs to a different Plan owner')
        return self.client.data_material('owner_patches.preview', {'requests': [
            {'identity': input_identity(base_document), 'buffer': deepcopy(buffer)}]})

    def execute(self, preview):
        if any(item['identity']['document_id'] != self.document_id for item in preview['items']):
            raise ValueError('Use the explicit multi-owner API for a cross-owner paste')
        return self.client.data_material('owner_patches.execute', {'preview': deepcopy(preview)})

    def undo(self, base_document, *, command_id):
        if base_document['id'] != self.document_id:
            raise ValueError('Undo belongs to a different owner')
        return self.client.document_command(self.document_id, 'document.undo', {},
            session_id=base_document['session_id'], expected_generation=base_document['generation'], command_id=command_id)

    def redo(self, base_document, *, command_id):
        if base_document['id'] != self.document_id:
            raise ValueError('Redo belongs to a different owner')
        return self.client.document_command(self.document_id, 'document.redo', {},
            session_id=base_document['session_id'], expected_generation=base_document['generation'], command_id=command_id)


def embed_plan_variables(widget_factory: Callable, *, parent, adapter: PlanOwnerAdapter, document):
    """Numerical's public factory creates a NEW widget using shared descriptors.

    Never pass numerical_window.variables or its QTableWidget. The factory must
    accept parent=... and implement the protocol; its window is not the owner.
    Material disposes the widget with its normal Qt parent lifetime.
    """
    widget = widget_factory(parent=parent)
    widget.bind_owner(adapter, document)
    return widget
