"""Small API facade over the existing Workbench owners and execution manager.

No new owner, backend, registry, HTTP server, GUI window or job manager is made.
The two root transport hooks install this facade in the existing local server.
"""
from __future__ import annotations
from copy import deepcopy

from .related_save import RelatedSaveCoordinator, input_identity
from .related_save_edits import preview_edits, execute_edits
from .related_save_recovery import RawRecoveryDrafts
from .data_processing import make_sheet_group, read_sheet_group, compile_selection, channel_from_import
from .material_control import capabilities, uniaxial_settings


class DataMaterialService:
    def __init__(self, workbench):
        self.workbench = workbench
        self.saves = RelatedSaveCoordinator(workbench.root, workbench._document_owner)
        self.recovery = RawRecoveryDrafts(workbench.root, workbench._document_owner)
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

    def sample_policy_preview(self, document_id, processing_revision, response, *, role='fit', weight=1., raw_selection=None):
        from .data_processing_selection import propose_sample_policy
        result = self.processing_result(document_id, processing_revision, selection=[response])
        source = result['diagnostics']['processing_record']['source']
        return propose_sample_policy(channel_from_import(result, source, response),
            role=role, weight=weight, raw_selection=raw_selection)

    def sample_policy_adopt(self, document_id, experiment_id, proposal, *, session_id,
                            expected_generation, command_id, entries=None):
        from .data_processing_selection import accept_sample_policy, sample_domain
        from .storage import load_json, canonical_hash, check_id
        owner = self.owner(document_id, 'numerical')
        policy = accept_sample_policy(proposal, adoption={'plan_document_id': document_id,
            'command_id': command_id, 'session_id': session_id, 'generation': expected_generation}, entries=entries)
        with owner._lock(document_id):
            current = owner.read(document_id)
            receipt = owner._folder(document_id) / 'commands' / (check_id(command_id) + '.json')
            if receipt.exists():
                prior = load_json(receipt)
                frozen = prior.get('response', {}).get('document', {}).get('draft')
                if frozen is not None:
                    item = next((e for e in frozen.get('experiments', []) if e['id'] == experiment_id), None)
                    if item is None or item.get('selection') != {'sample_policy': policy}:
                        raise ValueError('Policy command ID already belongs to another request')
                    # The existing command verifies request hash/session before
                    # returning its durable ack; no newer owner input is applied.
                    response = owner.command(document_id, owner.update_operation, {'draft': frozen},
                        session_id=session_id, expected_generation=expected_generation, command_id=command_id)
                    return {**response, 'sample_policy': policy, 'saved': False}
            if current['session_id'] != session_id or current['generation'] != expected_generation:
                raise ValueError('Plan owner changed; keep the policy preview and review again')
            draft = deepcopy(current['draft'])
            item = next((e for e in draft.get('experiments', []) if e['id'] == experiment_id), None)
            if item is None:
                raise ValueError('Select an existing Plan experiment')
            source = item['source']
            if 'processing_revision' not in source:
                raise ValueError('Select a frozen Data processing revision for sample policy adoption')
            result = self.processing_result(source['document_id'], source['processing_revision'], selection=[source['response']])
            origin = result['diagnostics']['processing_record']['source']
            if any(origin[k] != source[k] for k in ('document_id', 'job_id', 'input_revision', 'input_sha256')):
                raise ValueError('Plan source differs from the reviewed processing import')
            channel = channel_from_import(result, origin, source['response'])
            if sample_domain(channel) != policy['domain']:
                raise ValueError('Policy proposal belongs to another frozen response/grid')
            item['selection'] = {'sample_policy': policy}
            response = owner.command(document_id, owner.update_operation, {'draft': draft},
                session_id=session_id, expected_generation=expected_generation, command_id=command_id)
            return {**response, 'sample_policy': policy, 'saved': False}

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
        if isinstance(operation, str) and operation.startswith('acquisition.'):
            from .acquisition_service import AcquisitionService
            return AcquisitionService(self.workbench).dispatch(operation, arguments)
        methods = {
            'recovery.identity': self.recovery.owner_identity,
            'recovery.prepare': self.recovery.prepare,
            'recovery.execute': self.recovery.execute,
            'recovery.read': self.recovery.read,
            'recovery.inspect': self.recovery.inspect,
            'recovery.source_preview': self.recovery.source_preview,
            'recovery.portable_payload': self.recovery.portable_payload,
            'recovery.recover': self.recovery.recover,
            'recovery.discard': self.recovery.discard,
            'recovery.close_permitted': self.recovery.close_permitted,
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
            'data.sample_policy.preview': self.sample_policy_preview,
            'data.sample_policy.adopt': self.sample_policy_adopt,
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
    # Compact recovery reviews carry at most 16 existing 512 KiB raw
    # buffers, not whole historical documents/DAGs. Keep a bounded envelope;
    # native/ordinary command limits remain unchanged.
    body = handler._json_body(maximum=12 * 1024 * 1024)
    if not isinstance(body, dict) or set(body) != {'operation', 'arguments'}:
        raise ServiceError(400, 'Data/Material action requires operation and arguments')
    if not str(body['operation']).startswith('recovery.'):
        import json
        if len(json.dumps(body, ensure_ascii=False).encode('utf-8')) > 2 * 1024 * 1024:
            raise ServiceError(413, 'Data/Material non-recovery action exceeds 2 MiB')
    try:
        result = handler.server.data_material.dispatch(body['operation'], body['arguments'])
    except (ValueError, TypeError, KeyError, FileNotFoundError) as error:
        raise ServiceError(400, str(error)) from error
    return handler._json(200, result)
