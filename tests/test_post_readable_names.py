"""Readable new registration names; proxy/state doubles are not GUI acceptance."""
from copy import deepcopy
import json

import pytest

from apps.desktop_post import naming
from test_desktop_post_external import native
from test_post_analysis import analysis, sources
from test_post_workspace_ownership import owner_workspace


def test_duplicates_use_small_numbers_and_preserve_user_label():
    old = object()
    sources = {('Result | frame.vtu | b5181e99', 1): old,
               ('frame.vtu', 2): object(), ('frame.vtu (2)', 3): object()}
    assert naming.unique_name('frame.vtu', sources) == 'frame.vtu (3)'
    assert naming.unique_name('사용자 지정 이름', sources) == '사용자 지정 이름'
    assert naming.unique_name('  custom label  ', sources) == '  custom label  '
    assert sources[('Result | frame.vtu | b5181e99', 1)] is old


@pytest.mark.parametrize('kind,draft,expected', [
    ('filter', {'filter': 'Slice'}, '단면'),
    ('filter', {'filter': 'WarpByVector'}, '변형 표시'),
    ('comparison', {}, '결과 비교'),
    ('measurement', {'measurement': 'time'}, '시간 이력'),
])
def test_new_default_titles_describe_the_operation(owner_workspace, kind, draft, expected):
    env = owner_workspace
    created = env.work._edit(kind, draft)
    assert created['title'] == expected
    custom = env.work._edit(kind, draft, title='Filter')
    assert custom['title'] == 'Filter'
    changed = env.work._edit(kind, draft, object_ref=created['id'], title='사용자 명칭')
    assert changed['id'] == created['id'] and changed['title'] == '사용자 명칭'


def test_same_basename_and_custom_names_survive_save_reopen(native, tmp_path):
    fake, _, external = native
    first_path, second_path = tmp_path / 'a/frame.vtu', tmp_path / 'b/frame.vtu'
    for path in (first_path, second_path):
        path.parent.mkdir()
        path.write_text('controlled mesh', encoding='utf-8')
    project = external.open_result(first_path, tmp_path / 'project', input_id='Ioriginal',
                                   source_pins=external.pins(external.source_files(first_path)))
    document = json.loads(project.read_text(encoding='utf-8'))
    second, record = external.admit_result(second_path, input_id='Isecond',
                                           source_pins=external.pins(external.source_files(second_path)))
    assert document['sources']['result']['reader_name'] == 'frame.vtu'
    assert record['reader_name'] == 'frame.vtu (2)'
    record['source_ref'] = 'Ssecond'
    document['sources']['Ssecond'] = record
    custom, custom_record = external.admit_result(second_path, display_name='시험 응력')
    assert custom_record['reader_name'] == '시험 응력'
    document['sources']['Scustom'] = custom_record
    legacy_name = 'Result | frame.vtu | b5181e99'
    fake.XMLUnstructuredGridReader(registrationName=legacy_name, FileName=[str(first_path)])
    legacy_record = deepcopy(document['sources']['result'])
    legacy_record['reader_name'] = legacy_name
    document['sources']['Slegacy'] = legacy_record
    fake.SetActiveSource(second)
    saved = external.save_project(project, document)
    saved_document = json.loads(saved.read_text(encoding='utf-8'))
    assert saved_document['active_selection']['source_name'] == 'frame.vtu (2)'
    fake.sources.clear()
    external.restore_workspace(saved, saved_document)
    external.restore_selection(saved_document)
    assert fake.GetActiveSource() is fake.FindSource('frame.vtu (2)')
    assert fake.FindSource('frame.vtu') is not fake.FindSource('frame.vtu (2)')
    assert fake.FindSource(legacy_name) is not None
    assert saved_document['sources']['Slegacy']['reader_name'] == legacy_name
    assert saved_document['sources']['Ssecond']['source_ref'] == 'Ssecond'
    assert saved_document['sources']['Ssecond']['input_id'] == 'Isecond'


def test_repeated_analysis_registration_keeps_distinct_exact_names(analysis):
    module, native = analysis
    _, source, _ = sources(native)
    settings = {'origin': [0.5, 0, 0], 'normal': [1, 0, 0]}
    first = module.create_filter(source, 'Slice', settings, namespace='단면')
    second = module.create_filter(source, 'Slice', settings, namespace='단면')
    assert first['source'].label == '단면'
    assert second['source'].label == '단면 (2)'
    registered = {name: proxy for (name, _), proxy in native.GetSources().items()}
    assert registered['단면'] is first['source']
    assert registered['단면 (2)'] is second['source']


def test_source_label_is_forwarded_without_changing_document_reference(owner_workspace, monkeypatch):
    env = owner_workspace
    received = []
    def admit(*args, **kwargs):
        received.append(kwargs['display_name'])
        output = env.proxy(kwargs['display_name'])
        return output, {**deepcopy(env.document['sources']['Sraw']), 'reader_name': output.name}
    monkeypatch.setattr(env.module.external, 'admit_result', admit, raising=False)
    added = env.work.add_source(input_id='Ioriginal', receipt={'id': 'Ioriginal',
        'path': str(env.folder / 'raw.vtu'), 'source_pins': []}, label_text='사용자 결과')
    reference = added['source_ref']
    assert received == ['사용자 결과']
    assert reference.startswith('S') and reference != '사용자 결과'
    assert env.document['sources'][reference]['source_ref'] == reference
    assert env.document['sources'][reference]['reader_name'] == '사용자 결과'


def test_validation_passes_task_name_and_records_exact_proxy_name(owner_workspace, monkeypatch):
    env = owner_workspace
    passed = []
    def create(source, kind, settings, namespace):
        passed.append(namespace)
        output = env.proxy(namespace)
        return {'source': output, 'proxies': [output], 'summary': {}}
    monkeypatch.setattr(env.module.analysis, 'create_filter', create, raising=False)
    for name in ('GetActiveSource', 'GetActiveView'):
        monkeypatch.setattr(env.module.p, name, lambda: None, raising=False)
    for name in ('SetActiveSource', 'SetActiveView'):
        monkeypatch.setattr(env.module.p, name, lambda value: None, raising=False)
    created = env.work.edit_filter(draft={'source_ref': 'Sraw', 'filter': 'Slice'})
    preview = env.work.validate(object_ref=created['id'])
    assert passed == ['단면']
    assert preview['source_name'] == '단면' and preview['proxy_names'] == ['단면']
    assert env.work.object(created['id'])['id'] == created['id']


def test_saved_analysis_references_keep_new_and_legacy_names(owner_workspace):
    env = owner_workspace
    for reference, name in [('Anew', '단면 (2)'), ('Alegacy', 'CAE filter | Aold | 12345678')]:
        obj = env.add_object(reference)
        record = obj['history'][0]
        output = env.proxy(name)
        record.update(source_name=name, proxy_names=[name], graph=deepcopy(output.graph))
        env.work.bundles[record['id']] = {'source': output, 'proxies': [output], 'summary': {}}
    saved = env.work.prepare_save(deepcopy(env.document), env.folder / 'save')
    reopened = env.module.Workspace(env.owner, saved)
    for reference, name in [('Anew', '단면 (2)'), ('Alegacy', 'CAE filter | Aold | 12345678')]:
        obj = reopened.object(reference)
        assert obj['id'] == reference
        assert obj['history'][0]['source_name'] == name
        assert reopened.resolve(reference) is env.module.p.FindSource(name)
