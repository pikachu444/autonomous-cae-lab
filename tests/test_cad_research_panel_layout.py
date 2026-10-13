"""Native worksheet changes with explicit owner/command doubles; no calculation."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from copy import deepcopy
from types import SimpleNamespace as NS
import pytest
pytest.importorskip('PySide6')
from PySide6 import QtCore, QtWidgets
from apps.desktop_pre.research_panel import make_panel


@pytest.fixture
def worksheet():
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    solver = NS(Name='Solver', Label='CalculiX', TypeId='Fem::SolverCcxTools')
    analyses = [NS(Name=name, Label=name, TypeId='Fem::FemAnalysis', Group=[solver]) for name in ('A', 'B')]
    pairs = [{'analysis_id': 'A', 'object_id': 'ContactA', 'draft': {'label': '부품과 받침'}}]
    objects = {obj.Name: obj for obj in analyses}
    objects['ContactA'] = NS(Suppressed=False)
    owner = NS(doc=NS(Objects=analyses), _object=objects.__getitem__,
               fem=NS(contact=NS(_data=lambda: {'contacts': pairs})))
    states = {}
    for analysis in ('A', 'B'):
        candidates = [{'key': analysis + field, 'target': {'object_id': analysis, 'field': field},
                       'label': '모델 / ' + field, 'value': value, 'unit': 'mm', 'writable': True,
                       'diagnostic': None} for field, value in (('Length', 10.), ('Width', 6.))]
        states[analysis] = {'source_stamp': analysis + 'source', 'candidates': candidates,
                            'registered': [{'target': candidates[0]['target'], 'value': 10., 'unit': 'mm',
                                            'id': 'length', 'lower': 8., 'upper': 12.}]}
    calls, waiting, plans = [], [], []
    def submit(operation, arguments, target, done):
        calls.append((operation, deepcopy(arguments)))
        if operation == 'pre.research.discover':
            done(deepcopy(states[arguments['analysis_id']]))
        else:
            waiting.append(done)
        return {'command_id': 'C' + str(len(calls))}
    global_style = app.styleSheet()
    panel = make_panel(QtWidgets, QtCore, NS(owner=owner), submit, lambda *args: plans.append(args))
    panel.resize(1100, 780); panel.show(); app.processEvents()
    yield app, panel, states, calls, waiting, plans, global_style
    panel.close(); panel.deleteLater(); app.processEvents()


def test_range_drafts_survive_other_registration_and_failed_command(worksheet):
    app, panel, states, calls, waiting, plans, global_style = worksheet
    panel.table.item(0, 3).setText('7.5')
    panel.table.item(1, 3).setText('4.5')
    panel.table.item(1, 4).setText('7.5')
    panel.table.item(1, 5).setText('width')
    panel.table.selectRow(0); panel.register()
    assert calls[-1][1]['lower'] == 7.5
    # A queued native completion can arrive after selection changes.
    panel.table.selectRow(1)
    states['A']['registered'][0]['lower'] = 7.5
    waiting.pop(0)(deepcopy(states['A']))
    assert panel.table.currentRow() == 1
    assert panel.table.item(0, 6).text() == '등록됨'
    assert panel.table.item(1, 3).text() == '4.5'
    assert panel.table.item(1, 6).text() == '변경 미등록'
    panel.table.selectRow(0)
    panel.table.item(0, 5).setText('new_length')
    panel.remove()
    assert calls[-1] == ('pre.research.remove', {'analysis_id': 'A', 'id': 'length'})
    waiting.pop(0)({'status': 'FAILED', 'error': {'message': '해제 실패'}})
    assert panel.table.item(0, 5).text() == 'new_length'
    panel.table.item(0, 5).setText('length')
    before = len(calls)
    panel.plan()
    assert len(calls) == before and not plans
    assert panel.table.currentRow() == 1 and '먼저 등록' in panel.message.text()
    panel.register()
    waiting.pop(0)({'status': 'FAILED', 'error': {'message': '등록 실패'}})
    assert panel.table.item(1, 3).text() == '4.5'
    assert panel.table.item(1, 6).text() == '변경 미등록'
    assert app.styleSheet() == global_style
    assert panel.table.columnWidth(0) > panel.table.columnWidth(6)
    assert panel.responses.columnWidth(2) > panel.responses.columnWidth(7)


def test_analysis_switch_keeps_ranges_and_uses_its_own_responses(worksheet):
    app, panel, states, calls, waiting, plans, global_style = worksheet
    original_response = panel.definitions()
    assert original_response[0]['pair_id'] == 'ContactA'
    panel.table.item(0, 4).setText('13')
    panel.analysis.setCurrentIndex(1); app.processEvents()
    assert panel.definitions()[0]['kind'] == 'displacement'
    assert not panel.response_issue.isVisible()
    panel.analysis.setCurrentIndex(0); app.processEvents()
    assert panel.table.item(0, 4).text() == '13'
    assert panel.definitions() == original_response
    state = deepcopy(states['A'])
    state['candidates'][0]['writable'] = False
    state['candidates'][0]['diagnostic'] = 'Expression driven'
    panel.populate(state)
    assert panel.range_warning.isVisible() and '허용 상한 13' in panel.range_warning.toolTip()
    assert state['candidates'][0]['key'] not in panel.pending_ranges()
    panel.populate(deepcopy(states['A']))
    assert panel.table.item(0, 4).text() == '13'
    state = deepcopy(states['A'])
    state['candidates'] = state['candidates'][1:]
    panel.populate(state)
    assert panel.range_warning.isVisible() and not panel.pending_ranges()
    panel.populate(deepcopy(states['A']))
    assert panel.table.item(0, 4).text() == '13'
    panel.response_defs[0]['pair_id'] = 'UnavailablePair'
    panel.render_responses(); app.processEvents()
    assert panel.response_issue.isVisible() and '현재 해석에 없는' in panel.response_issue.text()
    assert not panel.prepare.isEnabled()
