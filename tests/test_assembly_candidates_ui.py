"""Focused native-panel command path with explicit owner/transport doubles."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from types import SimpleNamespace as NS
import pytest

pytest.importorskip('PySide6')
from PySide6 import QtCore, QtWidgets
from apps.desktop_pre.research_panel import make_panel


def test_coordinate_selection_units_cancel_and_explicit_registration(monkeypatch):
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    solver = NS(Name='Solver', Label='CalculiX', TypeId='Fem::SolverCcxTools')
    analysis = NS(Name='Analysis', Label='조립 해석', TypeId='Fem::FemAnalysis', Group=[solver],
                  isDerivedFrom=lambda kind: False)
    assembly = NS(Name='Assembly', Label='조립', TypeId='Assembly::AssemblyObject',
                  isDerivedFrom=lambda kind: kind == 'Assembly::AssemblyObject')
    owner = NS(doc=NS(Objects=[analysis, assembly]), _object=lambda name: analysis,
               fem=NS(contact=NS(_data=lambda: {'contacts': []})))
    target = {'object_id': 'Joint', 'native_type': 'App::FeaturePython',
              'family': 'joint_coordinate', 'field': 'travel'}
    row = {'target': target, 'key': 'joint_coordinate:Joint:travel', 'label': '직선 이동',
           'value': 2.5, 'unit': 'mm', 'writable': True, 'diagnostic': None,
           'joint_description': {'moving': '슬라이더', 'ground': '받침', 'occurrence_id': 'Moving',
                                'axis': {'axis_direction': [0., 0., 1.], 'axis_origin_mm': [5., -2., 3.2]},
                                'native_limits': {'min': -3., 'max': 3.}}}
    state = {'source_stamp': 'test-state', 'candidates': [row],
             'registered': [{'id': 'travel', 'target': target, 'value': .0025,
                             'unit': 'm', 'lower': -.003, 'upper': .003}]}
    calls = []
    def submit(operation, arguments, target, done):
        calls.append((operation, arguments))
        done(state if operation.endswith(('discover', 'register')) else {})
        return {'command_id': 'Ctest'}
    panel = make_panel(QtWidgets, QtCore, NS(owner=owner), submit, lambda *_: None)
    try:
        panel.resize(1100, 720)
        panel.show()
        panel.table.selectRow(0)
        app.processEvents()
        assert panel.table.item(0, 1).text() == '0.0025'
        assert panel.table.item(0, 2).text() == 'm'
        assert '슬라이더' in panel.coordinate_context.text()
        assert '양의 축 방향 (0, 0, 1)' in panel.coordinate_context.text()
        assert '축 원점 (5, -2, 3.2) mm' in panel.coordinate_context.text()
        assert '문서 전체 좌표' in panel.coordinate_context.text()
        before = list(calls)
        monkeypatch.setattr(QtWidgets.QInputDialog, 'getItem', lambda *_: ('조립', False))
        panel.connect_assembly()
        assert calls == before
        panel.highlight()
        assert calls[-1][0] == 'pre.select'
        assert calls[-1][1]['objects'] == [{'object_id': 'Joint'}, {'object_id': 'Moving'}]
        panel.table.item(0, 3).setText('-2.9e-3')
        panel.register()
        assert calls[-1][0] == 'pre.research.register'
        assert calls[-1][1]['lower'] == -.0029 and calls[-1][1]['unit'] == 'm'
    finally:
        panel.close()
        panel.deleteLater()
        app.processEvents()
