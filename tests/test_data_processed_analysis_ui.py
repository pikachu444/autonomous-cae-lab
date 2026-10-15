"""The viewer selects an immutable source; the existing analysis owns execution."""
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from copy import deepcopy
import pytest
pytest.importorskip('PySide6')
from PySide6.QtWidgets import QApplication
from apps.research.data_processing_dialog import DataProcessingPreviewDialog
from caelab.storage import canonical_hash


def retained():
    channel=dict(name='P_grid',values=[0.,1.],axis={'name':'time','unit':'s','values':[0.,1.]},
        samples=[{'sample_id':'s0'},{'sample_id':'s1'}],metadata={'unit':'MPa'})
    return {'diagnostics':{'processing_record':{'id':'Pexact','source':{'document_id':'Towner'}}},
        'channels':{'P_grid':channel},'responses':{'P_grid':{'kind':'series','measure':'first_Piola',
            'unit':'MPa','value':[0.,1.],'axes':[{'name':'time','unit':'s','values':[0.,1.]}]}}}


def test_retained_channel_request_freezes_exact_published_source_and_preserves_result():
    app=QApplication.instance() or QApplication([]);result=retained();original=deepcopy(result)
    dialog=DataProcessingPreviewDialog(result,retained=True,allow_plan=True)
    try:
        assert dialog.analysis_button.isEnabled()
        assert dialog._analysis()
        assert dialog.analysis_source==dict(kind='processing_channel',document_id='Towner',revision='Pexact',
            channel='P_grid',channel_sha256=canonical_hash(original['channels']['P_grid']))
        assert not dialog.plan_requested and result==original
        result['channels']['P_grid']['values'][0]=123
        assert dialog.analysis_source['channel_sha256']==canonical_hash(original['channels']['P_grid'])
    finally:dialog.close();app.processEvents()


@pytest.mark.parametrize('case',['preview','record_missing','channel_missing'])
def test_unpublished_or_missing_channel_never_requests_analysis(case):
    app=QApplication.instance() or QApplication([]);result=retained()
    if case=='record_missing':result['diagnostics']={}
    elif case=='channel_missing':result['channels']={}
    dialog=DataProcessingPreviewDialog(result,retained=case!='preview')
    try:
        assert dialog.analysis_button is None or not dialog.analysis_button.isEnabled()
        assert not dialog._analysis() and dialog.analysis_source is None
    finally:dialog.close();app.processEvents()
