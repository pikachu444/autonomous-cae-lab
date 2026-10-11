"""Optional assistance dependency checks without constructing or invoking models.

Import availability is separate from credentials, model configuration, public
network access and actual inference. Saved document listing remains package-free.
"""
from copy import deepcopy
from functools import lru_cache
from importlib import import_module
from importlib.metadata import PackageNotFoundError, version


PROBES = {
    'expert_agent': (
        ('haystack.components.agents', 'Agent', 'haystack-ai', 'assist-core'),
        ('haystack.dataclasses', 'ChatMessage', 'haystack-ai', 'assist-core'),
        ('haystack.tools', 'Tool', 'haystack-ai', 'assist-core')),
    'openai_compatible_generator': (
        ('haystack.components.generators.chat', 'OpenAIChatGenerator', 'haystack-ai', 'assist-core'),
        ('haystack.utils', 'Secret', 'haystack-ai', 'assist-core')),
    'knowledge_index': (
        ('haystack', 'Document', 'haystack-ai', 'assist-core'),
        ('haystack.document_stores.in_memory', 'InMemoryDocumentStore', 'haystack-ai', 'assist-core'),
        ('haystack.components.retrievers.in_memory', 'InMemoryBM25Retriever', 'haystack-ai', 'assist-core')),
    'pdf_read': (('pypdf', 'PdfReader', 'pypdf', 'assist-pdf'),),
    'mcp': (('mcp', None, 'mcp', 'mcp'),),
}


def _probe(module, symbol, distribution, extra):
    try:
        imported = import_module(module)
        if symbol is not None:
            getattr(imported, symbol)
    except Exception as error:
        # Optional dependency initialization can also fail with ValueError or
        # TypeError (for example, an incompatible installed binary/package).
        # Report its actual failure without blocking saved discussion editing.
        return {'module': module, 'symbol': symbol, 'distribution': distribution,
                'extra': extra, 'available': False, 'error_type': type(error).__name__,
                'message': str(error)}
    try:
        installed_version = version(distribution)
    except PackageNotFoundError:
        installed_version = None
    return {'module': module, 'symbol': symbol, 'distribution': distribution,
            'extra': extra, 'available': True, 'version': installed_version}


@lru_cache(maxsize=1)
def _package_readiness():
    features = {'document_listing': {'available': True, 'status': 'READY',
        'requires': [], 'scope': 'saved definitions and document metadata; no index or inference'}}
    missing = {}
    for feature, probes in PROBES.items():
        checks = [_probe(*probe) for probe in probes]
        available = all(check['available'] for check in checks)
        features[feature] = {'available': available, 'status': 'READY' if available else 'MISSING_DEPENDENCIES',
                             'requires': checks}
        for check in checks:
            if not check['available']:
                missing[check['distribution']] = {'distribution': check['distribution'], 'extra': check['extra'],
                    'install_command': 'python -m pip install -e ".[' + check['extra'] + ']"'}
    core_ready = features['expert_agent']['available'] and features['openai_compatible_generator']['available']
    status = ('READY' if all(feature['available'] for feature in features.values()) else
              'PARTIAL' if core_ready else 'MISSING_DEPENDENCIES')
    return {'status': status, 'scope': 'dependency_imports_only', 'features': features,
            'missing_dependencies': list(missing.values()), 'inference_performed': False,
            'model_configuration_checked': False, 'network_access_performed': False}


def package_readiness(*, refresh=False):
    """Return detached import checks; refresh after an explicit package install."""
    if refresh:
        _package_readiness.cache_clear()
    return deepcopy(_package_readiness())


def require_features(*features):
    """A narrow installer check, independent of configured providers or models."""
    readiness = package_readiness(refresh=True)
    unknown = set(features) - set(readiness['features'])
    if unknown:
        raise ValueError('Unknown dependency feature: ' + ', '.join(sorted(unknown)))
    unavailable = [feature for feature in features if not readiness['features'][feature]['available']]
    if unavailable:
        extras = sorted({check['extra'] for feature in unavailable for check in readiness['features'][feature]['requires'] if not check['available']})
        raise ImportError('Missing optional assistance dependencies for ' + ', '.join(unavailable) +
                          '; install project extras: ' + ', '.join(extras))
    return readiness
