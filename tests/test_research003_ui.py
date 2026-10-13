"""Qt command/read paths; no native solver. Actual SciPy/FELUPE only where selected."""
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import pytest
pytest.importorskip('PySide6')
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QThreadPool
from test_connected_evaluation_study import service,controlled,sources,change,wait
from caelab.jobs import TERMINAL


@pytest.fixture
def app():
    app=QApplication.instance() or QApplication([])
    yield app
    # Queued receivers run before service fixture releases its HTTP server.
    QThreadPool.globalInstance().waitForDone(5000);app.processEvents()


def test_ode_expression_draft_actual_result_and_small_window(service,app):
    from apps.research.pde_window import PDEWindow
    from caelab.pde_document import default_draft
    client=service[1]
    doc=client.document_open(kind='pde',draft=default_draft('pde.scipy.ode'))
    window=PDEWindow(client,document_id=doc['id'],poll_interval=0);window.resize(1100,780);window.show()
    try:
        wait(lambda:window.document and not window._busy,app)
        window.tree.setCurrentItem(window._nodes[('settings','states')]);app.processEvents()
        field=window.fields[('settings','states',0,'rhs')][0]
        field.setPlainText('temperature + rate');window.validate_inputs()
        wait(lambda:not window._busy,app)
        assert window.local_dirty and window._input_checks
        assert window.edited_draft()['settings']['states'][0]['rhs']=='temperature + rate'
        assert len(service[0].manager.list())==0
        window.fields[('settings','states',0,'rhs')][0].setPlainText('-rate*(temperature-ambient)')
        window.apply_inputs();wait(lambda:not window._busy,app)
        window.evaluate();wait(lambda:not window._busy and window.document['runs'],app)
        job=window.document['runs'][-1]['job_id'];wait(lambda:client.status(job)['state'] in TERMINAL,app)
        window._selected_job=job;window._result_key=None;window.refresh_result()
        wait(lambda:window._result and not window._busy,app)
        assert window._result['responses']['temperature']['unit']=='K'
        assert window.size().width()==1100 and window.size().height()==780
        assert window.result_canvas.width()>350 and window.result_canvas.height()>230
    finally:
        window._allow_close=True;window.close();QThreadPool.globalInstance().waitForDone(5000);app.processEvents()


def test_transfer_actual_bound_rows_and_plot_selection(service,controlled,app):
    from apps.research.transfer_inspection_window import TransferInspectionWindow
    wb,client=service;controlled['fail_structure']=False
    _,draft=sources(client);doc=client.document_open(kind='evaluation',draft=draft)
    job=change(client,doc,'evaluation.run')['job']['id'];wait(lambda:client.status(job)['state'] in TERMINAL,app)
    window=TransferInspectionWindow(client,doc['id'],job);window.show()
    try:
        wait(lambda:len(window._rows)==4,app)
        window.table.selectRow(2);app.processEvents()
        assert window._rows[2]['supplied']==window._rows[2]['received']==320.
        assert window.canvas.height()>240 and window.table.rowCount()==4
        assert '완료' in window.status.text()
        count=len(wb.manager.list());window._page(0)
        wait(lambda:len(window._rows)==4,app);assert len(wb.manager.list())==count
    finally:
        window.close();QThreadPool.globalInstance().waitForDone(5000);app.processEvents()


def test_native_material_source_editor_contract_without_simulation_changes(service,app):
    from apps.research.native_material_window import NativeMaterialWindow
    from caelab.user_material import default_settings
    client=service[1];draft={'backend':'material.mfront.user','settings':default_settings()}
    doc=client.document_open(kind='material',draft=draft)
    window=NativeMaterialWindow(client,document_id=doc['id'],poll_interval=0);window.show()
    try:
        wait(lambda:window.document and not window._busy,app)
        assert window.new_action.text()=='새 구성식…'
        assert window.evaluate_button.text()=='빌드만 실행'
        window.tree.setCurrentItem(window._nodes[('settings','source')]);app.processEvents()
        assert ('settings','source') not in window.fields # source editor is separate, not a giant inline field
        assert window.edited_draft()==draft and not service[0].manager.list()
    finally:
        window._allow_close=True;window.close();QThreadPool.globalInstance().waitForDone(5000);app.processEvents()



def test_user_source_review_cancel_then_local_permission_no_build(service,app,tmp_path,monkeypatch):
    from apps.research.material_build_dialog import MaterialBuildDialog
    from caelab import material_build_permission as permission,user_material as domain
    monkeypatch.setattr(permission,'directory',lambda:tmp_path/'operator')
    wb,client=service;settings=domain.default_settings()
    context=client.request('/api/workbench/material-build-context')
    dialog=MaterialBuildDialog(client,context,settings)
    dialog.show();app.processEvents()
    assert dialog.source.toPlainText()==settings['source']
    assert dialog.confirm.isEnabled()
    dialog.reject()
    assert not permission.is_admitted(settings['source'],settings['behaviour'])
    reopened=MaterialBuildDialog(client,context,settings)
    reopened.approve()
    assert reopened.approved and permission.is_admitted(settings['source'],settings['behaviour'])
    assert not wb.manager.list() # permission is not a hidden build/evaluation
    changed=dict(settings,source=settings['source']+'\n')
    assert not permission.is_admitted(changed['source'],changed['behaviour'])



@pytest.mark.parametrize('accept',[False,True])
def test_source_modal_preserves_other_window_property_and_exact_generation(service,app,monkeypatch,accept):
    from PySide6.QtWidgets import QDialog,QPlainTextEdit
    from apps.research.native_material_window import NativeMaterialWindow
    from caelab.user_material import default_settings
    from copy import deepcopy
    client=service[1];draft={'backend':'material.mfront.user','settings':default_settings()}
    doc=client.document_open(kind='material',draft=draft)
    window=NativeMaterialWindow(client,document_id=doc['id'],poll_interval=0);window.show()
    try:
        wait(lambda:window.document and not window._busy,app)
        def edit(dialog):
            fresh=client.document_read(doc['id']);changed=deepcopy(fresh['draft'])
            changed['settings']['properties'][0]['value']=2e9
            updated=change(client,fresh,'material.update',{'draft':changed})['document']
            # A queued document read may finish inside the nested modal loop.
            window._show_document(updated)
            dialog.findChild(QPlainTextEdit).setPlainText(draft['settings']['source']+'\n// reviewed version\n')
            return QDialog.DialogCode.Accepted if accept else QDialog.DialogCode.Rejected
        monkeypatch.setattr(QDialog,'exec',edit)
        window.edit_law_source()
        assert window.edited_draft()['settings']['properties'][0]['value']==2e9
        if accept:
            assert window.local_dirty and window.edited_draft()['settings']['source'].endswith('// reviewed version\n')
            window.apply_inputs();wait(lambda:not window._busy,app)
        else:
            assert window.edited_draft()['settings']['source']==draft['settings']['source']
            assert not window.local_dirty
        current=client.document_read(doc['id'])
        assert current['draft']['settings']['properties'][0]['value']==2e9
        assert not service[0].manager.list()
    finally:
        window._allow_close=True;window.close();QThreadPool.globalInstance().waitForDone(5000);app.processEvents()



def test_declared_numeric_repair_after_invalid_saved_text_and_new_owner(service,app):
    from copy import deepcopy
    from caelab.workbench import Workbench
    from caelab.dimensioned_models import ODE,WEAK,default_settings
    from caelab.user_material import default_settings as law_settings
    from apps.research.pde_window import PDEWindow,at_path,set_path,display,typed_value
    from apps.research.native_material_window import NativeMaterialWindow
    models=[
        (ODE,default_settings(ODE),[('states',0,'initial'),('states',0,'atol'),('parameters',0,'value'),
            ('time','start'),('time','end'),('time','samples'),('solver','rtol'),('solver','max_step')]),
        (WEAK,default_settings(WEAK),[('domain','width'),('domain','height'),('parameters',0,'value'),
            ('space','degree'),('mesh','levels',0),('solver','residual_relative')]),
        ('material.mfront.user',law_settings(),[('properties',0,'value'),('external',0,'value'),
            ('history',1,'time'),('history',1,'strain',3),('probe','increment'),('probe','steps',0)])]
    models[-1][1]['action']='evaluate'
    wb,client=service;saved=[]
    for backend,settings,paths in models:
        original={'backend':backend,'settings':settings};draft=deepcopy(original)
        for path in paths:set_path(draft,('settings',)+path,'1e')
        kind='material' if backend.startswith('material.') else 'pde'
        doc=client.document_open(kind=kind,draft=draft)
        saved.append((change(client,doc,'document.save')['document'],original,paths,kind))
    assert not wb.manager.list()
    assert wb.shutdown()['joined']
    fresh=Workbench(wb.workspace)
    try:
        for saved_doc,original,paths,kind in saved:
            opened=fresh.document_open(kind=kind,document_id=saved_doc['id'])
            assert opened['draft']==saved_doc['draft']
            cls=NativeMaterialWindow if kind=='material' else PDEWindow
            window=cls(fresh,auto_open=False,poll_interval=0);window._opened(opened);window.show()
            try:
                for short_path in paths:
                    path=('settings',)+short_path
                    node=next(window._nodes[path[:i]] for i in range(len(path),0,-1) if path[:i] in window._nodes)
                    window.tree.setCurrentItem(node);app.processEvents()
                    control=window.fields[path][0];assert control.text()=='1e'
                    text=display(at_path(original,path));control.setText(text);control.textEdited.emit(text)
                assert window.edited_draft()==original
                for short_path in paths:
                    if type(at_path(original,('settings',)+short_path)) is int:
                        assert type(at_path(window.edited_draft(),('settings',)+short_path)) is int
                window.apply_inputs();wait(lambda:not window._busy,app)
                assert window.document['draft']==original and not window.document['diagnostics']
                window.command('document.undo');wait(lambda:not window._busy,app)
                assert window.document['draft']==saved_doc['draft']
                window.command('document.redo');wait(lambda:not window._busy,app)
                window.save_document();wait(lambda:not window._busy,app)
                assert fresh.document_read(opened['id'])['draft']==original
                assert not fresh.manager.list()
            finally:
                window._allow_close=True;window.close();QThreadPool.globalInstance().waitForDone(5000);app.processEvents()
    finally:fresh.shutdown()
    assert typed_value('2.5','1e',('settings','time','samples'),ODE)==2.5
    assert typed_value('1e','1e',('settings','mesh','levels',0),WEAK)=='1e'
    assert typed_value('2e-6','1e',('settings','initial_internal',0),'material.mfront.user')==2e-6
    for backend,path in [(ODE,('states',0,'rhs')),(ODE,('parameters',0,'unit')),
                         (WEAK,('boundaries',0,'expression')),('material.mfront.user',('source',)),
                         (ODE,('custom','value'))]:
        assert typed_value('2','1e',('settings',)+path,backend)=='2'



@pytest.mark.parametrize('accept',[False,True])
def test_built_declarations_prepare_inputs_cancel_or_save_without_evaluation(service,app,monkeypatch,accept):
    from copy import deepcopy
    from PySide6.QtWidgets import QDialog
    from caelab import user_material as domain
    from caelab.adapters.user_mfront import UserMFrontAdapter
    from apps.research.material_law_inputs_dialog import MaterialLawInputsDialog
    from apps.research.native_material_window import NativeMaterialWindow
    settings=domain.default_settings();calls=[]
    descriptor={'behaviour':settings['behaviour'],
        'material_properties':[{'name':'YoungModulus','size':1},{'name':'NewCoefficient','size':1}],
        'external_state_variables':[{'name':'Temperature','size':1}],
        'internal_state_variables':[{'name':'memory','size':1}]}
    build={'source_sha256':domain.source_hash(settings['source']),'descriptor':descriptor}
    def controlled_build(self,settings,*,output,runtime=None):
        calls.append(settings['action'])
        return {'execution_status':'SUCCEEDED','responses':{},'checks':[],
            'diagnostics':{'build':deepcopy(build),'constitutive':{'steps':[],'status':'BUILT_ONLY'},
                'scope':'CONTROLLED compiled descriptor boundary, no native compiler'}}
    monkeypatch.setattr(UserMFrontAdapter,'run',controlled_build)
    wb,client=service;draft={'backend':domain.BACKEND,'settings':settings}
    doc=client.document_open(kind='material',draft=draft)
    job=change(client,doc,'material.evaluate')['job']['id']
    wait(lambda:client.status(job)['state'] in TERMINAL,app)
    window=NativeMaterialWindow(client,document_id=doc['id'],poll_interval=0);window.show()
    try:
        wait(lambda:window.document and not window._busy and window._result,app)
        def review(dialog):
            assert dialog.tables['properties'].item(1,1).text()==''
            assert dialog.tables['properties'].item(1,2).text()=='' # no guessed unit
            dialog.tables['properties'].item(1,1).setText('2.5')
            dialog.tables['properties'].item(1,2).setText('1')
            dialog.tables['initial_internal'].item(0,1).setText('0.15')
            return QDialog.DialogCode.Accepted if accept else QDialog.DialogCode.Rejected
        monkeypatch.setattr(MaterialLawInputsDialog,'exec',review)
        window.prepare_law_inputs();wait(lambda:not window._busy,app)
        current=window.edited_draft()
        if accept:
            assert current['settings']['properties'][0]==settings['properties'][0]
            assert current['settings']['properties'][1]=={'name':'NewCoefficient','value':2.5,'unit':'1'}
            assert current['settings']['initial_internal']==[.15] and current['settings']['action']=='evaluate'
            window.save_document();wait(lambda:not window._busy and not window.local_dirty,app)
            reopened=client.document_open(kind='material',document_id=doc['id'])
            assert reopened['draft']==current
        else:assert current==draft and not window.local_dirty
        assert calls==['build'] and len(wb.manager.list())==1
    finally:
        window._allow_close=True;window.close();QThreadPool.globalInstance().waitForDone(5000);app.processEvents()


def test_constitutive_physical_tensor_and_signed_probe_read_only(service,app):
    pytest.importorskip('felupe')
    from copy import deepcopy
    from caelab.material_document import default_draft
    from apps.research.constitutive_inspection_window import ConstitutiveInspectionWindow,selected_probes
    wb,client=service;draft=default_draft()
    draft['settings'].update(model='neo_hooke',parameters={'mu':30.,'lmbda':50.},
        tangent_probe={'increment':1,'input_component':'xy','steps':[1e-6]})
    draft['settings']['deformation_gradient'][1]=[[1.08,.12,0.],[.03,.98,0.],[0.,0.,1.02]]
    doc=client.document_open(kind='material',draft=draft)
    job=change(client,doc,'material.evaluate')['job']['id']
    wait(lambda:client.status(job)['state'] in TERMINAL,app)
    window=ConstitutiveInspectionWindow(client,doc['id'],job);window.resize(1100,780);window.show()
    try:
        wait(lambda:window._data is not None,app)
        window.increment.setCurrentIndex(window.increment.findData(1))
        wait(lambda:window._data is not None and window._data['increment']==1,app)
        assert window.stress.rowCount()==18 and window.tabs.tabText(0)=='변형과 응력'
        assert any(window.stress.item(i,1).text()=='yx' and window.stress.item(i,4).text()=='제1 Piola'
                   for i in range(window.stress.rowCount()))
        window.tangent.setCurrentCell(3,1);app.processEvents()
        assert window.probes.rowCount()==1 and window.probe_states.topLevelItemCount()==2
        assert window._fd_rows[0]['minus_input'] is not None and window._fd_rows[0]['plus_stress'] is not None
        assert window.size().width()==1100 and window.size().height()==780
        assert window.canvas.width()>=420 and len(wb.manager.list())==1
        # Explicit recorded native-order test double. SVK yx column is index4,
        # not FELUPE's index3; no actual native invocation here.
        names=['xx','yy','zz','xy','yx','xz','zx','yz','zy']
        native={'backend':'material.mfront.hyperelastic','increment':0,'components':names,
            'finite_differences':[{'h':.001,'pk1_tangent_mpa':[[i*10+j for j in range(9)] for i in range(9)],
                'probes':[{'column':4,'sign':sign,'deformation_gradient':list(range(9)),
                    'pk1_stress_mpa':list(range(10,19)),'initial_state':{'same':'baseline'}}
                    for sign in (-1,1)]}]}
        selected=selected_probes(native,3,4)[0]
        assert selected['minus_input']==4 and selected['plus_stress']==13 and selected['difference']==34
    finally:
        window.close();QThreadPool.globalInstance().waitForDone(5000);app.processEvents()
