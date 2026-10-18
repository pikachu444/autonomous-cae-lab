"""Frozen response semantics and Qt page geometry; no provider/solver calls."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from copy import deepcopy

import pytest
pytest.importorskip('PySide6')
from PySide6.QtGui import QFont, QTextCursor
from PySide6.QtWidgets import QApplication
from apps.research.report_pages import blocks, compose, markdown
from apps.research.report_window import section
from caelab.report_document import default_draft


def tensor_content():
    values = [[float(i) for i in range(81)] for _ in range(3)]
    response = dict(kind='series', unit='MPa', component='ijkl', location='material_point',
        axes=[dict(name='time', unit='s', values=[0., 1., 2.])], value=values)
    return dict(kind='result', result=dict(execution_status='SUCCEEDED', qualification='UNKNOWN', responses={'tangent': response}))


def test_multicomponent_tensor_keeps_exact_table_and_metadata_without_scalar_curve():
    content = tensor_content()
    original = deepcopy(content)
    rows = list(blocks(content))
    assert not any(kind == 'curve' for kind, _ in rows)
    assert any(kind == 'paragraph' and '성분' in value and '선택' in value for kind, value in rows)
    table = next(value for kind, value in rows if kind == 'table')
    assert [row[2] for row in table[1]] == content['result']['responses']['tangent']['value']
    assert content == original
    assert any('ijkl' in value and '재료점' in value for kind, value in rows if kind == 'paragraph')


def test_scalar_component_retains_curve_with_unknown_row_validity():
    content = tensor_content()
    response = content['result']['responses']['tangent']
    response.update(component='xxxx', value=[1800., 1800., 1800.])
    rows = list(blocks(content))
    curves = [value for kind, value in rows if kind == 'curve']
    assert len(curves) == 1
    assert curves[0]['y'] == [1800., 1800., 1800.]
    assert curves[0]['mask'] == [None, None, None]


def test_curves_after_tables_stay_inside_printable_page_and_keep_source():
    app = QApplication.instance() or QApplication([])
    content = tensor_content()
    content['result']['responses'] = {name: dict(kind='series', unit='MPa', component=name,
        axes=[dict(name='time', unit='s', values=[0., 1., 2.])], value=[0., 1., 2.]) for name in ('xx', 'yy', 'zz')}
    original = deepcopy(content)
    draft = default_draft()
    binding = dict(id='Aretained', sha256='a'*64, reference=dict(kind='result'))
    draft['sections'] = [section('응력과 원값', asset=binding)]
    assets = {'Aretained': dict(content=content, source_status='AVAILABLE')}
    document = compose(draft, assets, QFont('Segoe UI', 9))
    document.documentLayout().documentSize()
    image_count = 0
    block = document.begin()
    while block.isValid():
        iterator = block.begin()
        while not iterator.atEnd():
            fragment = iterator.fragment()
            if fragment.isValid() and fragment.charFormat().isImageFormat():
                image_count += 1
                cursor = QTextCursor(document); cursor.setPosition(fragment.position())
                assert cursor.currentTable() is None
                image = fragment.charFormat().toImageFormat()
                rect = document.documentLayout().blockBoundingRect(block)
                assert rect.left() + image.width() <= document.pageSize().width() - document.documentMargin() + .1
            iterator += 1
        block = block.next()
    assert image_count == 3
    assert content == original
def test_study_observation_status_uses_same_caption_without_rewriting_source():
    from copy import deepcopy
    from apps.research.report_pages import blocks
    content = {'kind': 'document', 'document': {'kind': 'study', 'draft': {'question': '다음 시험',
        'next_observations': [{'question': '다른 하중에서 구별할 수 있는가?', 'status': 'PLANNED', 'note': '원 메모'}]}}}
    before = deepcopy(content)
    paragraphs = '\n'.join(value for kind, value in blocks(content) if kind == 'paragraph')
    assert '확인 예정' in paragraphs and 'PLANNED' not in paragraphs
    assert content == before


@pytest.mark.parametrize('locator,caption',[
    ({'section':'절차','line_start':1,'line_end':6,'segment_id':0},'절차 / 줄 1–6'),
    ({'page':3},'쪽 3'),
])
def test_knowledge_locator_is_printed_with_the_exact_retained_excerpt(locator,caption):
    content={'kind':'knowledge','source':{'title':'원 문헌','segments':[{
        'locator':locator,'text':'보존한 정확 본문'}]}}
    before=deepcopy(content)
    paragraphs=[value for kind,value in blocks(content) if kind=='paragraph']
    assert paragraphs==['원 문헌',caption,'보존한 정확 본문']
    assert content==before


def test_failed_candidate_capture_preserves_exact_input_unit_for_printing():
    from caelab.report_document import compact_payload
    payload={'kind':'result','reference':{'selection':{'metadata_only':True}},'result':{
        'kind':'optimization','variables':[{'id':'Tref','unit':'K'}],
        'candidates':[{'values':{'Tref':293.15},'execution_status':'FAILED','objective':None,
            'input_bindings':[{'id':'Tref','unit':'K','value':293.15}]}]}}
    before=deepcopy(payload)
    content=compact_payload(payload)
    tables=[value for kind,value in blocks(content) if kind=='table']
    assert (['입력','값','단위'],[['Tref',293.15,'K']]) in tables
    assert content['result']['candidates'][0]['input_bindings']==payload['result']['candidates'][0]['input_bindings']
    assert payload==before


def test_legacy_candidate_unit_is_explicitly_unprovided():
    content={'kind':'result','result':{'candidates':[{'values':{'unknown':2.}}]}}
    tables=[value for kind,value in blocks(content) if kind=='table']
    assert (['입력','값','단위'],[['unknown',2.,'미제공']]) in tables
