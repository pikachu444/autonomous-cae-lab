"""Same two acceptance assertions can be run on the supplied baseline and patch.

Baseline fallback copy is only a probe: it never labels missing raw inclusion
as success. New synthetic temporary folders only; every owner closes in finally.
"""
import json
import tempfile
from pathlib import Path
from copy import deepcopy
from examples.portable_connection_public import create_public_store
from caelab.portable_project import inspect_copy,create_copy,open_project
from caelab.related_save_recovery import RawRecoveryDrafts


def keep(wb,doc):
    column=doc['draft']['mapping']['columns']['stress']['column']
    raw={'cells':[{'field_path':['mapping','columns','stress','column'],'original_value':column,
        'raw_text':'1e','position':{'table':'mapping','row':1,'column':2},'editor_kind':'unfinished'}],
        'local_draft':deepcopy(doc['draft']),'editor_revision':'UbaselineProbe'}
    recovery=RawRecoveryDrafts(wb.root,wb._document_owner)
    proposal=recovery.prepare([{'identity':recovery.identity(doc),'raw':raw}])
    if any(t['problems'] for t in proposal['targets']):return proposal,None
    return proposal,recovery.execute(proposal)


def main():
    with tempfile.TemporaryDirectory(prefix='c3a-red-green-') as temporary:
        root=Path(temporary);wb,docs=create_public_store(root/'original')
        observations={}
        try:
            doc=wb.document_read(docs['data']['id']);proposal,kept=keep(wb,doc)
            assert kept and kept['all_kept'],proposal
            choices=[{'document_id':doc['id'],'capsule_id':kept['targets'][0]['capsule_id']}]
            selections=[docs[k]['id'] for k in ('data','material','plan','second_plan')]
            try:
                plan=inspect_copy(wb,selections,recovery_archives=choices)
                observations['explicit_original_Q_included']=bool(plan.get('recovery_archives'))
            except TypeError as error:
                observations['explicit_original_Q_included']=False
                observations['missing_api']=str(error)
                plan=inspect_copy(wb,selections)
            assert plan['status']=='READY',plan
            receipt=create_copy(wb,plan,root/'copy',approved=True,command_id='CbaselineProbe',session_id=wb.session_id)
            current_id=next(r['document_id'] for r in receipt['documents'] if r['source_document_id']==doc['id'])
        finally:wb.shutdown()
        current=open_project(root/'copy')
        try:
            proposal,kept=keep(current,current.document_read(current_id))
            observations['current_Data_Keep_verified']=bool(kept and kept['all_kept'])
            if not kept: observations['current_Keep_problems']=proposal['targets'][0]['problems']
        finally:current.shutdown()
        print(json.dumps(observations,ensure_ascii=False,indent=2),flush=True)
        assert observations['explicit_original_Q_included'] and observations['current_Data_Keep_verified'], 'C3A acceptance remains RED'


if __name__=='__main__':main()
