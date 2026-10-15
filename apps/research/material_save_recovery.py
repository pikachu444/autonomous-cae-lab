"""GUI context for reopening the original related-save receipt; no requests."""
from copy import deepcopy


def checked_context(context, material_id):
    """Check the view envelope; Core still validates every receipt and command."""
    if context is None:
        return None
    if (not isinstance(context, dict) or set(context) != {'material_id', 'selected_plan', 'plans'}
            or context['material_id'] != material_id or not isinstance(context['plans'], dict)
            or context['selected_plan'] is not None and not isinstance(context['selected_plan'], str)):
        raise ValueError('보관한 저장 결과의 재료와 현재 문서가 다릅니다.')
    for identifier, item in context['plans'].items():
        if (not isinstance(identifier, str) or not identifier or not isinstance(item, dict)
                or set(item) != {'receipt_id', 'pending_preview', 'unconfirmed'}
                or not isinstance(item['receipt_id'], str) or not item['receipt_id']
                or type(item['unconfirmed']) is not bool):
            raise ValueError('보관한 저장 요청을 읽지 못했습니다. 원문은 유지됩니다.')
        preview = item['pending_preview']
        if preview is not None:
            if not isinstance(preview, dict) or preview.get('receipt_id') != item['receipt_id']:
                raise ValueError('원래 저장 요청과 저장 결과가 다릅니다.')
            targets = preview.get('targets')
            if not isinstance(targets, list) or len(targets) != 2:
                raise ValueError('보관한 저장 요청의 문서를 확인하세요.')
            identities = [target.get('identity', {}) for target in targets if isinstance(target, dict)]
            if (len(identities) != 2 or any(not isinstance(identity, dict)
                    or not isinstance(identity.get('document_id'), str)
                    or not isinstance(identity.get('kind'), str) for identity in identities)
                    or {(identity.get('document_id'), identity.get('kind')) for identity in identities}
                       != {(material_id, 'material'), (identifier, 'numerical')}):
                raise ValueError('보관한 저장 요청은 다른 재료나 계획의 요청입니다.')
    return deepcopy(context)


def saved_metadata(current, saved, *, previous_saved_revision):
    """Accept a save receipt only for the same acknowledged Material input."""
    if not isinstance(current, dict) or not isinstance(saved, dict):
        return None
    keys=('id','kind','session_id','generation','input_revision','draft')
    if (current.get('kind') != 'material' or type(saved.get('dirty')) is not bool or not isinstance(saved.get('saved_revision'), str)
            or not saved['saved_revision'] or any(current.get(key) != saved.get(key) for key in keys)):
        return None
    if current.get('saved_revision') not in (previous_saved_revision, saved['saved_revision']):
        return None
    from caelab.storage import canonical_hash
    if canonical_hash(current['draft']) != canonical_hash(saved['draft']):
        return None
    refreshed=deepcopy(current)
    refreshed['saved_revision']=saved['saved_revision']
    refreshed['dirty']=saved['dirty']
    return refreshed


def snapshot_context(window):
    panel = getattr(window, '_plan_panel', None)
    if panel is not None and panel._related_save_material_id == window.document['id']:
        return panel.related_save_snapshot()
    return context_for(window, window.document['id'])


def context_for(window, material_id):
    contexts = getattr(window, '_related_save_recovery_contexts', {})
    context = contexts.get(material_id)
    legacy = getattr(window, '_related_save_recovery_context', None)
    if context is None and isinstance(legacy, dict) and legacy.get('material_id') == material_id:
        context = legacy
    return checked_context(context, material_id)


def remember_context(window, context):
    if context is not None:
        contexts = getattr(window, '_related_save_recovery_contexts', None)
        if contexts is None:
            contexts = window._related_save_recovery_contexts = {}
        contexts[context['material_id']] = deepcopy(context)


def restore_context(window, context):
    """Defer view restoration until the user opens the existing Plan panel."""
    context = checked_context(context, window.document['id'])
    if context is None:
        return
    remember_context(window, context)
    window._related_save_recovery_context = context
    panel = getattr(window, '_plan_panel', None)
    if panel is not None:
        panel.restore_related_save_context(context)
