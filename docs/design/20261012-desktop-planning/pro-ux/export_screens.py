"""Render editable SVG state views from the actual Qt planning prototype.

This invokes only local fixture edits and QPainter. No product command, native
host, solver, optimizer, provider, browser or network request is made.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=Path(__file__).parent/'screens')
    parser.add_argument('--state',action='append',help='Render only this catalog state; repeatable')
    parser.add_argument('--offscreen',action='store_true')
    parser.add_argument('--png-output',type=Path,help='Optional scratch PNG review output; SVG remains the deliverable')
    args=parser.parse_args()
    if args.offscreen:os.environ['QT_QPA_PLATFORM']='offscreen'
    from PySide6.QtCore import Qt,QPoint,QSize,QRect,QTimer
    from PySide6.QtGui import QPainter
    from PySide6.QtSvg import QSvgGenerator
    from PySide6.QtWidgets import QApplication,QDialog,QStatusBar,QLabel
    from prototype_state import ReviewSession,clone,HERE,atomic_json
    from qt_prototype import DesktopHub,STYLE,configure_application_fonts
    app=QApplication.instance() or QApplication([])
    font_policy=configure_application_fonts(app)
    app.setStyle('Fusion');app.setStyleSheet(STYLE)
    args.output.mkdir(parents=True,exist_ok=True)
    if args.png_output:args.png_output.mkdir(parents=True,exist_ok=True)
    catalog=json.loads((HERE/'screen_states.json').read_text(encoding='utf-8'))
    hashes={name:hashlib.sha256((HERE/name).read_bytes()).hexdigest() for name in ('qt_prototype.py','qt_widgets.py','prototype_state.py','export_screens.py','fixtures/methods.json','screen_states.json')}
    reports=[];errors=[]
    previous_hook=sys.excepthook
    sys.excepthook=lambda kind,value,trace:errors.append(str(value))
    def merge(target,patch):
        for key,value in patch.items():
            if isinstance(value,dict) and isinstance(target.get(key),dict):merge(target[key],value)
            else:target[key]=clone(value)
    def english(session):
        expert=session.doc('expert')
        for data in (expert['saved'],expert['draft']):
            data.update(question='How much fixture compliance enters the measured displacement?',topics=['Fixture stiffness','Contact and friction','Gauge location','Discriminating test'],roles=['Structures','Testing','Materials'])
            data['turns']=[{'id':'question-example','role':'User example','actual':False,'text':'Separate fixture bending from specimen extension using the same load step.','topic':'Fixture stiffness','reply_to':None,'evidence':[]}]
        for data in (session.doc('study')['saved'],session.doc('study')['draft']):
            data['question']=expert['draft']['question']
            for h,text in zip(data['hypotheses'],['Fixture bending dominates','Constitutive response dominates','Gauge location or zero offset dominates']):h['text']=text
        session.selected['topic']='Fixture stiffness'
    def method_attempt(hub,window):
        window.example_matrix();hub.session.save_document(window.key)
        frozen=hub.session.freeze(window.key);job=hub.session.create_attempt(frozen['id']);hub.session.job_event(job['id'],'result')
        return job['result']
    for state in catalog['states']:
        if args.state and state['id'] not in args.state:continue
        start=len(errors)
        with tempfile.TemporaryDirectory(prefix='caelab-svg-') as directory:
            session=ReviewSession(directory);english(session)
            if state.get('setup')=='material-repair':session.material_repair_scenario()
            if 'patch' in state:
                for field in ('saved','draft'):merge(session.doc(state['tool'])[field],state['patch'])
            hub=DesktopHub(session);window=hub.open(state['tool']);window.resize(1440,900);app.processEvents()
            setup=state.get('setup');group_id=None
            try:
                if setup in ('running','cancel'):
                    job=session.create_attempt(session.freeze('simulation')['id']);session.selected['job']=job['id']
                    session.job_event(job['id'],'running')
                    if setup=='cancel':session.job_event(job['id'],'cancel');session.job_event(job['id'],'disconnect')
                    window.refresh()
                elif setup=='data-selection':session.mask([f'A{i}' for i in range(78,86)]);window.refresh();window.curve_selected([f'A{i}' for i in range(78,86)])
                elif setup=='discussion-layout':
                    payload=clone(window.data)
                    for i,(role,topic,text) in enumerate([('Structures example','Fixture stiffness','Compare rigid and flexible fixtures at the same load.'),('Testing example','Gauge location','Use two tracked gauge points and the machine displacement.'),('Materials example','Discriminating test','Keep the material fixed in the first compliance comparison.')]):
                        payload['turns'].append({'id':'layout-'+str(i),'role':role,'actual':False,'topic':topic,'text':text,'reply_to':'question-example','evidence':[]})
                    session.change(window.key,payload,'Show authored speaker layout');window.refresh()
                elif setup=='method-result':
                    rid=method_attempt(hub,window);window=hub.open_result(rid);window.resize(1440,900)
                elif setup in ('followup','judgment'):
                    plan=session.doc('numerical')['draft'];plan['method']='DOE';plan['parent_key']='expert';plan['budget']=4
                    numerical=hub.open('numerical');rid=method_attempt(hub,numerical)
                    if setup=='followup':
                        window=hub.discuss_result(rid,'DOE / Design responses / d2')
                        session.append_reply('Does d2 still separate fixture bending from specimen strain when the gauge position changes?','Gauge location',None,'expert',[rid]);window.refresh()
                    else:
                        payload=clone(window.data);payload['evidence'].append({'ref':rid,'locator':'DOE / Design responses / d2','hypothesis':'H1','relation':'Support','synthetic':True})
                        payload['judgment']='Insufficient evidence';payload['reason']='The authored DOE suggests a discriminating test. A measured gauge result is still required.'
                        payload['next_research']='Measure fixture and specimen displacement at the same force.';session.change('study',payload,'Apply review judgment');window.refresh()
                elif setup=='report-source':
                    if state.get('evidence_locator'):
                        for side in ('saved','draft'):
                            session.doc('study')[side]['evidence'][0]['locator']=state['evidence_locator']
                    window.load_study()
                    if state.get('section'):
                        for row in range(window.section_list.count()):
                            if window.section_list.item(row).data(Qt.ItemDataRole.UserRole)==state['section']:
                                window.section_list.setCurrentRow(row);break
                elif setup=='acquisition-loss':
                    window.show_connection_loss()
                elif setup=='adoption-partial':
                    group=session.prepare_adoption('p19');group_id=group['id'];session.apply_owner(group_id,'cad');session.save_adoption_owner(group_id,'cad');session.apply_owner(group_id,'material')
                    try:session.save_adoption_owner(group_id,'material',fail=True)
                    except Exception as error:group['owners']['material']['error']=str(error)
                for action in state.get('actions',[]):
                    if action not in ('example_matrix','show_method_example','ode_example'):raise ValueError('Action is not in the export whitelist: '+action)
                    getattr(window,action)()
                if state.get('mode'):window.mode.setCurrentText(state['mode'])
                if state.get('node'):
                    root=window.tree.topLevelItem(0)
                    for index in range(root.childCount()):
                        if root.child(index).text(0)==state['node']:window.tree.setCurrentItem(root.child(index));break
                for name,index in state.get('tabs',{}).items():getattr(window,name).setCurrentIndex(index)
                for name,(row,col) in state.get('select',{}).items():getattr(window,name).setCurrentCell(row,col)
                if hasattr(window,'connection') and not callable(window.connection):
                    route=window.data.get('runtime_proposal',{}).get('route','Not configured')
                    window.connection.setText('Provider: '+('OAuth / unverified' if route=='Existing subscription OAuth' else 'Local / unverified' if route=='Existing local endpoint' else 'Unconfigured'))
                    for r,role in enumerate(window.data['roles']):
                        config=window.data.get('runtime_proposal',{});model=config.get('expert_models',{}).get(role,{}).get('model') or config.get('model') or 'Unconfigured'
                        window.roles_table.item(r,1).setText(model+' / unverified')
                    window.composer.setPlaceholderText('Question, reply, objection or next check')
                    for r,turn in enumerate(window.data['turns']):
                        label='User' if turn['actual'] else turn['role']+' [authored example]'
                        window.turns.item(r).setText(label+'\n'+turn['text']+'\n'+turn['topic'])
                if hasattr(window,'statusBar'):
                    window.statusBar().showMessage('')
                    for label in window.statusBar().findChildren(QLabel):label.setText('Planning prototype / synthetic illustration')
                app.processEvents()
                def save_view(dialog=None):
                    output=args.output/(state['id']+'.svg');generator=QSvgGenerator();generator.setFileName(str(output));generator.setSize(QSize(1440,900));generator.setViewBox(QRect(0,0,1440,900));generator.setResolution(96)
                    generator.setTitle(state['title']);generator.setDescription(state['task']+' | Native Qt planning prototype; synthetic illustration.')
                    painter=QPainter(generator);window.render(painter,QPoint(0,0))
                    if dialog and dialog is not window:
                        x=max(0,(1440-dialog.width())//2);y=max(0,(900-dialog.height())//2);dialog.render(painter,QPoint(x,y))
                    painter.end()
                    if args.png_output:
                        from PySide6.QtGui import QPixmap
                        pixmap=QPixmap(1440,900);pixmap.fill(Qt.GlobalColor.white);p=QPainter(pixmap);window.render(p,QPoint(0,0))
                        if dialog and dialog is not window:dialog.render(p,QPoint(max(0,(1440-dialog.width())//2),max(0,(900-dialog.height())//2)))
                        p.end();pixmap.save(str(args.png_output/(state['id']+'.png')))
                    # State recipe is already in the editable catalog; this records exact dimensions and source provenance.
                    reports.append({'id':state['id'],'svg':output.name,'viewport':[window.width(),window.height()],'dialog':[dialog.width(),dialog.height()] if dialog else None,'errors':errors[start:]})
                dialog_name=state.get('dialog')
                if dialog_name:
                    invocations={'models':window.configure_models if hasattr(window,'configure_models') else None,
                      'compare':window.compare if hasattr(window,'compare') else None,
                      'protocol':window.protocol_dialog if hasattr(window,'protocol_dialog') else None,
                      'diagnostics':window.input_diagnostics if hasattr(window,'input_diagnostics') else None,
                      'domain':window.open_geometry if hasattr(window,'open_geometry') else None,
                      'calibration':lambda:hub.calibration(window),
                      'adoption':lambda:hub.adoption_dialog(window,group_id)}
                    captured=[]
                    def capture():
                        modal=app.activeModalWidget()
                        if not modal:errors.append('Expected modal dialog was not visible');return
                        save_view(modal);captured.append(True);modal.reject()
                    QTimer.singleShot(100,capture);invocations[dialog_name]()
                    if not captured:raise RuntimeError('Dialog capture did not complete: '+dialog_name)
                else:save_view()
            except Exception as error:
                reports.append({'id':state['id'],'errors':[type(error).__name__+': '+str(error)]});print(state['id'],type(error).__name__,str(error))
            for doc in session.documents.values():doc['dirty']=False
            for widget in list(hub.result_dialogs.values())+list(hub.windows.values()):widget.close();widget.deleteLater()
            app.processEvents()
        print(state['id'],'rendered' if reports[-1].get('svg') else 'FAILED')
    sys.excepthook=previous_hook
    atomic_json(args.output/'render_manifest.json',{'format':'caelab-ux-svg-render/1','mode':'QT_OFFSCREEN' if args.offscreen else 'QT_RENDER','font_policy':font_policy,'source_sha256':hashes,'states':reports,'callback_errors':errors,'native_host_executed':False,'solver_executed':False,'provider_executed':False})
    if errors or any(r.get('errors') for r in reports):return 1
    return 0


if __name__=='__main__':raise SystemExit(main())
