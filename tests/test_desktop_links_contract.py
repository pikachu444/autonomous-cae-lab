"""Portable service connection doubles; never starts a native app or solver."""
from pathlib import Path
import time

import pytest

from test_pre_frozen_analysis import native
from apps.desktop_pre.freeze_analysis import freeze_analysis
from caelab.evaluation import file_hash
from caelab.workbench import Workbench


@pytest.mark.parametrize('publication_fails', [False, True])
def test_native_export_submit_retry_and_post_registration(native, tmp_path, monkeypatch, publication_fails):
    wb=Workbench(tmp_path/'workspace')
    runs=[]
    def run_double(backend,settings,*,output,selection=None):
        assert backend=='structure.calculix.frozen'
        assert Path(settings['snapshot_path']).is_file()
        runs.append(settings['data_id'])
        path=output/'post'/'displacement.vtu'
        path.parent.mkdir(parents=True)
        path.write_text('<VTKFile type="UnstructuredGrid"><UnstructuredGrid><Piece NumberOfPoints="0" NumberOfCells="0"/></UnstructuredGrid></VTKFile>')
        return {'execution_status':'SUCCEEDED','responses':{},'checks':[],
            'engineering_valid':False,'qualification':'UNKNOWN','diagnostics':{'mode':'TEST_ONLY_ROUTING_DOUBLE'},
            'post_artifact':{'relative':'post/displacement.vtu','bytes':path.stat().st_size,'sha256':file_hash(path)}}
    monkeypatch.setattr('caelab.workbench.run',run_double)
    if publication_fails:
        def refuse_publication(*args, **kwargs):
            raise OSError('TEST_ONLY post input registration failure')
        monkeypatch.setattr('caelab.workbench.register_native_input', refuse_publication)
    try:
        descriptor={'id':'Pdesign','kind':'pre','generation':3,'view_generation':0,'title':'Editable test design','capabilities':['pre.freeze','document.activate']}
        auth=wb.native_commands.register(host_id='Hpre',session_id='Snative',application='freecad',version='TEST_ONLY',execution_mode='headless',documents=[descriptor],registration_nonce='n'*32)
        command=wb.document_command('Pdesign','pre.freeze',{},session_id='Snative',expected_generation=3,command_id='Cfreeze')
        dispatched=wb.native_commands.next('Hpre',session_id='Snative',host_token=auth['host_token'])['command']
        assert dispatched['command_id']==command['command_id']
        manifest=freeze_analysis(native.analysis,native.solver,wb.desktop.root/'Pdesign')
        result={'status':'COMPLETED','result':{'snapshot_relative':manifest.relative_to(wb.desktop.root).as_posix(),'label':'Native export double'},'generation':3,'view_generation':0}
        outcome={'state':'SUCCEEDED','result':result}
        wb.native_commands.event('Hpre',session_id='Snative',host_token=auth['host_token'],event='finished',command_id='Cfreeze',outcome=outcome,documents=[descriptor])
        submitted=wb.desktop.submit_frozen('Cfreeze')
        retry=wb.desktop.submit_frozen('Cfreeze')
        assert retry['job']['id']==submitted['job']['id']
        assert retry['input']['id']==submitted['input']['id']
        deadline=time.monotonic()+5
        while time.monotonic()<deadline:
            status=wb.manager.status(submitted['job']['id'])
            if status['state'] in {'SUCCEEDED','FAILED'}:
                assert status['state']==('FAILED' if publication_fails else 'SUCCEEDED'),status
                break
            time.sleep(.01)
        else:
            pytest.fail('Portable routing job did not finish')
        navigation=wb.desktop.navigation(submitted['job']['id'])
        assert navigation['origin_document']['id']=='Pdesign'
        assert navigation['frozen_origin']['generation']==3
        assert navigation['retained_design_input_id']==submitted['input']['id']
        if publication_fails:
            assert navigation['post_input'] is None
            saved=wb.result(submitted['job']['id'])
            assert saved['native_execution_status']=='SUCCEEDED'
            assert saved['post_registration']['status']=='FAILED'
            assert (wb.root/'native'/submitted['job']['id']/'post'/'displacement.vtu').is_file()
        else:
            assert navigation['post_input']['format']=='vtu'
            assert wb.native_input(navigation['post_input']['id'])['format']=='vtu'
        assert runs==[submitted['input']['id']]
    finally:
        assert wb.shutdown()['joined']


def test_native_application_kind_and_reserved_document_id_are_rejected(tmp_path):
    wb=Workbench(tmp_path)
    try:
        base={'id':'Pdesign','kind':'pre','generation':0,'view_generation':0,'capabilities':['pre.freeze']}
        kwargs={'host_id':'Howner','session_id':'Sowner','application':'paraview','version':'TEST_ONLY','execution_mode':'headless','registration_nonce':'n'*32}
        with pytest.raises(ValueError,match='kind disagree'):
            wb.native_commands.register(**kwargs,documents=[base])
        for prefix in ('M','T','N'):
            with pytest.raises(ValueError,match='unique native'):
                wb.native_commands.register(**{**kwargs,'application':'freecad'},documents=[{**base,'id':prefix+'reserved'}])
    finally:
        assert wb.shutdown()['joined']
