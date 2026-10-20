"""Saved typed bolt definitions survive removal of the duplicate Qt editor."""
from copy import deepcopy
from types import SimpleNamespace as NS
import pytest
from apps.desktop_pre import pretension_native as pt
from apps.desktop_pre.pretension_controls import route_native_solver
from caelab.storage import canonical_hash
from pretension_fixture import model


@pytest.fixture
def scene(monkeypatch):
    m = model(); draft = deepcopy(m['pretension_sections'][0]['draft']); draft['mesh_id'] = 'BoltMesh'
    data = {}; binding = {'source': 'exact-source', 'mesh': 'exact-ordered-mesh'}
    solver = NS(Name='Solver', TypeId='Fem::FemSolverObjectPython')
    analysis = NS(Name='Analysis', Label='사용자 볼트 체결', TypeId='Fem::FemAnalysis', Group=[solver])
    owner = NS(doc=NS(Objects=[analysis]), assert_thread=lambda: None, _object=lambda name: analysis,
        read_metadata=lambda: deepcopy(data))
    def write(value): data.clear(); data.update(deepcopy(value))
    owner.write_metadata = write
    fem = NS(owner=owner, _object=lambda target: analysis, _metadata=lambda: deepcopy(data),
        _assert_idle=lambda: None, _transaction=lambda label, change: change())
    monkeypatch.setattr(pt, '_mesh', lambda *args: (None, deepcopy(binding), m, 'Bolt'))
    pt.dispatch(fem, 'pre.fem.pretension_set', {'id': 'Pbolt', 'request_id': 'first-set',
        'expected_revision': None, 'draft': draft, 'mesh_binding': binding}, {'object_id': 'Analysis'})
    return NS(owner=owner, fem=fem, analysis=analysis, solver=solver, data=data, binding=binding)


def test_editor_cas_failure_and_valid_unapplied_value_never_changes_active_condition(scene):
    s = scene; applied = s.data['pretension_sections'][0]
    snapshot = {'id': 'Pbolt', 'draft': deepcopy(applied['draft']), 'mesh_binding': deepcopy(s.binding),
                'expected_revision': applied['revision']}
    snapshot['draft']['control']['value'] = '620'
    pt.save_editor(s.fem, s.analysis, {'editor': snapshot, 'expected_editor_sha256': None})
    assert s.data['pretension_sections'][0]['draft']['control']['value'] == 600
    changed = deepcopy(snapshot); changed['draft']['control']['value'] = '1e'
    before = deepcopy(s.data)
    with pytest.raises(ValueError, match='다른'):
        pt.save_editor(s.fem, s.analysis, {'editor': changed, 'expected_editor_sha256': None})
    assert s.data == before
    pt.save_editor(s.fem, s.analysis, {'editor': changed, 'expected_editor_sha256': canonical_hash(snapshot)})
    assert s.data['pretension_sections'] == before['pretension_sections']
    unchanged = deepcopy(s.data)
    remove = {'id': 'Pbolt', 'expected_revision': applied['revision'], 'expected_editor_sha256': None,
              'request_id': 'delete-01'}
    with pytest.raises(ValueError, match='다른'):
        pt.dispatch(s.fem, 'pre.fem.pretension_remove', remove, {'object_id': 'Analysis'})
    assert s.data == unchanged
    pt.save_editor(s.fem, s.analysis, {'editor': None, 'expected_editor_sha256': canonical_hash(changed)})
    pt.dispatch(s.fem, 'pre.fem.pretension_remove', remove, {'object_id': 'Analysis'})
    assert not s.data['pretension_sections']


def test_native_solver_does_not_omit_saved_bolt_conditions_or_open_a_replacement_editor(scene):
    s = scene; before = deepcopy(s.data)
    connection = NS(show_panel=lambda *a, **kw: pytest.fail('No duplicate bolt editor'))
    with pytest.raises(ValueError, match='사용자 볼트 체결.*계산 관리'):
        route_native_solver(connection, s.owner, s.solver)
    assert s.data == before
    assert route_native_solver(connection, s.owner, NS(Name='OtherSolver')) is False


def test_unapplied_saved_bolt_draft_is_retained_at_native_solver_entry(scene):
    s = scene; applied = s.data['pretension_sections'][0]
    snapshot = {'id': 'Pbolt', 'draft': deepcopy(applied['draft']), 'mesh_binding': deepcopy(s.binding),
                'expected_revision': applied['revision']}
    snapshot['draft']['control']['value'] = '1e'
    pt.save_editor(s.fem, s.analysis, {'editor': snapshot, 'expected_editor_sha256': None})
    before = deepcopy(s.data)
    with pytest.raises(ValueError, match='계산 관리'):
        route_native_solver(NS(), s.owner, s.solver)
    assert s.data == before and s.data['pretension_editors']['Analysis']['draft']['control']['value'] == '1e'
