"""Select a recorded field response; native interpretation remains in adapters."""

from .response_history import _read_native


def _adapter_resources(lab, result):
    backend = result['provenance']['adapter']
    adapter = lab.analysis_adapters.get(backend)
    if not callable(getattr(adapter, 'field_response_resources', None)):
        adapter = getattr(lab, 'response_field_adapters', {}).get(backend)
    hook = getattr(adapter, 'field_response_resources', None)
    if not callable(hook):
        return None, None
    policy = hook(result)
    if not isinstance(policy, dict) or not policy or len(policy) > 8:
        raise ValueError('Adapter field resources must have a bounded explicit contract')
    resources = {}
    for role, resource in policy.items():
        if not isinstance(role, str) or not isinstance(resource, dict) or set(resource) != {'path', 'maximum_bytes'}:
            raise ValueError('Adapter field resource declaration differs')
        resources[role] = _read_native(lab, result, resource['path'], maximum_bytes=resource['maximum_bytes'])
    return adapter, resources


def display_catalog(lab, identifier):
    from .response_comparison import _source
    from .contracts import CapabilityUnavailable
    result, proposal, hashes = _source(lab, identifier)
    adapter, resources = _adapter_resources(lab, result)
    hook = getattr(adapter, 'display_response_fields', None)
    if not callable(hook):
        raise CapabilityUnavailable('This result family has no common display-field reader')
    display = hook(result, proposal, resources)
    _, _, again = _source(lab, identifier)
    if hashes != again:
        raise ValueError('Recorded field source changed during inspection')
    return {'schema_version': '1.0', 'integrity': 'VERIFIED', 'experiment_id': identifier,
            'study_id': result['study']['id'], 'result_sha256': hashes['result_sha256'],
            'display': display, 'engineering': 'UNKNOWN', 'decision': 'NOT_RELEASED'}


def selected_response(lab, result, proposal, selection):
    from .adapters.structural_response_fields import select_field_response

    adapter, resources = _adapter_resources(lab, result)
    if adapter is not None:
        hook = getattr(adapter, 'select_response_fields', None)
        if not callable(hook):
            raise ValueError('Adapter has no exact recorded field selector')
        return hook(result, proposal, resources, selection)

    # The enclosing comparison verifies result/proposal/thread and all retained
    # artifacts before and after this read. Never accept a caller's physical value.
    raw, artifact = _read_native(lab, result, selection["artifact"])
    if artifact["sha256"] != selection["sha256"]:
        raise ValueError("Selected field hash does not match the recorded artifact")
    return select_field_response(result, proposal, raw, artifact, selection)
