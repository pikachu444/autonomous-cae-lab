"""Native-shaped owner/Qt checks, not acceptance of a live FreeCAD Task dialog."""
from copy import deepcopy
from types import SimpleNamespace as NS
import json
import sys
import pytest
from test_pre_fem_edit import native, submit, repair_conditions, region, Quantity


@pytest.fixture
def native_solver_apis(monkeypatch):
    """Original FreeCAD API boundaries, without starting a solver or new GUI."""
    from apps.desktop_pre import metadata, native_solver_guard
    data = {'schema': metadata.SCHEMA}
    saved = NS(PropertiesList=['Definition'])
    doc = NS(Objects=[], getObject=lambda name: saved if name == metadata.NAME else None)
    solver = NS(Name='UserSolver', Document=doc, TypeId='Fem::FemSolverObjectPython',
                MaterialNonlinearity='nonlinear')
    analysis = NS(Name='UserAnalysis', Label='사용자 해석', Document=doc,
                  TypeId='Fem::FemAnalysis', Group=[solver])
    doc.Objects = [analysis, solver]
    calls, warnings, errors = [], [], []
    result = object()

    class ViewProvider:
        def setEdit(self, vobj, mode=0):
            calls.append(('edit', vobj, mode))
            return result

    class Writer:
        def __init__(self):
            self.analysis, self.solver_obj = analysis, solver

        def write_solver_input(self, *args, **kwargs):
            calls.append(('write', args, kwargs))
            return result

    class Task:
        def __init__(self):
            self.fea = NS(analysis=analysis, solver=solver)

        def runCalculix(self, *args, **kwargs):
            calls.append(('run', args, kwargs))
            return result

        def femConsoleMessage(self, text, level):
            errors.append((text, level))

    modules = {
        'femviewprovider.view_solver_ccxtools': NS(VPSolverCcxTools=ViewProvider),
        'femsolver.calculix.writer': NS(FemInputWriterCcx=Writer),
        'femtaskpanels.task_solver_ccxtools': NS(_TaskPanel=Task),
        'FreeCAD': NS(Console=NS(PrintError=errors.append)),
        'FreeCADGui': NS(getMainWindow=lambda: 'native-main-window'),
        'PySide': NS(QtGui=NS(QMessageBox=NS(warning=lambda *args: warnings.append(args)))),
    }
    for name, module in modules.items():
        monkeypatch.setitem(sys.modules, name, module)
    native_solver_guard.install()

    def save():
        saved.Definition = json.dumps(data, ensure_ascii=False)

    save()
    return NS(data=data, saved=saved, save=save, analysis=analysis, solver=solver,
              doc=doc, view=ViewProvider(), writer=Writer(), task=Task(),
              result=result, calls=calls, warnings=warnings, errors=errors,
              install=native_solver_guard.install)


@pytest.mark.parametrize('key', [
    'contacts', 'contact_programs', 'convergence_drafts', 'periodic_constraints',
    'pretension_sections', 'initial_fields', 'pretension_editors', 'shells',
    'beam_models', 'dynamic_programs', 'composite_shells', 'displacement_transfers',
])
def test_native_solver_entry_writer_and_existing_task_reject_omitted_saved_conditions(native_solver_apis, key):
    api = native_solver_apis
    # The task already exists before saved conditions are changed.
    api.data[key] = ([{'analysis_id': api.analysis.Name, 'raw': '1e'}]
        if key in ('contacts', 'contact_programs', 'convergence_drafts',
                   'periodic_constraints', 'pretension_sections')
        else {api.analysis.Name: {'raw': '1e'}})
    api.save()
    before = api.saved.Definition
    assert api.view.setEdit(NS(Object=api.solver)) is False
    assert api.warnings[-1][0] == 'native-main-window'
    assert '사용자 해석' in api.warnings[-1][2] and '계산 관리' in api.warnings[-1][2]
    with pytest.raises(ValueError, match='사용자 해석.*계산 관리'):
        api.writer.write_solver_input()
    assert api.task.runCalculix() is None
    assert api.errors[-1][1] == 'Error' and '계산 관리' in api.errors[-1][0]
    assert not api.calls
    assert api.saved.Definition == before
    assert api.analysis.Group == [api.solver] and api.solver.MaterialNonlinearity == 'nonlinear'


def test_native_solver_delegation_preserves_calls_returns_and_stale_plasticity(native_solver_apis):
    api = native_solver_apis
    api.data.update(contacts=[{'analysis_id': 'OtherAnalysis'}],
        initial_fields={'OtherAnalysis': {'raw': '1e'}},
        plasticity_drafts=[{'analysis_id': api.analysis.Name, 'draft_errors': ['old draft'],
                            'draft': {'yield': '1e'}, 'applied': None}])
    api.save()
    before = api.saved.Definition
    methods = (type(api.view).setEdit, type(api.writer).write_solver_input, type(api.task).runCalculix)
    api.install()
    assert methods == (type(api.view).setEdit, type(api.writer).write_solver_input, type(api.task).runCalculix)
    vobj = NS(Object=api.solver)
    assert api.view.setEdit(vobj, 7) is api.result
    assert api.writer.write_solver_input('native-arg', output='unchanged') is api.result
    assert api.task.runCalculix(False, native_flag=True) is api.result
    assert api.calls == [('edit', vobj, 7), ('write', ('native-arg',), {'output': 'unchanged'}),
                         ('run', (False,), {'native_flag': True})]
    assert not api.warnings and not api.errors and api.saved.Definition == before


def test_native_writer_checks_its_actual_analysis_instead_of_selected_analysis(native_solver_apis):
    api = native_solver_apis
    api.data['initial_fields'] = {api.analysis.Name: {'raw': '1e'}}
    api.save()
    api.writer.analysis = NS(Name='OtherAnalysis', Label='다른 해석', Document=api.doc)
    assert api.writer.write_solver_input() is api.result
    assert api.calls == [('write', (), {})]


def test_unmanaged_native_model_keeps_all_original_solver_entry_points(native_solver_apis):
    api = native_solver_apis
    api.doc.getObject = lambda name: None
    assert api.view.setEdit(NS(Object=api.solver)) is api.result
    assert api.writer.write_solver_input() is api.result
    assert api.task.runCalculix() is api.result
    assert [call[0] for call in api.calls] == ['edit', 'write', 'run']
    assert not api.errors and not api.warnings


def test_native_targets_require_explicit_adoption_and_preserve_native_fields(native):
    repair_conditions(native)
    old_regions = deepcopy(native.metadata['regions'])
    native.force.References = [(native.shape, ['Face1', 'Face2'])]
    native.force.Direction = (native.shape, ['Edge1'])
    native.force.Force, native.force.Reversed, native.force.EnableAmplitude = Quantity('23 N'), True, True
    assert native.editor._condition_errors(native.force, native.editor._metadata())
    result = submit(native, 'condition_repair', {'use_native_references': True}, native.force)
    assert result['region_id'] is None and result['direction_region_id'] is None
    assert native.metadata['regions'] == old_regions
    assert not native.editor._condition_errors(native.force, native.editor._metadata())
    assert native.force.Force.Value == 23 and native.force.Reversed and native.force.EnableAmplitude
    assert native.force.References == [(native.shape, ['Face1', 'Face2'])]


def test_current_exact_named_regions_are_retained_and_value_only_edit_needs_no_adoption(native):
    repair_conditions(native)
    before = deepcopy(native.metadata)
    native.force.Force = Quantity('24 N'); native.force.Reversed = True
    assert not native.editor._condition_errors(native.force, native.editor._metadata())
    assert native.metadata == before
    result = submit(native, 'condition_repair', {'use_native_references': True}, native.force)
    assert result['region_id'] == before['conditions'][1]['region_id']


def test_generic_native_face_edit_does_not_require_legacy_condition_repair(native):
    repair_conditions(native)
    native.force.References = [(native.shape, ['Face1'])]
    before = deepcopy(native.metadata)
    assert native.editor._condition_errors(native.force, before)
    assert native.editor.validate_for_run(native.analysis) == []
    assert native.metadata == before
    assert native.force.References == [(native.shape, ['Face1'])]


def test_generic_native_admission_keeps_native_validator_refusal(native,monkeypatch):
    repair_conditions(native)
    native.force.References=[]
    before=deepcopy(native.metadata)
    def reject(analysis,solver):
        assert analysis is native.analysis and solver is native.solver
        assert not native.force.References
        raise ValueError('Force has empty references.')
    monkeypatch.setattr('apps.desktop_pre.native_calculix.validate_analysis',reject)
    errors=native.editor.validate_for_run(native.analysis)
    assert any(row['message']=='Force has empty references.' and row['blocks_evaluation'] for row in errors)
    assert native.metadata==before


@pytest.mark.parametrize('changed',['geometry','mesh'])
def test_generic_native_admission_keeps_actual_mesh_source_checks(native,changed):
    repair_conditions(native)
    if changed=='geometry':native.shape.Shape.brep='changed native source geometry'
    else:native.mesh.FemMesh.Nodes[4].z=2.
    before=deepcopy(native.metadata)
    errors=native.editor.validate_for_run(native.analysis)
    expected='Source geometry changed' if changed=='geometry' else 'Native mesh changed'
    assert any(expected in row['message'] and row['blocks_evaluation'] for row in errors)
    assert native.metadata==before


@pytest.mark.parametrize('problem', ['active_task', 'geometry', 'empty', 'edge_reference', 'foreign', 'direction', 'boolean'])
def test_native_confirmation_does_not_bypass_invalid_target_or_active_task(native, problem):
    repair_conditions(native)
    before = deepcopy(native.metadata)
    args = {'use_native_references': True}
    if problem == 'active_task': native.edit = native.force.Name
    elif problem == 'geometry': native.shape.Shape.brep = 'changed CAD'
    elif problem == 'empty': native.force.References = []
    elif problem == 'edge_reference': native.force.References = [(native.shape, ['Edge1'])]
    elif problem == 'foreign':
        foreign = NS(Name=native.shape.Name, Document=NS(), Shape=native.shape.Shape)
        native.force.References = [(foreign, ['Face1'])]
    elif problem == 'direction': native.force.Direction = (native.shape, ['Face1'])
    elif problem == 'boolean': args['use_native_references'] = 1
    with pytest.raises(ValueError): submit(native, 'condition_repair', args, native.force)
    assert native.metadata == before












@pytest.mark.parametrize('target', ['mesh', 'material', 'fixed', 'force'])
def test_existing_freecad_task_entry_changes_no_native_values_or_metadata(native, target):
    obj = getattr(native, target)
    before = deepcopy(native.metadata)
    group = list(native.analysis.Group)
    result = submit(native, 'task_edit', obj=obj)
    assert native.edit == obj.Name and result['state'] == 'NATIVE_TASK_OPEN'
    assert native.metadata == before and native.analysis.Group == group
    native.edit = None  # Native Task cancel; no replacement editor or auto-apply.
    assert native.metadata == before and native.force.Force.Value == 10


def test_typed_force_creation_retains_native_task_and_exact_source_selection(native):
    selected = region(native)
    result = submit(native, 'condition_set', {'kind': 'Force', 'region_id': selected['id'],
        'force': 37, 'unit': 'N'}, native.analysis)
    created = native._object(result['object_id'])
    assert created in native.analysis.Group and created.Force.Value == 37
    assert created.References == [(native.shape, ['Face1'])]
    before = deepcopy(native.metadata)
    submit(native, 'task_edit', obj=created)
    assert native.edit == created.Name and native.metadata == before


def test_explicit_target_repair_preserves_native_force_after_cad_change(native):
    repair_conditions(native)
    native.force.Direction = (native.shape, ['Edge1'])
    submit(native, 'condition_repair', {'use_native_references': True}, native.force)
    native.shape.Shape.brep = 'edited CAD'; native.shape.Shape.Edges[0].brep = 'edited edge'
    edge = region(native, 'Edge1'); face = region(native, 'Face2')
    submit(native, 'condition_repair', {'region_id': face['id'], 'direction_region_id': edge['id']}, native.force)
    assert native.force.Direction == (native.shape, ['Edge1']) and native.force.Force.Value == 10
    assert not native.editor._condition_errors(native.force, native.editor._metadata())
