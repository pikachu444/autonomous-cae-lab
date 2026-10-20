"""Owner/HTTP and Aster table contracts, no native runtime or model generation."""
from copy import deepcopy
import threading
import pytest
from initial_field_fixture import snapshot,applied


@pytest.mark.parametrize('kind,backend',[('temperature','structure.calculix.initial_fields'),('compatible','structure.codeaster.initial_fields')])
def test_explicit_initial_export_opens_same_http_document_without_calculation(kind,backend,tmp_path):
    from apps.lab.server import LabHTTPServer
    from apps.lab.service import LabService
    from caelab.workbench_client import Client
    server=LabHTTPServer(LabService(tmp_path/'workspace'),0);wb=server.workbench
    thread=threading.Thread(target=server.serve_forever,kwargs={'poll_interval':.02},daemon=True);thread.start()
    client=Client('http://127.0.0.1:'+str(server.server_port))
    try:
        descriptor={'id':'Pinitial','kind':'pre','generation':3,'view_generation':0,'title':'초기장 연결 검사','capabilities':['pre.initial.freeze']}
        auth=wb.native_commands.register(host_id='Hinitial',session_id='Snative',application='freecad',version='CONTROLLED_ONLY',execution_mode='headless',documents=[descriptor],registration_nonce='i'*32)
        wb.document_command('Pinitial','pre.initial.freeze',{},session_id='Snative',expected_generation=3,command_id='Cinitial')
        wb.native_commands.next('Hinitial',session_id='Snative',host_token=auth['host_token'])
        path=snapshot(wb.desktop.root/'Pinitial'/'Finitial',kind)
        wb.native_commands.event('Hinitial',session_id='Snative',host_token=auth['host_token'],event='finished',command_id='Cinitial',documents=[descriptor],outcome={'state':'SUCCEEDED','result':{'status':'COMPLETED','result':{'snapshot_relative':path.relative_to(wb.desktop.root).as_posix(),'label':'초기 상태'},'generation':3,'view_generation':0}})
        opened=client.native_open_simulation('Cinitial');doc=opened['document'];assert doc['draft']['backend']==backend
        assert opened['executed'] is False and not wb.manager.list()
        now=wb.simulation_documents.read(doc['id']);wb.simulation_documents.command(doc['id'],'document.save',{},session_id=now['session_id'],expected_generation=now['generation'])
        again=client.native_open_simulation('Cinitial');assert again['document']['id']==doc['id'] and again['input']['id']==opened['input']['id']
        wrong='calculix' if kind=='compatible' else 'codeaster'
        with pytest.raises(ValueError,match='솔버'):wb.desktop.open_frozen_simulation('Cinitial',solver=wrong)
        assert len(wb.simulation_documents.list())==1 and not wb.manager.list()
    finally:
        server.shutdown();server.server_close();thread.join(2);assert not thread.is_alive()


def test_real_aster_table_contract_separates_provided_fields_from_accepted_orders():
    from test_codeaster_frozen import raw_result
    from caelab.adapters.initial_fields import parse_aster
    from caelab.adapters.codeaster_worker import VECTOR_COMPONENTS,STRESS_COMPONENTS
    m=applied('compatible');mesh={'nodes':m['nodes'],'elements':m['elements'],'fixed_dofs':m['boundary_dofs'],'loads':m['loads'],'initial_field_definition':m['initial_fields']['definition']}
    state=raw_result(mesh);initial=mesh['initial_field_definition']['compatible'];guard=state['native_mesh_checks']
    u={r['node_id']:r['value'] for r in initial['displacements_mm']};t={'NOEUD':[str(i+1) for i in range(len(guard['node_ids_in_native_order']))]}
    for i,k in enumerate(VECTOR_COMPONENTS):t[k]=[u[n][i] for n in guard['node_ids_in_native_order']]
    s={'MAILLE':['1']*5,'POINT':list(range(1,6)),'SOUS_POINT':[1]*5}
    for i,k in enumerate(STRESS_COMPONENTS):s[k]=[initial['stress_MPa'][i]]*5
    rows=[]
    for order,time in ((0,0.),(1,1.),(2,2.)):
        row=deepcopy(state);row.update(order=order,available_orders=[order],access_parameters={'NUME_ORDRE':[order],'INST':[time]})
        for table in row['tables'].values():table['NUME_ORDRE']=[order]*len(table['NUME_ORDRE'])
        rows.append(row)
    raw={'states':rows,'provided_initial':initial,'native_mesh_checks':guard,'native_initial_tables':{'DEPL':t,'SIGM':s},'native_initial_snapshot_status':'CONTROLLED_CHAM_GD_CONTRACT'}
    parsed=parse_aster(raw,mesh);assert [x['order'] for x in parsed['initial_fields_states']]==[0,1,2]
    assert parsed['provided_initial']['stress_MPa'][0]==210. and parsed['stress_points'][0]['stress_MPa'][0]==1.
    for fault in ('missing','value','identity'):
        bad=deepcopy(raw)
        if fault=='missing':
            for column in bad['native_initial_tables']['SIGM'].values():column.pop()
        elif fault=='value':bad['native_initial_tables']['DEPL']['DX'][0]=999.
        else:bad['native_initial_tables']['SIGM']['POINT'][-1]=1
        with pytest.raises(ValueError):parse_aster(bad,mesh)
