"""Service-platform boundary. No WSL/native process; real SciPy owner path."""
from copy import deepcopy
import json
import pytest
from caelab.adapters import native_doctor as doctor
from caelab.pde_document import default_draft
from caelab.jobs import TERMINAL
from test_connected_evaluation_study import service, change, wait


def test_readiness_and_direct_native_restriction_do_not_probe_or_launch(monkeypatch,tmp_path):
    monkeypatch.setattr(doctor,'service_platform',lambda:'win32')
    def forbidden(*args,**kwargs):
        raise AssertionError('No native process or runtime discovery is allowed in this check')
    monkeypatch.setattr(doctor,'_command',forbidden)
    for backend in ('pde.fenicsx','pde.fenicsx.dimensioned','material.mfront','material.mfront.user'):
        result=doctor.doctor_native_backend(backend,execute=False)
        assert result['dependencies']=='UNAVAILABLE'
        assert result['execution']=='NOT_REQUESTED' and result['environment']['service_platform']=='win32'
        assert 'Linux' in result['reason'] and '자동 전환' in result['reason']
    from caelab.adapters.dimensioned_weak import DimensionedWeakAdapter
    from caelab.adapters.user_mfront import UserMFrontAdapter
    from caelab.adapters.mfront_material import _runtime_identity
    for adapter in (DimensionedWeakAdapter(),UserMFrontAdapter()):
        with pytest.raises(RuntimeError,match='Linux'):
            adapter.run(adapter.default_settings(),output=tmp_path)
    with pytest.raises(RuntimeError,match='Linux'):_runtime_identity()
    assert list(tmp_path.iterdir())==[]
    # Installed Python packages are inspected without a version subprocess.
    for backend,dependency in (('pde.scipy.ode','scipy'),('material.felupe','felupe')):
        pytest.importorskip(dependency)
        result=doctor.doctor_native_backend(backend,execute=False)
        assert result['dependencies']=='READY' and not result['environment']['blocked']
        assert result['execution']=='NOT_REQUESTED'


def test_remote_host_is_explicit_unknown_is_not_client_platform(monkeypatch):
    monkeypatch.setattr(doctor,'service_platform',lambda:'win32')
    for backend in ('pde.fenicsx.dimensioned','material.mfront.user'):
        assert doctor.execution_environment(backend,host='win32')['blocked']
        linux=doctor.execution_environment(backend,host='linux')
        assert not linux['blocked'] and linux['installation']=='NOT_CHECKED'
        unknown=doctor.execution_environment(backend,host=None)
        assert not unknown['blocked'] and unknown['label']=='계산 환경 확인 필요'
    assert not doctor.execution_environment('pde.scipy.ode',host='win32')['requires_linux']
    assert not doctor.execution_environment('material.felupe',host='win32')['requires_linux']


def test_windows_service_ode_and_felupe_execute_save_and_cold_reopen_without_wsl(service,monkeypatch):
    pytest.importorskip('scipy');pytest.importorskip('felupe')
    monkeypatch.setattr(doctor,'service_platform',lambda:'win32')
    def forbidden(*args,**kwargs):raise AssertionError('WSL/native probing must not occur')
    monkeypatch.setattr(doctor,'_command',forbidden)
    from caelab.material_document import default_draft as material_draft
    wb,client=service;records=[]
    for kind,draft in (('pde',default_draft('pde.scipy.ode')),('material',material_draft())):
        original=deepcopy(draft)
        doc=client.document_open(kind=kind,draft=draft)
        assert doc['service_platform']=='win32' and doc['diagnostics']==[]
        job=change(client,doc,kind+'.evaluate')['job']['id']
        wait(lambda:client.status(job)['state'] in TERMINAL)
        result=client.document_result(doc['id'],job)
        assert result['execution_status']=='SUCCEEDED' and result['responses']
        saved=change(client,client.document_read(doc['id']),'document.save')['document']
        assert saved['draft']==original
        owner=wb._document_owner(doc['id'])
        stored=json.loads((owner._folder(doc['id'])/'revisions'/saved['saved_revision']/'document.json').read_text(encoding='utf-8'))
        assert 'service_platform' not in stored and 'service_platform' not in stored['draft']
        records.append((kind,doc['id'],job,original,result))
    count=len(wb.manager.list());assert count==2
    assert wb.shutdown()['joined']
    from caelab.workbench import Workbench
    fresh=Workbench(wb.workspace)
    try:
        before=len(fresh.manager.list())
        for kind,identifier,job,draft,result in records:
            reopened=fresh.document_open(kind=kind,document_id=identifier)
            assert reopened['draft']==draft and reopened['service_platform']=='win32'
            assert fresh.document_result(identifier,job)['responses']==result['responses']
        assert len(fresh.manager.list())==before
    finally:fresh.shutdown()
