"""Dependency scopes and Windows optional extras, without installs or inference."""
from pathlib import Path
from types import SimpleNamespace
import tomllib

import pytest

from caelab.assist import readiness


@pytest.fixture(autouse=True)
def reset_cache():
    readiness._package_readiness.cache_clear()
    yield
    readiness._package_readiness.cache_clear()


def all_modules(monkeypatch, missing=()):
    imported = []
    def forbidden_constructor(*args, **kwargs):
        raise AssertionError('Readiness must not construct a model, document store or tool')
    def load(module):
        imported.append(module)
        if any(module == item or module.startswith(item + '.') for item in missing):
            raise ModuleNotFoundError('CONTROLLED missing optional dependency: ' + module)
        return SimpleNamespace(**{symbol: forbidden_constructor for symbol in (
            'Agent', 'ChatMessage', 'Tool', 'OpenAIChatGenerator', 'Secret', 'Document',
            'InMemoryDocumentStore', 'InMemoryBM25Retriever', 'PdfReader')})
    monkeypatch.setattr(readiness, 'import_module', load)
    monkeypatch.setattr(readiness, 'version', lambda distribution: 'CONTROLLED_VERSION')
    return imported


def test_ready_probes_only_import_symbols_and_returns_detached_cached_result(monkeypatch):
    imported = all_modules(monkeypatch)
    first = readiness.package_readiness()
    assert first['status'] == 'READY'
    assert first['features']['expert_agent']['available']
    assert first['inference_performed'] is False
    assert first['model_configuration_checked'] is False
    assert first['network_access_performed'] is False
    assert not first['missing_dependencies']
    count = len(imported)
    first['features']['expert_agent']['available'] = False
    assert readiness.package_readiness()['features']['expert_agent']['available']
    assert len(imported) == count
    readiness.package_readiness(refresh=True)
    assert len(imported) == 2 * count


def test_missing_agent_does_not_hide_document_listing_or_pdf_read(monkeypatch):
    all_modules(monkeypatch, missing=('haystack',))
    result = readiness.package_readiness()
    assert result['status'] == 'MISSING_DEPENDENCIES'
    assert not result['features']['expert_agent']['available']
    assert result['features']['document_listing']['available']
    assert result['features']['pdf_read']['available']
    assert result['missing_dependencies'] == [{'distribution': 'haystack-ai', 'extra': 'assist-core',
        'install_command': 'python -m pip install -e ".[assist-core]"'}]
    with pytest.raises(ImportError, match='assist-core'):
        readiness.require_features('expert_agent')
    readiness.require_features('document_listing', 'pdf_read')


def test_optional_pdf_mcp_packages_do_not_block_agent_or_bm25(monkeypatch):
    all_modules(monkeypatch, missing=('pypdf', 'mcp'))
    result = readiness.package_readiness()
    assert result['status'] == 'PARTIAL'
    assert result['features']['expert_agent']['available']
    assert result['features']['knowledge_index']['available']
    assert not result['features']['pdf_read']['available']
    assert not result['features']['mcp']['available']
    readiness.require_features('expert_agent', 'openai_compatible_generator', 'knowledge_index')
    with pytest.raises(ValueError, match='Unknown dependency'):
        readiness.require_features('invented_feature')


def test_optional_package_initialization_failure_remains_a_visible_dependency_state(monkeypatch):
    def broken(_module):
        raise ValueError('CONTROLLED incompatible package initialization')
    monkeypatch.setattr(readiness, 'import_module', broken)
    result = readiness.package_readiness()
    assert result['features']['document_listing']['available']
    assert result['features']['expert_agent']['status'] == 'MISSING_DEPENDENCIES'
    assert result['features']['expert_agent']['requires'][0]['error_type'] == 'ValueError'
    assert result['inference_performed'] is False


def test_existing_assist_extra_and_windows_flags_cover_core_and_explicit_pdf():
    root = Path(__file__).resolve().parents[1]
    project = tomllib.loads((root / 'pyproject.toml').read_text(encoding='utf-8-sig'))
    extras = project['project']['optional-dependencies']
    assert extras['assist'] == extras['assist-core'] + extras['assist-pdf']
    install = (root / 'scripts' / 'install-windows.ps1').read_text(encoding='utf-8-sig')
    launch = (root / 'scripts' / 'start-windows.ps1').read_text(encoding='utf-8-sig')
    for flag in ('Expert', 'Documents', 'MCP', 'Sensitivity'):
        assert '[switch]$' + flag in install and '[switch]$' + flag in launch
        assert '-' + flag + ':$' + flag in launch
    assert "if ($ResearchUI -or $Expert) { $extras += 'assist-core' }" in install
    assert "if ($Documents) { $extras += 'assist-pdf' }" in install
    assert 'require_features("expert_agent", "openai_compatible_generator", "knowledge_index")' in install
    assert 'installed_extras=$install.installed_extras' in launch
    assert '$_ -notin $launch.installed_extras' in launch
