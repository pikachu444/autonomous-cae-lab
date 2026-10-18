"""Published processed observations survive two copies without rewriting lineage."""
from copy import deepcopy
from pathlib import Path

import pytest

from caelab.portable_project import inspect_copy,create_copy,open_project,verify_project
from caelab.storage import canonical_hash
from examples.portable_connection_public import create_public_store,command,save


@pytest.mark.parametrize('saved_processing,edit_after_processing,new_processing_in_copy',[
    (True,False,False),(False,False,False),(True,True,False),(True,False,True)])
def test_processed_observation_copy_cold_prepare_and_recopy(tmp_path,saved_processing,edit_after_processing,new_processing_in_copy):
    wb,docs=create_public_store(tmp_path/'original')
    try:
        data=wb.document_read(docs['data']['id'])
        run=next(r for r in data['runs'] if r['job_id']==docs['success_job']['id'])
        source={k:run[k] for k in ('job_id','input_revision','input_sha256')}
        source['document_id']=data['id']
        draft=deepcopy(data['draft'])
        draft['processing']={'source':source,'recipe':{'version':1,'operations':[
            {'id':'origin','operation':'zero_shift','input':'stress','output':'processed',
             'settings':{'source_rows':[int(wb.document_result(data['id'],run['job_id'])['responses']['stress']['source_rows'][0])]}}]}}
        data=command(wb,data,'data.update',{'draft':draft})
        preview=wb.data_documents.processing_preview(data['id'])
        response=wb.document_command(data['id'],'data.processing.apply',{'preview_sha256':preview['preview_sha256']},
            session_id=wb.session_id,expected_generation=data['generation'],command_id='Cprocessing')
        revision=response['processing']['id']
        data=wb.document_read(data['id'])
        if edit_after_processing:
            changed=deepcopy(data['draft']);changed['test_metadata']['protocol']='처리 뒤 편집한 현재 입력'
            data=command(wb,data,'data.update',{'draft':changed})
        if saved_processing:data=save(wb,data)
        original=wb.data_documents.processing_result(data['id'],revision)
        channel_hash=canonical_hash(original['responses']['processed']['processing_channel'])
        plan=wb.document_read(docs['plan']['id']); draft=deepcopy(plan['draft'])
        draft['experiments'][0]['source'].update(processing_revision=revision,response='processed')
        plan=save(wb,command(wb,plan,'numerical.update',{'draft':draft}))
        baseline=wb.numerical_documents.job_arguments(plan['draft'])
        selected=[data['id'],docs['material']['id'],plan['id']]
        inspection=inspect_copy(wb,selected)
        assert inspection['status']=='READY',inspection.get('issues')
        first=tmp_path/'first'
        create_copy(wb,inspection,first,approved=True,command_id='Ccopy',session_id=wb.session_id)
        assert len(wb.manager.list())==2  # Only the fixture's original successful/failed table imports.
    finally:wb.shutdown()
    # Remove the source from ordinary discovery before opening the copy.
    (tmp_path/'original').rename(tmp_path/'original-unavailable')
    for current,destination in [(first,tmp_path/'second'),(tmp_path/'second',None)]:
        cold=open_project(current)
        try:
            rows=cold.documents()['documents']
            data=next(d for d in rows if d['kind']=='data')
            plan=next(d for d in rows if d['kind']=='numerical')
            if destination and new_processing_in_copy:
                preview=cold.data_documents.processing_preview(data['id'])
                response=cold.document_command(data['id'],'data.processing.apply',{'preview_sha256':preview['preview_sha256']},
                    session_id=cold.session_id,expected_generation=data['generation'],command_id='Cnewprocessing')
                revision=response['processing']['id'];data=save(cold,response['document'])
                new_result=cold.data_documents.processing_result(data['id'],revision)
                channel_hash=canonical_hash(new_result['responses']['processed']['processing_channel'])
                draft=deepcopy(plan['draft']);draft['experiments'][0]['source']['processing_revision']=revision
                plan=save(cold,command(cold,plan,'numerical.update',{'draft':draft}))
                baseline=cold.numerical_documents.job_arguments(plan['draft'])
            retained=cold.data_documents.processing_result(data['id'],revision)
            assert canonical_hash(retained['responses']['processed']['processing_channel'])==channel_hash
            from caelab.portable_data_processing import source as verified_source
            record=next(r for r in data['processing_revisions'] if r['id']==revision)
            owner=cold.data_documents
            base=owner._folder(data['id'])/'revisions'/record['retained_revision']
            revision_folder=lambda value:owner._folder(data['id'])/'revisions'/value
            for changed in (('source','input_sha256','portable_processing') if record.get('portable_processing') else ('source',)):
                bad=deepcopy(record)
                if changed=='source':bad['source']['input_sha256']='a'*64
                elif changed=='input_sha256':bad[changed]='b'*64
                else:bad[changed]['sha256']='c'*64
                with pytest.raises(ValueError):verified_source(data,bad,retained,base,revision_folder)
            prepared=cold.numerical_documents.job_arguments(plan['draft'])
            assert prepared['experiments'][0]['observations']==baseline['experiments'][0]['observations']
            assert prepared['experiments'][0]['observation_source']['data_source']==baseline['experiments'][0]['observation_source']['data_source']
            binding=prepared['experiments'][0]['observation_source']
            assert binding.get('current_data_source',binding['data_source'])['document_id']==data['id']
            before=len(cold.manager.list())
            data=save(cold,data)  # Ordinary Save retains proof assets as well as canonical result bytes.
            assert verify_project(current)['status']=='READY'
            if destination:
                inspection=inspect_copy(cold,[r['id'] for r in cold.documents()['documents']])
                assert inspection['status']=='READY',inspection.get('issues')
                create_copy(cold,inspection,destination,approved=True,command_id='Crecopy',session_id=cold.session_id)
            assert len(cold.manager.list())==before
        finally:cold.shutdown()
