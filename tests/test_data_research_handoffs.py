"""Actual table imports, retained comparisons and unexecuted workspace handoffs."""
from copy import deepcopy
import shutil
import time

import pytest

from caelab.workbench import Workbench
from caelab.data_document import default_draft


def command(wb, doc, operation, args=None):
    current=wb.document_read(doc['id'])
    return wb.document_command(doc['id'],operation,args or {},session_id=current['session_id'],
                                expected_generation=current['generation'])


def imported(wb, text, name):
    entry=wb.upload(name,text.encode('utf-8'))
    draft=default_draft()
    draft['data_id']=entry['id']
    draft['mapping']['skip_header']=1
    spec=draft['mapping']['columns']['response']
    spec.update(unit='MPa',component='xx',location='material_point',frame='material_cartesian',measure='infinitesimal_Cauchy')
    spec['axis'].update(name='time',unit='s')
    spec['row_selection']={'exclude_rows':[2],'reasons':{'2':'sensor disconnected'}}
    draft['mapping']['columns']['transverse']=deepcopy(spec)
    draft['mapping']['columns']['transverse'].update(column=2,component='yy')
    draft['test_metadata']={'test_id':name,'specimen':'새 시편'}
    doc=wb.document_open(kind='data',draft=draft)
    receipt=command(wb,doc,'data.import')
    job=receipt['job']['id']
    end=time.monotonic()+8
    while wb.manager.status(job)['state'] not in {'SUCCEEDED','FAILED'} and time.monotonic()<end:
        time.sleep(.005)
    assert wb.manager.status(job)['state']=='SUCCEEDED'
    return wb.document_read(doc['id']),job


def test_retained_comparison_paged_raw_and_followup_save_reopen(tmp_path):
    wb=Workbench(tmp_path)
    try:
        a,ja=imported(wb,'t,x,y\n0,3,6\n1,nan,nan\n2,5,8\n','측정.csv')
        b,jb=imported(wb,'t,x,y\n0,3.25,6.25\n1,nan,nan\n2,5.25,8.25\n','보존 예측.csv')
        source={'document_id':a['id'],'job_id':ja,'response':'response',
                'input_revision':a['runs'][0]['input_revision'],'input_sha256':a['runs'][0]['input_sha256']}
        prediction={'document_id':b['id'],'job_id':jb,'response':'response'}
        comparison=wb.document_compare(source,prediction)
        assert comparison['comparison']['rmse']==pytest.approx(.25)
        assert comparison['comparison']['alignment_policy']=='exact_samples_preserving_calculation_gaps'
        assert comparison['comparison']['observation_source_rows']==[1,3]
        assert wb.document_compare(source,prediction)['id']==comparison['id']
        assert len(wb.document_read(a['id'])['comparisons'])==1
        page=wb.document_result(a['id'],ja,selection={'responses':['response'],'rows':[1,2]})['responses']['response']
        assert page['value']==[5]
        assert page['raw_samples']['value']==['nan']
        assert page['raw_samples']['calculation_valid']==[False]
        material=wb.document_open(kind='material')
        plan=wb.desktop.data_followup(source,'numerical',session_id=wb.session_id,
            command_id='Cfit_followup',material_document_id=material['id'])
        assert plan['executed'] is False
        assert plan['document']['draft']['experiments'][0]['source']==source
        assert len(wb.manager.list())==2  # No Material run, optimizer or inference at handoff.
        discussion=wb.desktop.data_followup(source,'expert',session_id=wb.session_id,command_id='Cexpert_followup')
        assert discussion['document']['draft']['composer']['evidence'][0]['job_id']==ja
        assert not discussion['document']['runs']
        again=wb.desktop.data_followup(source,'expert',session_id=wb.session_id,command_id='Cexpert_again')
        assert again['document']['id']==discussion['document']['id']
        assert len(again['document']['draft']['composer']['evidence'])==1
        saved=command(wb,a,'document.save')['document']
        old_input=wb.root/'inputs'/a['draft']['data_id']
        old_input.rename(old_input.with_name(old_input.name+'-retained-original'))
        working=wb.data_documents._folder(a['id'])/'comparisons'
        working.rename(working.with_name('comparisons-working-retained'))
        identity=saved['id']
        comparison_id=comparison['id']
        wb.shutdown()
        wb=Workbench(tmp_path)
        reopened=wb.document_open(kind='data',document_id=identity)
        assert wb.data_documents.comparison(identity,comparison_id)['comparison']['rmse']==pytest.approx(.25)
        assert reopened['comparisons'][0]['id']==comparison_id
        assert not reopened['dirty']
        assert len(wb.manager.list())==2
        with pytest.raises(ValueError,match='session'):
            wb.desktop.data_followup(source,'expert',session_id=saved['session_id'],command_id='Cold_session')
    finally:
        wb.shutdown()
