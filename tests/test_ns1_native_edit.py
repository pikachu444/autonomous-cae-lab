"""Literal native-object/owner doubles, not FreeCAD or constitutive validation."""
from copy import deepcopy
import json
import sys
from types import SimpleNamespace as NS
import pytest

from test_pre_fem_edit import native, Object
from apps.desktop_pre import nonlinear_material as nm
from apps.desktop_pre.fem_edit import FEMEditor
from apps.desktop_pre.native_calculix import validate_analysis as native_validate_analysis
from caelab.calculix_material import J2, LINEAR, default_plasticity


def draft(count=3):
    curve = default_plasticity()
    curve['yield_points'] = [[str(250+i), str(i*.0001)] for i in range(count)]
    return dict(law=J2, definitions_confirmed=True, plasticity=curve)


@pytest.fixture
def nonlinear_factory(native, monkeypatch):
    def factory(doc, base):
        return Object(doc, 'PlasticMaterial', 'Fem::FeaturePython', Proxy=NS(Type=nm.KIND),
                      LinearBaseMaterial=base, MaterialModelNonlinearity='isotropic hardening',
                      YieldPoints=[], Suppressed=False)
    monkeypatch.setattr(sys.modules['ObjectsFem'], 'makeMaterialMechanicalNonlinear', factory, raising=False)
    return native


def test_native_apply_keeps_original_curve_and_base_values(nonlinear_factory):
    n = nonlinear_factory
    value = draft(); value['plasticity'].update(stress_unit='GPa', strain_unit='%')
    value['plasticity']['yield_points'] = [['.25000000000000001','0'], ['.27','1.234567891234567e-3']]
    source, elastic = deepcopy(value), deepcopy(n.material.Material)
    actual = nm.apply(n.editor, n.material, n.analysis.Name, value)
    obj, = nm.native_objects(n.analysis)
    assert obj.LinearBaseMaterial is n.material and n.solver.MaterialNonlinearity == 'nonlinear'
    assert n.material.Material == elastic and actual['draft'] == source and actual['applied']
    assert n.metadata['keep_other_owner_field']
    effective = nm.effective(n.editor, n.analysis, n.material)
    assert effective['source_curve'] == source['plasticity']
    assert effective['plasticity']['yield_points'][1][1] == pytest.approx(1.234567891234567e-5)
    assert all(len(token.strip()) <= 20 for row in obj.YieldPoints for token in row.split(','))
    assert not actual['executed'] and value == source


def test_invalid_draft_is_reopened_by_new_owner_but_no_old_native_curve_is_used(nonlinear_factory):
    n = nonlinear_factory
    nm.apply(n.editor, n.material, n.analysis.Name, draft())
    obj, = nm.native_objects(n.analysis); before = list(obj.YieldPoints)
    invalid = draft(201)
    nm.save(n.editor, n.material, n.analysis.Name, invalid)
    n.metadata = json.loads(json.dumps(n.metadata, allow_nan=False))
    n.editor = FEMEditor(n)  # New editor owner; no previous form required.
    restored = nm.read(n.editor, n.material, n.analysis.Name)
    assert restored['draft'] == invalid and restored['errors'][0]['path'].endswith('.200')
    assert obj.YieldPoints == before and not restored['applied']
    with pytest.raises(ValueError, match='200'): nm.effective(n.editor, n.analysis, n.material)
    with pytest.raises(ValueError, match='200'): nm.apply(n.editor, n.material, n.analysis.Name, invalid)
    assert obj.YieldPoints == before
    repaired = draft(200)
    nm.apply(n.editor, n.material, n.analysis.Name, repaired)
    assert len(nm.effective(n.editor, n.analysis, n.material)['plasticity']['yield_points']) == 200


def test_unapplied_valid_curve_and_external_native_change_are_not_silently_used(nonlinear_factory):
    n = nonlinear_factory
    nm.apply(n.editor, n.material, n.analysis.Name, draft())
    changed = draft(); changed['plasticity']['yield_points'][2][0]='280'
    nm.save(n.editor, n.material, n.analysis.Name, changed)
    with pytest.raises(ValueError, match='적용'): nm.effective(n.editor, n.analysis, n.material)
    nm.apply(n.editor, n.material, n.analysis.Name, changed)
    obj, = nm.native_objects(n.analysis); obj.YieldPoints = ['250,0', '300,.01']
    with pytest.raises(ValueError, match='native'): nm.effective(n.editor, n.analysis, n.material)


def test_explicit_elastic_choice_suppresses_not_deletes_and_geometry_is_separate(nonlinear_factory):
    n = nonlinear_factory
    value = draft(); nm.apply(n.editor, n.material, n.analysis.Name, value)
    obj, = nm.native_objects(n.analysis); old = list(obj.YieldPoints)
    value['law'] = LINEAR
    nm.apply(n.editor, n.material, n.analysis.Name, value)
    assert obj in n.analysis.Group and obj.Suppressed and obj.YieldPoints == old
    assert n.solver.MaterialNonlinearity == 'linear' and nm.effective(n.editor,n.analysis,n.material)['law'] == LINEAR
    nm.settings(n.editor, n.solver, {'nlgeom': True})
    assert n.solver.GeometricalNonlinearity == 'nonlinear' and nm.uses_solid_route(n.analysis,n.metadata)
    assert nm.read(n.editor,n.material,n.analysis.Name)['draft']['plasticity'] == draft()['plasticity']


def test_native_only_duplicate_foreign_unconfirmed_and_unapplied_inputs_fail(nonlinear_factory):
    n = nonlinear_factory
    value=draft(); value['definitions_confirmed']=False
    assert nm.draft_errors(value)[0]['path']=='definitions_confirmed'
    with pytest.raises(ValueError): nm.apply(n.editor,n.material,n.analysis.Name,value)
    assert not nm.native_objects(n.analysis)
    nm.apply(n.editor,n.material,n.analysis.Name,draft())
    obj,=nm.native_objects(n.analysis)
    n.metadata={'keep_other_owner_field':True}  # Existing native-only user model.
    assert nm.effective(n.editor,n.analysis,n.material)['law']==J2
    obj.YieldPoints=['1,0']*201
    assert len(nm.read(n.editor,n.material,n.analysis.Name)['draft']['plasticity']['yield_points'])==201
    with pytest.raises(ValueError,match='200'): nm.effective(n.editor,n.analysis,n.material)
    other=Object(n.doc,'Duplicate','Fem::FeaturePython',Proxy=NS(Type=nm.KIND),
                 LinearBaseMaterial=n.material,MaterialModelNonlinearity='isotropic hardening',YieldPoints=['250,0'])
    n.analysis.addObject(other)
    with pytest.raises(ValueError,match='중복'): nm.effective(n.editor,n.analysis,n.material)
    n.analysis.Group.remove(n.material)
    with pytest.raises(ValueError): nm.read(n.editor,n.material,n.analysis.Name)


def test_twenty_character_fortran_read_is_not_just_python_emulation(tmp_path):
    import shutil, subprocess
    from caelab.calculix_material import native_yield_points
    compiler=shutil.which('gfortran')
    if not compiler: pytest.skip('gfortran unavailable: native F20.0 lexical check not run')
    value=draft(2); value['plasticity']['yield_points'][1][1]='1.234567891234567e-05'
    token=native_yield_points(value['plasticity'])[1].split(',')[1].strip()
    source=tmp_path/'read_field.f90'; binary=tmp_path/'read_field'
    source.write_text('''program read_field
implicit none
character(128) :: raw
real(8) :: value
integer :: status
read(*,'(A)') raw
read(raw(1:20),'(F20.0)',iostat=status) value
if(status /= 0) stop 2
write(*,'(ES25.16E3)') value
end program
''')
    subprocess.run([compiler,str(source),'-o',str(binary)],check=True,capture_output=True,timeout=20)
    result=subprocess.run([str(binary)],input=token+'\n',text=True,check=True,capture_output=True,timeout=5)
    assert float(result.stdout)==pytest.approx(1.234567891234567e-5,rel=5e-13,abs=0)


def test_saved_elastic_application_rejects_a_new_active_native_curve(nonlinear_factory):
    """Astra: the unchanged suppressed object must not certify a different J2."""
    n = nonlinear_factory
    source = draft()
    nm.apply(n.editor, n.material, n.analysis.Name, source)
    old, = nm.native_objects(n.analysis)
    elastic = dict(source, law=LINEAR)
    nm.apply(n.editor, n.material, n.analysis.Name, elastic)
    other = Object(n.doc, 'NewNativePlastic', 'Fem::FeaturePython', Proxy=NS(Type=nm.KIND),
                   LinearBaseMaterial=n.material, MaterialModelNonlinearity='isotropic hardening',
                   YieldPoints=['400,0', '450,.02'], Suppressed=False)
    n.analysis.addObject(other)
    n.solver.MaterialNonlinearity = 'nonlinear'
    before = deepcopy(n.metadata)
    assert old.Suppressed and nm.native_objects(n.analysis) == [other]
    with pytest.raises(ValueError, match='native'):
        nm.effective(n.editor, n.analysis, n.material)
    restored = nm.read(n.editor, n.material, n.analysis.Name)
    assert not restored['applied'] and restored['errors']
    assert restored['draft'] == elastic and n.metadata == before


@pytest.mark.parametrize('change', ['replace', 'suppress', 'remove', 'relink', 'duplicate'])
def test_active_application_snapshot_rejects_native_set_changes(nonlinear_factory, change):
    n = nonlinear_factory
    nm.apply(n.editor, n.material, n.analysis.Name, draft())
    old, = nm.native_objects(n.analysis)
    before = deepcopy(n.metadata)
    if change == 'suppress':
        old.Suppressed = True
    elif change == 'remove':
        n.analysis.Group.remove(old)
    elif change == 'relink':
        old.LinearBaseMaterial = NS(Name='AnotherBase')
    else:
        other = Object(n.doc, 'Replacement', 'Fem::FeaturePython', Proxy=NS(Type=nm.KIND),
                       LinearBaseMaterial=n.material, MaterialModelNonlinearity='isotropic hardening',
                       YieldPoints=list(old.YieldPoints), Suppressed=False)
        n.analysis.addObject(other)
        if change == 'replace':
            n.analysis.Group.remove(old)
    n.metadata = json.loads(json.dumps(n.metadata))
    n.editor = FEMEditor(n)
    with pytest.raises(ValueError):
        nm.effective(n.editor, n.analysis, n.material)
    assert not nm.read(n.editor, n.material, n.analysis.Name)['applied']
    assert n.metadata == before


@pytest.mark.parametrize('law', [LINEAR, J2])
def test_applied_legacy_snapshot_and_other_base_objects_remain_compatible(nonlinear_factory, law):
    n = nonlinear_factory
    nm.apply(n.editor, n.material, n.analysis.Name, draft())
    value = dict(draft(), law=law)
    nm.apply(n.editor, n.material, n.analysis.Name, value)
    # This IS the existing saved schema: no active-set migration/new fields.
    record, = n.metadata['plasticity_drafts']
    assert set(record) == {'analysis_id', 'material_id', 'draft', 'applied_draft', 'applied_native'}
    other = Object(n.doc, 'OtherBaseJ2', 'Fem::FeaturePython', Proxy=NS(Type=nm.KIND),
                   LinearBaseMaterial=NS(Name='DifferentBase'), MaterialModelNonlinearity='isotropic hardening',
                   YieldPoints=['500,0'], Suppressed=False)
    n.analysis.addObject(other)
    n.solver.MaterialNonlinearity = 'nonlinear'
    n.metadata = json.loads(json.dumps(n.metadata)); n.editor = FEMEditor(n)
    result = nm.effective(n.editor, n.analysis, n.material)
    assert result['law'] == law and nm.read(n.editor, n.material, n.analysis.Name)['applied']
    assert (result.get('source_curve') == value['plasticity']) is (law == J2)


def test_reapply_to_explicitly_selected_replacement_does_not_misattribute_source(nonlinear_factory):
    n = nonlinear_factory
    nm.apply(n.editor, n.material, n.analysis.Name, draft())
    old, = nm.native_objects(n.analysis)
    nm.apply(n.editor, n.material, n.analysis.Name, dict(draft(), law=LINEAR))
    old_rows = list(old.YieldPoints)
    other = Object(n.doc, 'Replacement', 'Fem::FeaturePython', Proxy=NS(Type=nm.KIND),
                   LinearBaseMaterial=n.material, MaterialModelNonlinearity='isotropic hardening',
                   YieldPoints=['400,0', '450,.02'], Suppressed=False)
    n.analysis.addObject(other)
    before = deepcopy(n.metadata)
    with pytest.raises(ValueError): nm.effective(n.editor, n.analysis, n.material)
    with pytest.raises(ValueError): nm.apply(n.editor, n.material, n.analysis.Name, draft())
    assert n.metadata == before and old.YieldPoints == old_rows
    # Explicit native cleanup; no automatic deletion/selection of duplicates.
    n.analysis.Group.remove(old)
    chosen = draft(2); chosen['plasticity']['yield_points'] = [['400','0'], ['450','.02']]
    nm.apply(n.editor, n.material, n.analysis.Name, chosen)
    result = nm.effective(n.editor, n.analysis, n.material)
    assert result['native_nonlinear_id'] == other.Name
    assert result['source_curve'] == chosen['plasticity'] != before['plasticity_drafts'][0]['draft']['plasticity']
    assert old.YieldPoints == old_rows and old.Suppressed


# The complete collector/freeze admission, with explicit native-shaped doubles.
from test_contact_execution import model


@pytest.mark.parametrize('single', [False, True])
def test_elastic_native_addition_is_blocked_at_collect_and_freeze(model, monkeypatch, single, tmp_path):
    from test_ns1_native_collect import native_fixture
    from apps.desktop_pre import freeze_contact as exporter
    n = native_fixture(model, monkeypatch, single)
    base = n.objects['PadMaterial']; old = n.plastic
    old.Suppressed = True
    value = dict(draft(), law=LINEAR)
    n.metadata['plasticity_drafts'] = [{'analysis_id': n.analysis.Name, 'material_id': base.Name,
        'draft': deepcopy(value), 'applied_draft': deepcopy(value), 'applied_native': nm._signature(old)}]
    other = NS(**vars(old)); other.Name = 'AdditionalJ2'; other.Suppressed = False
    other.YieldPoints = ['400,0', '450,.02']
    n.analysis.Group.append(other); n.doc.Objects.append(other)
    before = deepcopy(n.metadata)
    with pytest.raises(ValueError, match='native'):
        exporter.collect(n.analysis, n.solver, n.fem)
    with pytest.raises(ValueError, match='native'):
        exporter.freeze_contact(n.analysis, n.solver, tmp_path/'frozen', fem=n.fem)
    assert n.metadata == before and not (tmp_path/'frozen').exists()


def test_applied_plasticity_draft_keeps_native_run_route(nonlinear_factory, monkeypatch):
    from PySide6.QtWidgets import QApplication, QLabel
    from apps.desktop_pre.connection import Connection
    n = nonlinear_factory
    app = QApplication.instance() or QApplication([])
    nm.apply(n.editor, n.material, n.analysis.Name, draft())
    kind = lambda obj: getattr(getattr(obj, 'Proxy', None), 'Type', obj.TypeId)
    monkeypatch.setitem(sys.modules, 'FemGui', NS(getActiveAnalysis=lambda: n.analysis))
    monkeypatch.setitem(sys.modules, 'femtools', NS(femutils=NS(type_of_obj=kind)))
    owner = NS(doc=n.doc, document_id='UserModel', session_id='UserSession', generation=7,
               refresh=lambda: None, read_metadata=n.read_metadata)
    calls = []
    connection = NS(pending=None, App=n.App, owners={n.doc.Name: (owner, None, None)}, panels={},
                    message=QLabel(), send_command=lambda: calls.append(deepcopy(connection.pending)))
    for export_only in (True, False):
        connection.pending = None
        Connection.run(connection, export_only=export_only)
        assert calls[-1]['operation'] == 'pre.freeze', connection.message.text()
        assert calls[-1]['arguments'] == {'analysis_id': n.analysis.Name, 'solver_id': n.solver.Name}
        assert calls[-1]['export_only'] is export_only
    app.processEvents()


@pytest.fixture
def saved_native_admission(nonlinear_factory, monkeypatch):
    """Use real native admission with explicit FreeCAD property/accessor doubles."""
    n = nonlinear_factory
    n.App.GuiUp = False
    n.doc.isTouched = lambda: False
    n.doc.getObject = lambda name: next((obj for obj in n.doc.Objects if obj.Name == name), None)
    for obj in n.doc.Objects: obj.State = []
    def stored(doc):
        assert doc is n.doc
        return n.read_metadata()
    monkeypatch.setattr('apps.desktop_pre.metadata.read', stored)
    monkeypatch.setitem(sys.modules, 'FreeCAD', n.App)
    def members(analysis):
        groups = {'mats_linear': 'Fem::MaterialCommon', 'mats_nonlinear': nm.KIND,
                  'cons_fixed': 'Fem::ConstraintFixed', 'cons_force': 'Fem::ConstraintForce'}
        return NS(**{key: [{'Object': obj} for obj in analysis.Group
                          if nm.native_type(obj) == kind and not getattr(obj, 'Suppressed', False)]
                     for key, kind in groups.items()})
    monkeypatch.setitem(sys.modules, 'femtools', NS(femutils=NS(type_of_obj=nm.native_type),
        membertools=NS(get_mesh_to_solve=lambda analysis: (n.mesh, ''), AnalysisMember=members),
        checksanalysis=NS(check_member_for_solver_calculix=lambda *args: '')))
    monkeypatch.setattr('apps.desktop_pre.native_calculix.validate_analysis', native_validate_analysis)
    return n


@pytest.mark.parametrize('changed', ['draft', 'native_curve', 'solver', 'missing_base', 'foreign_base',
                                      'suppressed_base', 'duplicate_record'])
def test_legacy_typed_material_admission_preserves_saved_plasticity_guards(saved_native_admission, changed):
    n = saved_native_admission
    nm.apply(n.editor, n.material, n.analysis.Name, draft())
    nm.native_objects(n.analysis)[0].State = []
    assert nm.validate_applied_materials(n.analysis, n.solver, n.metadata) == n.metadata['plasticity_drafts']
    assert n.editor.validate_for_run(n.analysis) == []
    if changed == 'draft':
        value = draft(); value['plasticity']['yield_points'][1][0] = '290'
        nm.save(n.editor, n.material, n.analysis.Name, value)
    elif changed == 'native_curve':
        nm.native_objects(n.analysis)[0].YieldPoints = ['300,0', '350,.01']
    elif changed == 'solver':
        n.solver.MaterialNonlinearity = 'linear'
    elif changed == 'missing_base':
        n.analysis.Group.remove(n.material)
    elif changed == 'foreign_base':
        n.material.Document = NS(Name='ForeignDocument')
    elif changed == 'suppressed_base':
        n.material.Suppressed = True
    else:
        n.metadata['plasticity_drafts'].append(deepcopy(n.metadata['plasticity_drafts'][0]))
    before = deepcopy(n.metadata)
    with pytest.raises(ValueError):
        nm.validate_applied_materials(n.analysis, n.solver, n.metadata)
    assert n.metadata == before


@pytest.mark.parametrize('legacy_edit', ['saved_draft', 'duplicate_record', 'native_curve', 'native_kinematic'])
def test_native_material_admission_uses_current_objects_without_changing_legacy_drafts(saved_native_admission, legacy_edit):
    n = saved_native_admission
    nm.apply(n.editor, n.material, n.analysis.Name, draft())
    nm.native_objects(n.analysis)[0].State = []
    nonlinear, = nm.native_objects(n.analysis)
    if legacy_edit == 'saved_draft':
        n.metadata['plasticity_drafts'][0]['draft']['definitions_confirmed'] = False
    elif legacy_edit == 'duplicate_record':
        n.metadata['plasticity_drafts'].append(deepcopy(n.metadata['plasticity_drafts'][0]))
    elif legacy_edit == 'native_curve':
        nonlinear.YieldPoints = ['300,0', '350,.01']
    else:
        nonlinear.MaterialModelNonlinearity = 'kinematic hardening'
    before = list(nonlinear.YieldPoints)
    before_metadata = deepcopy(n.metadata)
    with pytest.raises(ValueError):
        nm.validate_applied_materials(n.analysis, n.solver, n.metadata)
    assert n.editor.validate_for_run(n.analysis) == []
    assert nonlinear.YieldPoints == before and n.metadata == before_metadata
    assert nonlinear.MaterialModelNonlinearity == ('kinematic hardening' if legacy_edit == 'native_kinematic'
                                                  else 'isotropic hardening')
