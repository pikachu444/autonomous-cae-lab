"""Bounded offscreen checks; these do not certify native UI usability."""
import copy
import os
from pathlib import Path
import tempfile

os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from PySide6.QtWidgets import QApplication
from desktop import content_hash, read_document, write_document, MainWindow
from collaboration_spaces import WorkbenchWorkspace

app=QApplication([])
with tempfile.TemporaryDirectory(prefix='caelab-contract-') as folder:
    root=Path(folder)
    source={'id':'case-one','kind':'pre','revision':0,'name':'Original','data':{'selected':0,'variables':[{'name':'E','value':1000}]}}
    first=write_document(root/'case.caeprep',source)
    changed=copy.deepcopy(first);changed['data']['variables'][0]['value']=1500
    second=write_document(root/'case.caeprep',changed,1)
    assert read_document(root/'.history/case-one/1.json')['data']['variables'][0]['value']==1000
    assert second['revision']==2
    try:write_document(root/'case.caeprep',first,1)
    except RuntimeError:pass
    else:raise AssertionError('stale save must be rejected')
    assert read_document(root/'case.caeprep')['data']['variables'][0]['value']==1500
    view=copy.deepcopy(first);view.update(name='Renamed',revision=9,path='moved');view['data']['selected']=9
    assert content_hash(view)==content_hash(first)
    renamed=copy.deepcopy(first);renamed['data']['variables'][0]['name']='nu'
    assert content_hash(renamed)!=content_hash(first)
    node={'id':'case-one','kind':'pre','revision':1,'path':'missing.caeprep','content_hash':content_hash(first)}
    wb=WorkbenchWorkspace({'nodes':[node],'links':[],'selected':'case-one'},lambda *args:None,lambda *args:None)
    original_node=wb.d['nodes'][0]
    wb.relink_path(original_node,root/'case.caeprep')
    assert original_node['revision']==1 and original_node['latest']==2 and original_node['state']=='갱신 필요'
    wrong=write_document(root/'wrong.caeprep',dict(source,id='other'))
    try:wb.relink_path(original_node,root/'wrong.caeprep')
    except ValueError:pass
    else:raise AssertionError('wrong document ID must be rejected')
    wb.deleteLater()
    post=MainWindow('post')
    saved_post=write_document(root/'post.caepost',post.workspace.document())
    post.deleteLater()
    pinned_post=MainWindow('post',root/'post.caepost',saved_post['revision'])
    pinned_post.workspace.component.setCurrentText('응력')
    pinned_post.workspace._apply_view()
    pinned_post.workspace.mutate('결과 셀 선택',lambda:pinned_post.workspace.data.__setitem__('selection',[0,0]))
    assert pinned_post.workspace.data['component']=='응력'
    assert pinned_post.workspace.data['selection']==[0,0]
    assert content_hash(pinned_post.workspace.document())==content_hash(saved_post)
    pinned_post.deleteLater()
    curve=MainWindow('post')
    curve_doc=curve.workspace.document();curve_doc['data'].update(field=[],source_type='csv')
    curve.workspace.set_document(curve_doc)
    assert curve.workspace.tabs.currentIndex()==1
    assert curve.workspace.tabs.tabText(1)=='응답 곡선'
    curve.deleteLater()

for kind in ('pre','runner','post','opt','expert','workbench'):
    win=MainWindow(kind)
    assert win.workspace.document()['kind']==kind
    if kind=='runner':
        win.workspace.case_name.setText('Pending case edit')
        win.workspace.case_name.textEdited.emit('Pending case edit')
        win.workspace.iterations.setValue(33)
        data=win.workspace.document()['data']
        assert data['case_name']=='Pending case edit' and data['iterations']==33
    if kind=='opt':
        win.workspace.study.setText('Pending study edit')
        win.workspace.study.textEdited.emit('Pending study edit')
        win.workspace.budget.setValue(19)
        data=win.workspace.document()['data']
        assert data['study_name']=='Pending study edit' and data['budget']==19
    win.deleteLater()
print('PASS: six constructors, persisted settings, immutable history, stale-save rejection, semantic input hash, exact-ID/revision relink. Offscreen only.')
