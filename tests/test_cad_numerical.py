"""Focused CAD research contracts. Native objects/processes below are test doubles."""
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace as NS
import zipfile

import pytest

from caelab.adapters.cad_analysis import CADAnalysisAdapter, BACKEND, select_responses
from caelab.model_parameters import bind
from caelab.evaluation import read_result
from caelab.native_cad import publish_project, sha, KIND
from caelab.workbench import Workbench


def recipe():
    return {'version': 1, 'analysis_id': 'Analysis', 'solver_id': 'Solver',
        'route': 'single_solid', 'qualification': 'UNKNOWN', 'pairs': [],
        'variables': [{'id': 'width', 'label': 'Stock width', 'analysis_id': 'Analysis',
            'target': {'object_id': 'Stock', 'native_type': 'Part::Box', 'family': 'geometry', 'field': 'Width'},
            'value': .02, 'unit': 'm', 'lower': .01, 'upper': .03}],
        'responses': [{'id': 'uz_max', 'kind': 'displacement', 'component': 'Z',
                       'unit': 'mm', 'increment': 'final', 'reduction': 'max'}],
        'meshes': [{'object_id': 'Mesh', 'body_id': 'Stock', 'settings': {}}],
        'correspondence': {'policy': 'freecad-mapped-element-v1', 'targets': {}, 'links': []}}


def settings():
    return {'data_id': 'Dsource', 'source_sha256': 'a' * 64,
            'recipe': recipe(), 'values': {'width': .02}}


def test_typed_binding_keeps_model_limits_units_and_source():
    adapter, original = CADAnalysisAdapter(), settings()
    changed = bind(adapter, original, {'width': .02123456789})
    assert changed['values']['width'] == .02123456789
    assert changed['recipe'] == original['recipe']
    assert changed['source_sha256'] == original['source_sha256']
    assert adapter.describe_inputs(changed)[0]['unit'] == 'm'
    assert original['values']['width'] == .02
    with pytest.raises(ValueError):
        bind(adapter, original, {'width': .04})


def test_binding_failure_has_an_attempt_before_binding(tmp_path, monkeypatch):
    from caelab.adapters import native_evaluation as module
    output = tmp_path / 'result'
    factory = module.NativeEvaluationFactory(BACKEND, output / 'evaluations', retained_root=output)
    def reject(adapter, template, values):
        requests = list((output / 'evaluations').glob('candidate-*.request.json'))
        assert len(requests) == 1
        raise ValueError('explicit test binding refusal')
    monkeypatch.setattr(module, 'bind', reject)
    with factory.prepare(settings()) as evaluator:
        result = evaluator.evaluate({'width': .021})
    assert result['execution_status'] == 'FAILED' and result['responses'] == {}
    assert result['diagnostics']['phase'] == 'binding'
    attempts = factory.retained_attempts()
    assert len(attempts) == 1 and attempts[0]['values'] == {'width': .021}
    saved = read_result(output / attempts[0]['relative'])
    assert saved['settings']['values']['width'] == .02


def test_signed_displacement_and_poisson_domains():
    from apps.desktop_pre.research_inputs import validate_limits
    displacement = {'target': {'family': 'displacement', 'field': 'zDisplacement'}}
    assert validate_limits(displacement, -.001, 0, -.0003) == (-.001, 0.)
    material = {'target': {'family': 'material', 'field': 'PoissonRatio'}}
    with pytest.raises(ValueError, match='Poisson'):
        validate_limits(material, 0, .5, .3)
    assert validate_limits(material, -.2, .49, .3) == (-.2, .49)


def test_native_unit_read_is_explicit():
    from apps.desktop_pre.research_inputs import value_at, quantity_value
    class Quantity:
        def getUserPreferred(self):
            return ('0.3 mm', 1., 'mm')
        def getValueAs(self, unit):
            return NS(Value={'mm': .3, 'm': .0003}[unit])
    obj = NS(Name='Load', TypeId='Fem::ConstraintDisplacement', zDisplacement=Quantity())
    owner = NS(_object=lambda name: obj)
    target = {'object_id': 'Load', 'native_type': obj.TypeId,
              'family': 'displacement', 'field': 'zDisplacement'}
    assert value_at(owner, target, 'm') == .0003
    assert quantity_value(owner, obj.zDisplacement) == (.3, 'mm')


def test_native_mapping_unchanged_changed_missing_and_split(monkeypatch):
    from apps.desktop_pre import candidate_correspondence as module
    mapped = 'Face5;:M;CUT;:H2af:7,F'
    subname = ';' + mapped + '.Face5'
    old = {'object_id': 'Bridge', 'type': 'Part::Cut', 'brep_sha256': 'old',
           'global_placement': [], 'subelements': [{'name': 'Face5', 'brep_sha256': 'old-face'}]}
    shape = NS(ElementMap={mapped: 'Face5'},
        getElementMappedName=lambda name: mapped,
        getElementIndexedName=lambda name: 'Face5',
        getElementHistory=lambda name: (7, 'upstream', []),
        getElement=lambda name: NS(isNull=lambda: False))
    obj = NS(Name='Bridge', Label='Bridge', TypeId='Part::Cut', Shape=shape)
    obj.resolveSubElement = lambda name: (obj, subname, 'Face5')
    owner = NS(_object=lambda name: obj)
    identity = module.anchor(obj, 'Face5')
    record = {'target': old, 'elements': [identity], 'history_unavailable': None}
    monkeypatch.setattr(module, '_target', lambda obj, names: deepcopy(old))
    assert module.resolve(owner, record)[2] == 'unchanged'
    monkeypatch.setattr(module, '_target', lambda obj, names: {**old, 'brep_sha256': 'changed'})
    assert module.resolve(owner, record) == (obj, ['Face5'], 'native_mapped_element')
    obj.resolveSubElement = lambda name: (obj, subname, '?Face5')
    with pytest.raises(ValueError, match='UNRESOLVED'):
        module.resolve(owner, record)
    obj.resolveSubElement = lambda name: (obj, subname, 'Face5')
    shape.ElementMap['descendant'] = 'Face9'
    shape.getElementHistory = lambda name: (7, mapped, []) if name == 'descendant' else (7, 'upstream', [])
    with pytest.raises(ValueError, match='SPLIT'):
        module.resolve(owner, record)
    raw = {**record, 'elements': [], 'history_unavailable': 'No native map'}
    with pytest.raises(ValueError, match='UNRESOLVED'):
        module.resolve(owner, raw)


def test_response_uses_actual_signed_components_and_blocks_missing():
    r = recipe()
    calculated = {'responses': {'displacement': {'value': [[0., 0., -.2], [0., 0., -.1]],
                                                 'metadata': {'node_ids': [1, 2]}}}}
    selected = select_responses(calculated, Path('.'), r)
    assert selected['uz_max']['value'] == -.1 and selected['uz_max']['unit'] == 'mm'
    calculated['responses']['displacement']['value'][1][2] = None
    with pytest.raises(ValueError, match='missing'):
        select_responses(calculated, Path('.'), r)


def archive(path, recipe_value):
    native = path.parent / 'model.FCStd'
    native.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(native, 'w') as stream:
        stream.writestr('Document.xml', '<Document><Objects Count="0"/><ObjectData Count="0"/></Document>')
    manifest = {'kind': KIND, 'schema_version': 1, 'document_id': 'Pbase',
                'revision': 'Rbase', 'entry': 'documents/model.FCStd',
                'documents': [{'file': 'documents/model.FCStd', 'bytes': native.stat().st_size,
                               'sha256': sha(native)}], 'unavailable_dependencies': [],
                'metadata': {'candidate_recipe': recipe_value}, 'qualification': 'UNKNOWN'}
    return publish_project(path, manifest, {'documents/model.FCStd': native})


@pytest.mark.parametrize('operation', ['doe', 'optimize'])
def test_completed_capture_opens_existing_owners_without_run_and_retries_preserve_edits(tmp_path, monkeypatch, operation):
    from caelab.cad_numerical import prepare_plan, resolve_settings
    wb = Workbench(tmp_path / 'store')
    try:
        project = wb.desktop.root / 'Pbase' / 'project_staging' / 'Rbase' / 'retained.caepre'
        saved = archive(project, recipe())
        result = {'project_relative': project.relative_to(wb.desktop.root).as_posix(),
                  'project_sha256': saved['sha256'], 'recipe': recipe(), 'revision': 'Rbase', 'label': 'Public model'}
        command = {'operation': 'pre.research.prepare', 'state': 'SUCCEEDED',
                   'document_id': 'Pbase', 'request_hash': 'a' * 64,
                   'outcome': {'result': {'status': 'COMPLETED', 'result': result}}}
        monkeypatch.setattr(wb.native_commands, 'status', lambda identifier: deepcopy(command))
        monkeypatch.setattr(wb.manager, 'submit', lambda *a, **k: pytest.fail('Planning must not execute'))
        opened = prepare_plan(wb, 'Ccapture', operation=operation)
        plan = opened['document']
        assert plan['kind'] == 'numerical' and not plan['diagnostics'] and not plan['runs']
        assert plan['draft']['request']['operation'] == operation
        assert plan['draft']['request']['inputs']['variables'][0]['unit'] == 'm'
        assert opened['source']['kind'] == 'simulation'
        setting = plan['draft']['request']['inputs']['settings']
        internal = resolve_settings(wb, setting)
        assert resolve_settings(wb, internal) == internal
        with pytest.raises(ValueError, match='paths'):
            resolve_settings(wb, {**internal, '_native_context': {'source': 'other'}})
        draft = deepcopy(plan['draft'])
        draft['request']['purpose'] = 'Edited independent study'
        edited = wb.numerical_documents.command(plan['id'], 'numerical.update', {'draft': draft},
            session_id=wb.session_id, expected_generation=plan['generation'])['document']
        again = prepare_plan(wb, 'Ccapture', operation=operation)['document']
        assert again['draft'] == edited['draft']
        wb.numerical_documents.command(plan['id'], 'document.save', {},
            session_id=wb.session_id, expected_generation=again['generation'])
        assert wb.document_open(document_id=plan['id'])['draft'] == again['draft']
    finally:
        wb.shutdown()
