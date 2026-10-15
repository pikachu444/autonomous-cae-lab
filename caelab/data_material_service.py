"""Small API facade over the existing Workbench owners and execution manager.

No new owner, backend, registry, HTTP server, GUI window or job manager is made.
The two root transport hooks install this facade in the existing local server.
"""
from __future__ import annotations
from copy import deepcopy

from .related_save import RelatedSaveCoordinator, input_identity
from .related_save_edits import preview_edits, execute_edits
from .data_processing import make_sheet_group, read_sheet_group, compile_selection, channel_from_import
from .material_control import capabilities, uniaxial_settings


class DataMaterialService:
    def __init__(self, workbench):
        self.workbench = workbench
        self.saves = RelatedSaveCoordinator(workbench.root, workbench._document_owner)
        # This is the same Numerical owner, not a separately cached Plan editor.
        workbench.numerical_documents.resolve_processing = workbench.data_documents.processing_result

    def owner(self, identifier, kind):
        owner = self.workbench._document_owner(identifier)
        if owner.kind != kind:
            raise ValueError('Select the existing ' + kind + ' document owner')
        return owner

    def processing_preview(self, document_id):
        return self.owner(document_id, 'data').processing_preview(document_id)

    def processing_apply(self, document_id, preview_sha256, *, session_id, expected_generation, command_id):
        return self.owner(document_id, 'data').command(document_id, 'data.processing.apply',
            {'preview_sha256': preview_sha256}, session_id=session_id,
            expected_generation=expected_generation, command_id=command_id)

    def processing_result(self, document_id, processing_revision, *, selection=None):
        return self.owner(document_id, 'data').processing_result(document_id, processing_revision, selection=selection)

    def processing_compile(self, document_id, processing_revision, response, *, selection=None, role='fit', weight=1.):
        result = self.processing_result(document_id, processing_revision, selection=[response])
        source = result['diagnostics']['processing_record']['source']
        channel = channel_from_import(result, source, response)
        return compile_selection(channel, selection, default_role=role, base_weight=weight)

    def sheet_group_preview(self, references):
        if not isinstance(references, list) or not 1 <= len(references) <= 128:
            raise ValueError('Select 1 to 128 exact saved Data references')
        documents = []
        for ref in references:
            if not isinstance(ref, dict) or set(ref) != {'document_id', 'kind', 'saved_revision', 'input_revision', 'input_sha256'}:
                raise ValueError('Sheet selection requires complete saved reference identities')
            owner = self.owner(ref['document_id'], 'data')
            saved = owner._verify_revision(ref['document_id'], ref['saved_revision'])
            from .related_save import saved_reference
            if saved_reference(owner, saved) != ref:
                raise ValueError('Sheet reference changed')
            documents.append(saved)
        group = make_sheet_group(documents)
        return {'group': group, 'sheets': read_sheet_group(group, self.workbench._document_owner),
                'published': False, 'storage': 'existing Data draft.sheet_group'}

    def dispatch(self, operation, arguments):
        """JSON-friendly public API. Every mutation uses explicit owner CAS IDs."""
        methods = {
            'related_save.preview': self.saves.preview,
            'related_save.execute': self.saves.execute,
            'related_save.retry': self.saves.retry,
            'related_save.receipt': self.saves.read_receipt,
            'related_save.publish': self.saves.publish_link,
            'related_save.reconcile': self.saves.reconcile_publication,
            'data.processing.preview': self.processing_preview,
            'data.processing.apply': self.processing_apply,
            'data.processing.result': self.processing_result,
            'data.processing.compile': self.processing_compile,
            'data.sheet_group.preview': self.sheet_group_preview,
            'data.sheet_group.read': lambda group: read_sheet_group(group, self.workbench._document_owner),
            'material.control.capabilities': capabilities,
            'material.control.uniaxial_preview': uniaxial_settings,
            'owner_patches.preview': lambda requests: preview_edits(self.workbench._document_owner, requests),
            'owner_patches.execute': lambda preview: execute_edits(self.workbench._document_owner, preview),
        }
        if not isinstance(operation, str) or operation not in methods or not isinstance(arguments, dict):
            raise ValueError('Unsupported Data/Material API action')
        # Bind before executing: an unknown/missing argument cannot partially run.
        import inspect
        inspect.signature(methods[operation]).bind(**arguments)
        return methods[operation](**deepcopy(arguments))


def handle_http(handler, method, query):
    """Root routes only the exact /api/workbench/data-material path here."""
    from apps.lab.service import ServiceError
    if method != 'POST' or query:
        raise ServiceError(400, 'Data/Material actions use authenticated POST without a query')
    # Two owner buffers may each use the existing 96 KiB draft allowance.
    # Only this action endpoint uses the explicit 2 MiB ceiling; ordinary
    # command endpoints retain their original 128 KiB admission limit.
    body = handler._json_body(maximum=2 * 1024 * 1024)
    if not isinstance(body, dict) or set(body) != {'operation', 'arguments'}:
        raise ServiceError(400, 'Data/Material action requires operation and arguments')
    try:
        result = handler.server.data_material.dispatch(body['operation'], body['arguments'])
    except (ValueError, TypeError, KeyError, FileNotFoundError) as error:
        raise ServiceError(400, str(error)) from error
    return handler._json(200, result)
