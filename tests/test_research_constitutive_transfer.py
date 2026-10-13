"""Actual FELUPE plus exact HTTP transfer reader using explicit controlled native fields."""
from copy import deepcopy
import numpy as np
import pytest
from caelab.material_document import default_draft
from caelab.jobs import TERMINAL
from caelab.storage import canonical_hash
from test_connected_evaluation_study import service,controlled,sources,change,wait


def test_independent_felupe_probe_same_baseline_and_cold_inspection(service):
    pytest.importorskip('felupe')
    wb,client=service;draft=default_draft()
    draft['settings'].update(model='neo_hooke',parameters={'mu':30.,'lmbda':50.})
    draft['settings']['deformation_gradient'][1][0][1]=.03
    draft['settings']['tangent_probe']={'increment':1,'input_component':'xy','steps':[1e-5,1e-6,1e-7]}
    doc=client.document_open(kind='material',draft=draft)
    receipt=change(client,doc,'material.evaluate');job=receipt['job']['id']
    wait(lambda:client.status(job)['state'] in TERMINAL)
    result=client.document_result(doc['id'],job);assert result['execution_status']=='SUCCEEDED',result
    view=client.constitutive_inspect(doc['id'],job,1)
    assert view['increment']==1 and view['pair'].startswith('dP')
    assert view['state_trial'] is None and view['state_committed'] is None and view['residual'] is None
    for probe in view['finite_differences']:
        assert np.allclose(probe['finite_difference'],probe['analytic'],rtol=2e-5,atol=1e-5)
    before=client.document_read(doc['id']);assert before['draft']==draft
    saved=change(client,before,'document.save')['document']
    from caelab.workbench import Workbench
    fresh=Workbench(wb.workspace);fresh.document_open(kind='material',document_id=saved['id'])
    again=fresh.constitutive_inspect(doc['id'],job,1)
    assert again['tangent']==view['tangent'] and again['source'] is not None
    assert len(wb.manager.list())==1


def test_exact_transfer_rows_bound_values_failed_run_and_saved_read(service,controlled):
    wb,client=service;original,draft=sources(client)
    doc=client.document_open(kind='evaluation',draft=draft)
    first=change(client,doc,'evaluation.run')['job']['id']
    wait(lambda:client.status(first)['state'] in TERMINAL)
    failed=client.evaluation_transfer(doc['id'],first,'TtoU',0)
    # The real execution wrapper saves actual bound settings even when the
    # controlled structural solver fails. Failure is never inferred from equality.
    assert failed['target_attempt']['state']=='FAILED'
    assert all(r['supplied']==320. and r['received']==320. for r in failed['rows'])
    second=change(client,client.document_read(doc['id']),'evaluation.run')['job']['id']
    wait(lambda:client.status(second)['state'] in TERMINAL)
    view=client.evaluation_transfer(doc['id'],second,'TtoU',0,start=1,count=2)
    assert view['exact_values_match'] and view['metadata']['unit']=='K'
    assert view['metadata']['coordinate_units']=='m' and len(view['rows'])==2
    assert all(row['available'] and row['required'] and row['difference']==0 for row in view['rows'])
    assert view['reference_temperature']==draft.get('reference_temperature',original[1]['draft']['settings']['reference_temperature'])
    for source in original:assert client.document_read(source['id'])['draft']==source['draft']
    saved=change(client,client.document_read(doc['id']),'document.save')['document']
    from caelab.workbench import Workbench
    fresh=Workbench(wb.workspace);fresh.document_open(kind='evaluation',document_id=saved['id'])
    assert fresh.evaluation_transfer(doc['id'],second,'TtoU',0,start=1,count=2)['rows']==view['rows']
    count=len(wb.manager.list())
    with pytest.raises(Exception):client.evaluation_transfer(doc['id'],second,'TtoU',9)
    assert len(wb.manager.list())==count
