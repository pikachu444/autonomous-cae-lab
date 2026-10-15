"""Public analytic axis declarations + synthetic PNG receipts, not physics evidence."""
from copy import deepcopy
import base64
import json
import shutil

import pytest

from caelab import report_image as images
from caelab.report_image_axis import native_clock, caption as axis_caption, saved_axis_context
from caelab.storage import canonical_hash
from apps.research.report_image_pages import image_markdown
from report_image_fixture import fixture, refresh_snapshot
from test_report_image_core import owner, command


def declared_fixture(path, declaration, *, has_time=True, value=.25):
    f = fixture(path)
    metadata = {'arrays': deepcopy(f['record']['summary']['declarations']['arrays']), **deepcopy(declaration)}
    source = f['project']['sources']['Sinput']
    source.update(native_metadata=deepcopy(metadata), native_metadata_sha256=canonical_hash(metadata))
    f['record']['bindings']['Sinput']['metadata'] = source['native_metadata_sha256']
    f['record']['summary']['declarations'] = deepcopy(metadata)
    refresh_snapshot(f)
    f['snapshot']['scene']['clock'] = native_clock(has_time, value, .25, .25, metadata)
    return f


@pytest.mark.parametrize('unit,semantics,label', [
    ('s', 'physical_time', '물리시간 0.25 [s]'),
    ('ms', '시험 시작 기준', '물리시간 0.25 [ms]'),
    ('1', 'STATIC_LOAD_PARAMETER', '정적 하중 매개변수 0.25 [1]'),
    ('1', 'load_parameter', '정적 하중 매개변수 0.25 [1]'),
    ('1', 'DIMENSIONLESS_MODEL_TIME', '무차원 모델시간 0.25 [1]'),
    ('s', 'UNKNOWN', '축 의미 미제공 0.25 [s]'),
    ('s', ' UNKNOWN ', '축 의미 미제공 0.25 [s]'),
    (None, None, '축 의미 미제공 0.25 [단위 미제공]'),
])
def test_axis_meaning_in_caption_and_markdown_not_data_time_guess(tmp_path, unit, semantics, label):
    declaration = {'time': {'unit': unit, 'semantics': semantics, 'values': [.25]}}
    f = declared_fixture(tmp_path/'post', declaration)
    _, content = images.completed_content(f['command'])
    text = images.caption(content['snapshot'])
    assert label in text and label in image_markdown(content, {})
    assert '실제 시각' not in text
    if unit == '1' or semantics is None or 'UNKNOWN' in str(semantics):
        assert '물리시간 0.25' not in text


def test_data_time_without_output_declaration_remains_unknown_even_if_original_time_known(tmp_path):
    f = fixture(tmp_path/'post')
    f['record']['summary'].pop('declarations')
    refresh_snapshot(f)
    f['snapshot']['scene']['clock'] = native_clock(True, .25, .25, .25, None)
    _, content = images.completed_content(f['command'])
    text = images.caption(content['snapshot'])
    assert '축 의미 미제공 0.25' in text
    assert '원입력' in text and '물리시간 [s]' in text  # Declaration, not an output value.
    assert '물리시간 0.25' not in text


@pytest.mark.parametrize('kind', ['physical', 'static_parameter', 'model', 'unknown', 'static_metadata'])
def test_same_axis_snapshot_survives_saved_reopen_source_removal_and_study_body(tmp_path, kind):
    units = {'physical': ('s', 'physical_time'), 'static_parameter': ('1', 'STATIC_LOAD_PARAMETER'),
             'model': ('1', 'DIMENSIONLESS_MODEL_TIME'), 'unknown': (None, None)}
    if kind == 'static_metadata':
        declaration = {'time': None, 'static': {'step': 3, 'increment': 7, 'load_parameter': .25}}
        f = declared_fixture(tmp_path/'post', declaration, has_time=False)
    else:
        unit, semantic = units[kind]
        f = declared_fixture(tmp_path/'post', {'time': {'unit': unit, 'semantics': semantic, 'values': [.25]}})
    store = owner(tmp_path/'store'); doc = store.open()
    binding = store.capture_image(doc['id'], f['command']); asset = store.asset(doc['id'], binding)
    before_caption = images.caption(asset['content']['snapshot'])
    draft = images.apply_binding(doc['draft'], binding, asset['content'])
    draft['sections'][0]['text'] = 'Study 판단: 가설 미확인. 다음 연구는 측정 위치 검토.'
    doc = command(store, doc, 'report.update', {'draft': draft})
    doc = command(store, doc, 'document.save')
    shutil.rmtree(f['source'].parent)
    fresh = owner(tmp_path/'store'); opened = fresh.open(document_id=doc['id'])
    saved = fresh.content(doc['id'], [binding])['assets'][0]
    assert opened['draft'] == draft and saved['source_status'] == 'UNAVAILABLE'
    assert images.caption(saved['content']['snapshot']) == before_caption
    assert before_caption.replace('"', '&quot;') in image_markdown(saved['content'], {})
    assert '계산 성공' not in before_caption


def test_static_original_metadata_retained_without_inventing_output_clock(tmp_path):
    f = declared_fixture(tmp_path/'post', {'time': None, 'static': {'step': 2, 'increment': 9, 'load_parameter': .25}}, has_time=False)
    f['record']['summary'].pop('declarations'); refresh_snapshot(f)
    f['snapshot']['scene']['clock'] = native_clock(False, None, 0., 0., None)
    _, content = images.completed_content(f['command'])
    text = images.caption(content['snapshot'])
    assert '원입력' in text and '정적 단계 2 / 증분 9 / 하중 매개변수 0.25 [1]' in text
    assert '물리시간 아님' in text and '0초 아님' in text


@pytest.mark.parametrize('semantic,unit', [('STATIC_LOAD_PARAMETER', 's'), ('DIMENSIONLESS_MODEL_TIME', 'ms'),
    ('physical_time', '1'), ('physical_time', None), ('named_clock', 'MPa'), ('UNKNOWN', 'mm')])
def test_invalid_combination_never_replaces_previous_binding(tmp_path, semantic, unit):
    f = fixture(tmp_path/'post'); store = owner(tmp_path/'store'); doc = store.open()
    binding = store.capture_image(doc['id'], f['command']); previous = store.asset(doc['id'], binding)
    draft = images.apply_binding(doc['draft'], binding, previous['content']); draft['sections'][0]['text'] = '이전 판단'
    doc = command(store, doc, 'report.update', {'draft': draft}); before = deepcopy(doc)
    bad = deepcopy(f['command']); snapshot = bad['outcome']['result']['result']['report_snapshot']
    snapshot['scene']['clock'].update(unit=unit, semantics=semantic)
    with pytest.raises(ValueError): store.capture_image(doc['id'], bad)
    assert store.read(doc['id']) == before and store.asset(doc['id'], binding) == previous


def comparison_from_frozen(f, frozen, *, second_value=None):
    """Exact older observation is used while a newer one is the upstream UI pick."""
    older = deepcopy(f['record']); older['id'] = 'Robservation1'
    older['recipe'] = {'source_ref': 'Sinput', 'measurement': 'point', 'time': frozen['value']}
    older['summary']['declarations'] = {'arrays': [], 'time': None, 'frozen_clock': deepcopy(frozen)}
    newer = deepcopy(older); newer['id'] = 'Robservation2'
    newer['summary']['declarations']['frozen_clock']['value'] = second_value or 99.
    f['project']['analysis']['objects']['Mobservation'] = {
        'id': 'Mobservation', 'kind': 'measurement', 'position': 1, 'history': [older, newer]}
    side = {'source_ref': 'Mobservation', 'frozen_clock': deepcopy(frozen), 'sampling': {'mode': 'exact', 'time': None}}
    f['object']['kind'] = 'comparison'
    f['record']['recipe'] = {'version': 2, 'a': deepcopy(side), 'b': deepcopy(side), 'clock': deepcopy(frozen)}
    f['record']['bindings'] = {'Mobservation': {'revision': canonical_hash(images._identity(older))}}
    f['record']['dependencies'] = {'Mobservation': older['id']}
    f['record']['summary']['declarations'] = {'arrays': [], 'time': None,
        'frozen_clock': deepcopy(frozen), 'sample_clock': deepcopy(frozen)}
    refresh_snapshot(f)
    f['snapshot']['scene']['clock'] = native_clock(False, None, 0., 0., f['record']['summary']['declarations'])
    return older, newer


@pytest.mark.parametrize('unit,semantic,label', [('s', 'physical_time', '물리시간'),
    ('1', 'STATIC_LOAD_PARAMETER', '정적 하중 매개변수'), ('1', 'DIMENSIONLESS_MODEL_TIME', '무차원 모델시간'),
    (None, None, '축 의미 미제공')])
def test_comparison_frozen_axis_uses_exact_prior_observation_not_current(tmp_path, unit, semantic, label):
    f = fixture(tmp_path/'post'); frozen = {'unit': unit, 'semantics': semantic, 'value': .25}
    comparison_from_frozen(f, frozen)
    _, content = images.completed_content(f['command'])
    text = images.caption(content['snapshot'])
    assert '고정 관측: ' + label + ' 0.25' in text and '99.0' not in text
    assert [row['revision'] for row in content['snapshot']['scene']['axis_context']['records']] == ['Robservation1', 'Rresult']
    assert content['snapshot']['scene']['clock']['value'] is None


@pytest.mark.parametrize('fault', ['side', 'sample', 'output', 'raw_clock', 'filter_input', 'static_clock', 'source_declaration'])
def test_conflicting_pinned_declarations_are_rejected(tmp_path, fault):
    f = fixture(tmp_path/'post')
    if fault in ('side', 'sample', 'output', 'raw_clock'):
        frozen = {'unit': '1', 'semantics': 'STATIC_LOAD_PARAMETER', 'value': .25}
        comparison_from_frozen(f, frozen)
        if fault == 'side': f['record']['recipe']['a']['frozen_clock']['value'] = .5
        elif fault == 'sample': f['record']['summary']['declarations']['sample_clock']['value'] = .5
        elif fault == 'output': f['record']['summary']['declarations']['frozen_clock']['value'] = .5
        else:
            f['snapshot']['scene']['clock'].update(status='DATA_TIME', value=.25, view_time=.25,
                unit='s', semantics='physical_time')
            with pytest.raises(ValueError): images.completed_content(f['command'])
            return
    elif fault == 'filter_input':
        f['record']['summary']['declarations']['time'] = {'unit': '1', 'semantics': 'DIMENSIONLESS_MODEL_TIME'}
    elif fault == 'static_clock':
        f['record']['summary']['declarations']['static'] = {'step': 1, 'increment': 1, 'load_parameter': .25}
    else:
        meta = f['project']['sources']['Sinput']['native_metadata']; meta['time']['unit'] = '1'
        f['project']['sources']['Sinput']['native_metadata_sha256'] = canonical_hash(meta)
        f['record']['bindings']['Sinput']['metadata'] = canonical_hash(meta)
    with pytest.raises(ValueError): refresh_snapshot(f)


def test_legacy_image_is_readable_relabelled_and_not_newly_adopted(tmp_path):
    f = fixture(tmp_path/'post')
    snapshot = f['snapshot']; snapshot['format'] = images.LEGACY_FORMAT
    snapshot['scene'].pop('axis_context'); snapshot['scene'].pop('block_coloring')
    snapshot['scene']['clock'].update(unit='1', semantics='STATIC_LOAD_PARAMETER')
    content = {'kind': 'post_image', 'snapshot': snapshot,
               'png_base64': base64.b64encode(f['png'].read_bytes()).decode()}
    assert images.validate_content(content) == f['png'].read_bytes()
    text = images.caption(snapshot)
    assert '정적 하중 매개변수 0.25' in text and '실제 시각 0.25' not in text
    assert '블록별 색상 검증 미기록' in text
    with pytest.raises(ValueError, match='이전 캡처'): images.completed_content(f['command'])


def test_known_axis_without_data_value_is_not_claimed_unknown(tmp_path):
    f = fixture(tmp_path/'post'); snapshot = deepcopy(f['snapshot'])
    snapshot['scene']['clock'].update(status='NO_DATA_TIME', value=None)
    text = axis_caption(snapshot)
    assert '데이터 축값 없음' in text and '출력의 축 선언: 물리시간 [s]' in text
    assert '물리시간 0' not in text
