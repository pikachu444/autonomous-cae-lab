"""Real shared model/HTTP records with explicit test-only solve observations."""

from copy import deepcopy
import hashlib

import pytest

from apps.lab.service import LabService
from caelab import Lab
from caelab.adapters.codeaster_geometric import CodeAsterGeometricAdapter
from caelab.storage import canonical_hash, load_json, save_json
from plugins.geometric_nonlinearity.reference import default_settings
from test_lab_server import running, study_arguments


def _test_observation(self, output, settings):
    """A routing stand-in, never evidence of a numerical/native beam PASS."""
    output.mkdir()
    save_json(output / "test_only.json", {"test_only": True, "settings": settings})
    return {"status": "COMPLETED", "solver_status": "COMPLETED", "converged": True,
            "checks": [{"code": "test_transport", "status": "PASS",
                        "observed": "TEST ONLY: native solver was not run"}],
            "metrics": {"test_observation": {"value": 1., "unit": "1", "valid": True}},
            "pending_validations": ["native_global_energy", "static_strength", "material_qualification"],
            "provenance": {"test_only": True, "versions": {"solver": "TEST-ONLY"}},
            "raw_result": "simulation/test_only.json"}


def _files(path):
    return {p.relative_to(path).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in path.rglob('*') if p.is_file()}


def test_geometric_common_model_revisions_and_old_results_survive_changed_material(tmp_path, monkeypatch):
    monkeypatch.setattr(CodeAsterGeometricAdapter, 'solve', _test_observation)
    lab = Lab(tmp_path)
    lab.create_study(**study_arguments())
    settings = default_settings()
    initial = lab.run_model_analysis(study_id='S-http', experiment_id='E-beam-original',
                                    backend=CodeAsterGeometricAdapter.backend, settings=settings)
    before = _files(tmp_path / 'experiments/E-beam-original')
    changed = deepcopy(settings)
    changed['material']['youngs_modulus_mpa'] *= 2
    revised = lab.run_model_analysis(study_id='S-http', experiment_id='E-beam-revised',
                                    backend=CodeAsterGeometricAdapter.backend, settings=changed)
    assert initial['model_revision'] != revised['model_revision']
    assert _files(tmp_path / 'experiments/E-beam-original') == before
    for result, request in [(initial, settings), (revised, changed)]:
        declaration = CodeAsterGeometricAdapter().describe_model(request)
        assert result['model_revision'] == canonical_hash({'settings': request, 'declaration': declaration})
        assert result['status'] == 'COMPLETED_REVIEW_REQUIRED' and result['decision'] == 'NOT_RELEASED'
        assert result['cad_revision'] is None and 'parent_experiment_id' not in result
        proposal = load_json(tmp_path / 'experiments' / result['experiment_id'] / 'proposal.json')
        assert proposal['model']['geometry'] == declaration['model']['geometry']
        assert proposal['loads'] == declaration['loads']
        fields = {field['field']: field for field in proposal['outputs']['fields']}
        assert fields['displacement']['unit'] == 'mm' and fields['rotation']['unit'] == 'rad'
        assert fields['reaction_force']['unit'] == 'N' and fields['reaction_moment']['unit'] == 'N mm'
        assert fields['curvature']['unit'] == '1/mm'
        unknown = set(lab.research_summary(result['experiment_id'])['unknown'])
        assert {'native_global_energy', 'static_strength', 'material_qualification',
                'physical_validation', 'model_qualification'} <= unknown
    with pytest.raises(FileExistsError):
        lab.run_model_analysis(study_id='S-http', experiment_id='E-beam-original',
                               backend=CodeAsterGeometricAdapter.backend, settings=changed)
    assert _files(tmp_path / 'experiments/E-beam-original') == before


def test_geometric_http_preserves_six_component_units_and_refuses_unsupported_load(tmp_path, monkeypatch):
    calls = []
    def observe(self, output, settings):
        calls.append(deepcopy(settings))
        return _test_observation(self, output, settings)
    monkeypatch.setattr(CodeAsterGeometricAdapter, 'solve', observe)
    service = LabService(tmp_path)
    request = default_settings()
    with running(service) as client:
        client.job('study_create', study_arguments())
        arguments = {'study_id': 'S-http', 'experiment_id': 'E-beam-http',
                     'backend': CodeAsterGeometricAdapter.backend, 'settings': request}
        result = client.job('model_analysis_run', arguments)['result']
        inspected = client.request('/api/experiments/E-beam-http')
        assert inspected['result'] == result and calls == [request]
        assert result['decision'] == 'NOT_RELEASED'
        assert {'physical_validation', 'model_qualification', 'native_global_energy'} <= set(inspected['summary']['unknown'])
        invalid = deepcopy(request)
        invalid['history']['moments_n_mm'][-1] *= 2  # Exceeds the frozen 1rad case.
        rejected = client.job('model_analysis_run', dict(arguments, experiment_id='E-beam-http-reject', settings=invalid))['result']
        assert rejected['status'] == 'REJECTED' and rejected['solver_status'] == 'NOT_RUN'
        assert rejected['metrics'] == {} and calls == [request]
        assert not (tmp_path / 'experiments/E-beam-http-reject/simulation').exists()
        assert client.request('/api/experiments/E-beam-http-reject')['result'] == rejected


def test_geometric_preset_is_independent_and_does_not_advertise_input_bindings(tmp_path):
    service = LabService(tmp_path)
    first = service.presets()['codeaster_geometric']
    first['settings']['history']['moments_n_mm'][-1] = -1
    second = service.presets()['codeaster_geometric']
    assert second['settings'] == default_settings()
    assert second['operation'] == 'model_analysis_run'
    assert second['backend'] == CodeAsterGeometricAdapter.backend
    assert second['status'] == 'EXPERIMENTAL' and second['declared_inputs'] is False
    assert '검증 대기' in second['scope'] and 'UNKNOWN' in second['scope']
