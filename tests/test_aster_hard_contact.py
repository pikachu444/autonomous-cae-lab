"""Controlled input/reader contracts; these tests never claim native physics."""
from copy import deepcopy
import json,hashlib
from types import SimpleNamespace as NS
import pytest
from test_contact_execution import model
from caelab.adapters import contact_aster_model as domain,contact_aster_worker as worker,contact_aster_results as reader
from caelab.storage import save_json

@pytest.fixture
def hard(model):
    model=deepcopy(model);model['backend']=domain.BACKEND
    model['native_to_deck_slots']={k:list(v) for k,v in domain.SLOTS.items()}
    model['contacts'][0]['draft'].update(normal_law='hard',sliding='small',normal_stiffness_MPa_per_mm='',stick_stiffness_MPa_per_mm='')
    model['step']['geometry']='linear';model['source_bodies']=[{'body_id':k,'target':{'fixture':'CONTROLLED'}} for k in model['body_maps']]
    return model

def freeze(folder,model):
    folder.mkdir();(folder/'editable.FCStd').write_bytes(b'CONTROLLED_NOT_NATIVE')
    save_json(folder/'mesh.json',model)
    (folder/'mesh.mail').write_text(worker.mesh_text(model)[0],encoding='ascii',newline='\n')
    (folder/'model.comm').write_text(worker.command_text(),encoding='ascii',newline='\n')
    save_json(folder/'snapshot.json',dict(kind='freecad-contact-frozen',schema_version='1',id='Fhard',backend=domain.BACKEND,
        input_file='model.comm',bodies=model['source_bodies'],files=[dict(relative=p.name,bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest()) for p in sorted(folder.iterdir())]))
    return folder/'snapshot.json'

def native_fixture(model):
    _,labels,catalog=worker.mesh_text(model);ids=sorted(labels);orders=[1,2]
    def table(nodes,components,order):
        return dict(NOEUD=[str(ids.index(n)+1) for n in nodes],NUME_ORDRE=[order]*len(nodes),
            **{k:[0. for n in nodes] for k in components})
    steps=[]
    for order in orders:
        pairs={}
        for p in model['contacts']:
            slave=sorted(domain.surface_nodes(model,p['a']))
            pairs[p['object_id']]={
                'CONT_NOEU':table(slave,worker.CONTACT_COMPONENTS,order),
                'MULTIPLIERS':table(slave,worker.MULTIPLIERS if p['draft']['tangential_law']=='coulomb' else ('LAGS_C',),order)}
        steps.append(dict(order=order,fields={k:table(ids,worker.DISPLACEMENT,order) for k in ('DEPL','REAC_NODA')},pairs=pairs))
    return dict(solver_status='COMPLETED',converged=True,source_commit=domain.SOURCE,versions={'code_aster':'17.4.0'},
        native_mesh_checks=dict(status='PASS',node_ids_in_native_order=ids),available_orders=orders,
        access_parameters=dict(NUME_ORDRE=orders,INST=[.5,1.]),tables=steps),catalog

def test_hard_is_not_a_penalty_substitution_and_same_coordinates_stay_distinct(hard):
    nodes,elements,bodies,quality=domain.validate_model(hard)
    assert len(bodies)==2 and not set(elements[1])&set(elements[2]) and quality['tetra10']
    text,_,catalog=worker.mesh_text(hard)
    assert 'TRIA6' in text and catalog['pairs']['Contact']['slave_node_ids']==sorted(domain.surface_nodes(hard,hard['contacts'][0]['a']))
    from caelab.contact_deck import validate_model
    with pytest.raises(ValueError):validate_model(hard)
    for key,value in [('normal_stiffness_MPa_per_mm','1e20'),('sliding','surface_to_surface'),('friction_coefficient','1e')]:
        draft=deepcopy(hard['contacts'][0]['draft']);draft[key]=value
        assert any(r['path']==key for r in domain.law_errors(draft))
        assert draft[key]==value

def test_hexa8_native_order_faces_quality_and_inversion(hard):
    bodies=[]
    cube=[(0,0,0),(1,0,0),(1,1,0),(0,1,0),(0,0,1),(1,0,1),(1,1,1),(0,1,1)]
    slots=domain.SLOTS['C3D8']
    for name,offset in [('Pad',0),('Base',2)]:
        native=[None]*8
        for i,j in enumerate(slots):native[j]=cube[i]
        bodies.append(dict(body_id=name,nodes=[dict(node_id=i+1,position_mm=[x,y,z+offset]) for i,(x,y,z) in enumerate(native)],
            elements=[dict(element_id=73,type='C3D8',native_node_ids=list(range(1,9)))]))
    mapped=domain.assemble(bodies);hard.update(mapped)
    for n in hard['nodes']:n['native_position_mm']=list(n['position_mm'])
    for side,name in [('a','Pad'),('b','Base')]:
        hard['contacts'][0][side]=domain.surface_union(name,[dict(face='Face6',element_faces=[[73,6]])],hard['body_maps'])
    hard['boundary_dofs']=[dict(node_id=9,component=i,value_mm=0.) for i in (1,2,3)]
    hard['loads']=[dict(node_id=1,component=3,force_N=-1.)]
    assert len(domain.validate_model(hard)[3]['hexa8'])==2
    assert 'HEXA8' in worker.mesh_text(hard)[0] and 'QUAD4' in worker.mesh_text(hard)[0]
    for n in hard['nodes']:n['position_mm'][0]*=-1;n['native_position_mm'][0]*=-1
    with pytest.raises(ValueError,match='Jacobian'):domain.validate_model(hard)

def test_native_import_uses_labels_not_coincident_coordinate_matching(hard):
    _,labels,catalog=worker.mesh_text(hard);names=list(catalog['nodes']);cells=list(catalog['cells'])
    mesh=NS(getNumberOfNodes=lambda:len(names),getNumberOfCells=lambda:len(cells),getNodes=lambda:range(len(names)),
        getCoordinates=lambda:NS(toNumpy=lambda:NS(tolist=lambda:[catalog['nodes'][n]['xyz'] for n in names])),
        getNodeName=lambda i:names[i],getCellName=lambda i:cells[i],getCellTypeName=lambda i:catalog['cells'][cells[i]]['type'],
        getConnectivity=lambda:[[names.index(n) for n in catalog['cells'][c]['nodes']] for c in cells],
        getCells=lambda group:[cells.index(c) for c in catalog['groups'][group]])
    assert worker.capture_import(mesh,catalog)['node_ids_in_native_order']==sorted(labels)
    mesh.getNodeName=lambda i:names[0]
    with pytest.raises(ValueError):worker.capture_import(mesh,catalog)


@pytest.mark.parametrize('friction', ['frictionless', 'coulomb'])
def test_user_mesh_ids_names_dimensions_and_load_interval_reach_native_input(hard, friction):
    """User inputs, rather than validation-case identities, determine the deck."""
    body_names = {'Pad': 'MovingTool42', 'Base': 'Housing07'}
    nodes = {r['node_id']: 400 + 7*r['node_id'] for r in hard['nodes']}
    elements = {r['element_id']: 800 + 11*r['element_id'] for r in hard['elements']}
    for row in hard['nodes']:
        row['node_id'] = nodes[row['node_id']]
        row['body_id'] = body_names[row['body_id']]
        row['position_mm'] = [2.5*v+t for v,t in zip(row['position_mm'], [17., -8., 4.])]
        row['native_position_mm'] = list(row['position_mm'])
    for row in hard['elements']:
        row['element_id'] = elements[row['element_id']]
        row['body_id'] = body_names[row['body_id']]
        row['node_ids'] = [nodes[n] for n in row['node_ids']]
    hard['body_maps'] = {
        body_names[name]: {'nodes': {n: nodes[v] for n,v in mapping['nodes'].items()},
                           'elements': {e: elements[v] for e,v in mapping['elements'].items()}}
        for name,mapping in hard['body_maps'].items()}
    for material in hard['materials']:
        material.update(body_id=body_names[material['body_id']], young_modulus_MPa=18750.)
    for source in hard['source_bodies']:
        source['body_id'] = body_names[source['body_id']]
    for row in hard['boundary_dofs'] + hard['loads']:
        row['node_id'] = nodes[row['node_id']]
        if 'force_N' in row:
            row['force_N'] = -37.5
    pair = hard['contacts'][0]
    pair['object_id'] = 'ToolHousingContact29'
    pair['draft'].update(label='공구와 하우징', tangential_law=friction,
                         friction_coefficient='.37' if friction == 'coulomb' else '')
    for side in ('a', 'b'):
        surface = pair[side]
        surface['body_id'] = body_names[surface['body_id']]
        surface['element_faces'] = [[elements[e],f] for e,f in surface['element_faces']]
        for face in surface['cad_faces']:
            face['element_faces'] = [[elements[e],f] for e,f in face['element_faces']]
    hard['step'].update(period=7.25, initial=.25, maximum=.5)
    domain.validate_model(hard)
    text,labels,catalog = worker.mesh_text(hard)
    assert set(catalog['pairs']) == {'ToolHousingContact29'}
    assert set(labels) == set(nodes.values())
    assert 'N407 ' in text and 'M811 ' in text
    assert hard['loads'][0]['force_N'] == -37.5
    raw,_ = native_fixture(hard)
    raw['access_parameters']['INST'] = [2.4, 7.25]
    parsed = reader.parse(raw,hard,catalog)
    assert [s['load_parameter'] for s in parsed['steps']] == [2.4,7.25]
    assert set(parsed['steps'][0]['pairs']) == {'ToolHousingContact29'}
    assert set(parsed['steps'][0]['fields']['DEPL']) == {str(n) for n in nodes.values()}

def test_missing_native_contact_values_are_unknown_and_wrong_pair_order_rejected(hard):
    raw,catalog=native_fixture(hard)
    raw['tables'][0]['pairs']['Contact']['CONT_NOEU']['JEU'][0]=None
    parsed=reader.parse(raw,hard,catalog)
    first=str(parsed['steps'][0]['pairs']['Contact']['nodes'][0])
    assert parsed['steps'][0]['pairs']['Contact']['values'][first]['JEU']is None
    assert parsed['axis']['unit']=='1' and reader.UNITS['LAGS_F1']=='1' and reader.UNITS['RNX']=='N'
    raw['tables'][0]['pairs']['Contact']['CONT_NOEU']['NUME_ORDRE'][0]=2
    with pytest.raises(ValueError,match='order'):reader.parse(raw,hard,catalog)


def test_pair_wrench_sums_only_native_slave_forces_and_shifts_reference(hard,tmp_path,monkeypatch):
    from caelab.contact_resultants import project, selection
    raw,catalog = native_fixture(hard)
    table = raw['tables'][0]['pairs']['Contact']['CONT_NOEU']
    loads = [(2.,0.,-3., .5,-1.,0., -.25,.75,0.),
             (-1.,4.,2., 0.,.5,.25, 0.,-.5,.75)]
    channels = ('RNX','RNY','RNZ','RTAX','RTAY','RTAZ','RTGX','RTGY','RTGZ')
    for index,values in enumerate(loads):
        for key,value in zip(channels,values):
            table[key][index] = value
    # A pressure/direction multiplier must never enter a force sum.
    for key in worker.MULTIPLIERS:
        raw['tables'][0]['pairs']['Contact']['MULTIPLIERS'][key] = [1e6]*len(table['CONT'])
    parsed = reader.parse(raw,hard,catalog)
    save_json(tmp_path/'contact_fields.json',parsed)
    receipt = dict(artifacts=[],execution_status='SUCCEEDED')
    monkeypatch.setattr(reader,'context',lambda out:(receipt,hard,parsed))
    descriptors = reader.catalog({},tmp_path)
    assert descriptors['Contact.CF_MX']['value_origin'] == 'DERIVED_SUM_NATIVE_NODAL_FORCES'
    assert descriptors['Contact.RNX']['source']['value_origin'] == 'NATIVE'
    history = reader.read({},tmp_path,'Contact.CF_FX')
    assert history['value'] == [1.25,0.]
    assert history['valid_mask'] == [True,True]
    assert reader.read({},tmp_path,'Contact.CF_MX',stop=1)['value'] == [.9375]
    with pytest.raises(ValueError):
        reader.read({},tmp_path,'Contact.CF_MX@1')
    total = reader.pair_resultant(hard,parsed,'Contact',1)
    assert total['force_N'] == pytest.approx([1.25,3.75,0.])
    assert total['moment_origin_Nmm'] == pytest.approx([.9375,2.6875,-.25])
    assert reader.pair_resultant(hard,parsed,'Contact',1,'CFN')['force_N'] == [1.,4.,-1.]
    assert reader.pair_resultant(hard,parsed,'Contact',1,'CFS')['force_N'] == [.25,-.25,1.]
    assert total['force_on'] == 'slave_A' and total['moment_configuration'] == 'REFERENCE'
    assert total['value_origin'] == 'DERIVED_SUM_NATIVE_NODAL_FORCES'
    spec = selection(dict(response='moment',side='a',reference_point_mm=[2.,-1.,3.],
                          basis_rows=[[1.,0.,0.],[0.,1.,0.],[0.,0.,1.]],frame_label='전역 좌표계'))
    shifted = [project(total,spec,c)[0] for c in range(3)]
    assert shifted == pytest.approx([12.1875,-1.0625,-9.])
    table['RNX'][0] = None
    missing = reader.pair_resultant(hard,reader.parse(raw,hard,catalog),'Contact',1)
    assert missing['status'] == 'UNKNOWN'
    assert missing['force_N'] == [None,3.75,0.]
    assert missing['moment_origin_Nmm'] == [.9375,None,-.25]
    assert project(missing,{**spec,'response':'force'},1) == (3.75,None)
    table['CONT'][0] = -1.
    unpaired = reader.pair_resultant(hard,reader.parse(raw,hard,catalog),'Contact',1)
    assert unpaired['force_N'] == [None,None,None]
    assert unpaired['moment_origin_Nmm'] == [None,None,None]
    assert table['CONT'][0] == -1. and table['RNY'][0] == 0.
    with pytest.raises(ValueError):
        reader.pair_resultant(hard,parsed,'Contact',99)

def test_snapshot_file_tamper_and_public_server_paths_rejected(hard,tmp_path,monkeypatch):
    source=freeze(tmp_path/'input',hard)
    assert domain.validate_snapshot(source)[1]==json.loads(json.dumps(hard))
    (source.parent/'mesh.mail').write_bytes(b'wrong')
    with pytest.raises(ValueError,match='보존본'):domain.validate_snapshot(source)
    adapter=domain.ContactCodeAsterAdapter()
    monkeypatch.setattr('pathlib.Path.read_bytes',lambda p:(_ for _ in ()).throw(AssertionError('PUBLIC PATH READ')))
    with pytest.raises(ValueError,match='서버 파일'):adapter.validate_settings({'snapshot_path':'C:/private','data_id':'Dsafe'})
    assert adapter.describe_ports({'data_id':'Dsafe'})['clock']=='STATIC_LOAD_PARAMETER'

def test_runtime_absence_preserves_prepared_input_and_no_native_claim(hard,tmp_path,monkeypatch):
    source=freeze(tmp_path/'input',hard);monkeypatch.delenv('CAELAB_CODEASTER_IMAGE_SHA256',raising=False)
    result=domain.ContactCodeAsterAdapter().run({'data_id':'Dhard','snapshot_path':str(source)},output=tmp_path/'out')
    assert result['execution_status']=='REJECTED' and result['solver_status']=='NOT_RUN'
    assert (tmp_path/'out/solver/mesh.mail').is_file() and (tmp_path/'out/frozen_input/editable.FCStd').is_file()
    assert 'native_channels'not in result and result['qualification']=='UNKNOWN'

def test_registered_input_simulation_save_cold_and_retained_native_selection(hard,tmp_path,monkeypatch):
    from caelab.workbench import Workbench
    from caelab.native_inputs import register_frozen_input
    from caelab.adapters import codeaster_frozen
    source=freeze(tmp_path/'input',hard);raw,catalog=native_fixture(hard)
    # Explicit controlled native callback. No solver is run or physics claimed.
    def execute(out,budgets):
        config=json.loads((out/'solver/input.json').read_text(encoding='utf-8'))
        raw.update(input_sha256=hashlib.sha256((out/'solver/input.json').read_bytes()).hexdigest(),mail_sha256=config['mail_sha256'])
        save_json(out/'solver/worker_result.json',raw);save_json(out/'solver/native_mesh_checks.json',raw['native_mesh_checks'])
        (out/'solver/results.med').write_bytes(b'CONTROLLED_NOT_NATIVE_MED')
        return {'test_double':True}
    monkeypatch.setattr(codeaster_frozen,'execute_native',execute)
    from caelab.adapters.codeaster_contact import _IMAGE_SHA
    monkeypatch.setenv('CAELAB_CODEASTER_IMAGE_SHA256',_IMAGE_SHA)
    wb=Workbench(tmp_path/'workspace')
    try:
        receipt=register_frozen_input(wb.root,tmp_path/'input',source,'Dhard',root_id='public-fixture',relative='snapshot.json',limit=10**7)
        settings={'data_id':receipt['id'],'snapshot_path':str(wb.input_path('Dhard'))}
        result=domain.ContactCodeAsterAdapter().run(settings,output=tmp_path/'result')
        assert result['execution_status']=='SUCCEEDED',result.get('diagnostics')
        channel=reader.read(result,tmp_path/'result','Contact.JEU@1')
        assert channel['axes'][0]['values']==[.5,1.] and channel['value']==[0.,0.]
        document=wb.document_open(kind='simulation',title='공개 접촉 제어 검사',draft={'backend':domain.BACKEND,'settings':{'data_id':receipt['id']}})
        import time,subprocess,sys
        def command(doc,operation):
            return wb.document_command(doc['id'],operation,{},session_id=doc['session_id'],expected_generation=doc['generation'])
        reply=command(document,'simulation.evaluate');document=reply['document'];jobid=reply['job']['id']
        deadline=time.monotonic()+10
        while time.monotonic()<deadline:
            job=wb.manager.status(jobid)
            if job['state']in ('SUCCEEDED','FAILED','CANCELLED','REJECTED'):break
            time.sleep(.02)
        assert job['state']=='SUCCEEDED',job
        selected=wb.document_result(document['id'],jobid,selection={'responses':['Contact.JEU@1','Contact.LAGS_C@1','Contact.CF_FX','Contact.CF_MZ']})
        assert selected['responses']['Contact.JEU@1']['value']==[0.,0.]
        assert selected['responses']['Contact.CF_FX']['value']==[0.,0.]
        document=command(document,'document.save')['document'];document_id=document['id']
        from caelab.storage import canonical_hash
        expected=canonical_hash(wb.document_result(document_id,jobid,selection={'responses':['Contact.JEU@1','Contact.LAGS_C@1','Contact.CF_FX','Contact.CF_MZ']}))
        count=len(wb.manager.list())
    finally:wb.shutdown()
    program='''
import sys
from pathlib import Path
sys.path.insert(0,sys.argv[1])
from caelab.workbench import Workbench
from caelab.storage import canonical_hash
from caelab.adapters.contact_aster_model import ContactCodeAsterAdapter
ContactCodeAsterAdapter.run=lambda *a,**k:(_ for _ in ()).throw(AssertionError('COLD MUST NOT RUN'))
wb=Workbench(sys.argv[2])
try:
 d=wb.document_open(kind='simulation',document_id=sys.argv[3])
 r=wb.document_result(d['id'],sys.argv[4],selection={'responses':['Contact.JEU@1','Contact.LAGS_C@1','Contact.CF_FX','Contact.CF_MZ']})
 assert canonical_hash(r)==sys.argv[5]
 assert len(wb.manager.list())==int(sys.argv[6])
 print('COLD_SELECTION_IDENTICAL_NEW_JOBS_ZERO')
finally:wb.shutdown()
'''
    cold=subprocess.run([sys.executable,'-X','utf8','-c',program,str(__import__('pathlib').Path(__file__).resolve().parents[1]),str(tmp_path/'workspace'),document_id,jobid,expected,str(count)],capture_output=True,text=True,timeout=15)
    assert cold.returncode==0,cold.stdout+cold.stderr


def _owned_freecad_check(tmp_path, program, *arguments):
    """Explicit opt-in: isolated installed FreeCAD Python/Qt, never a solver."""
    import os, subprocess
    from pathlib import Path
    executable = os.environ.get('CAELAB_TEST_FREECAD_PYTHON')
    if not executable:
        pytest.skip('Set CAELAB_TEST_FREECAD_PYTHON for the assigned native UI check')
    assert Path(executable).is_file()
    environment = dict(os.environ, QT_QPA_PLATFORM='offscreen', PYTHONUTF8='1')
    process = None
    try:
        process = subprocess.Popen([executable, '-X', 'utf8', '-c', program,
            str(Path(__file__).resolve().parents[1]), *map(str, arguments)],
            env=environment, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, encoding='utf-8', errors='replace',
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        stdout, stderr = process.communicate(timeout=30)
        assert process.returncode == 0, stdout + stderr
        return stdout
    finally:
        if process is not None and process.poll() is None:
            process.terminate()
            try: process.communicate(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill(); process.communicate(timeout=5)


def test_actual_connection_run_routes_user_hard_and_existing_ccx_without_solving(tmp_path):
    result = _owned_freecad_check(tmp_path, r'''
import sys
sys.path.insert(0,sys.argv[1])
from copy import deepcopy
from types import SimpleNamespace as NS
import FreeCAD as App, ObjectsFem
from PySide import QtWidgets as W
from apps.desktop_pre.connection import Connection
application=W.QApplication.instance() or W.QApplication([])
assert not App.listDocuments()
doc=App.newDocument('HousingAssembly729')
try:
 analysis=ObjectsFem.makeAnalysis(doc,'SeparationStudy84')
 solver=ObjectsFem.makeSolverCalculiXCcxTools(doc,'NativeSettings27')
 analysis.addObject(solver)
 contact=ObjectsFem.makeConstraintContact(doc,'HousingToolPair62')
 analysis.addObject(contact)
 # FreeCAD's console runtime has no Gui module; control only its selection
 # accessor while retaining actual native document/analysis/solver objects.
 sys.modules['FemGui']=NS(getActiveAnalysis=lambda:analysis)
 metadata={'contacts':[{'analysis_id':analysis.Name,'object_id':contact.Name,
                       'draft':{'normal_law':'hard'}}]}
 before=deepcopy(metadata);sent=[];refreshed=[]
 owner=NS(doc=doc,document_id='PUser729',session_id='SUser729',generation=73,
          read_metadata=lambda:deepcopy(metadata),refresh=lambda:refreshed.append(True))
 connection=Connection.__new__(Connection)
 connection.App=App;connection.owners={doc.Name:(owner,None,None)}
 connection.panels={};connection.pending=None;connection.message=W.QLabel()
 connection.send_command=lambda:sent.append(deepcopy(connection.pending))
 def check(operation,export_only):
  connection.pending=None
  connection.run(export_only=export_only)
  assert connection.pending is not None,connection.message.text()
  request=sent[-1]
  assert request['operation']==operation,request
  assert request['arguments']=={'analysis_id':analysis.Name,'solver_id':solver.Name}
  assert request['document_id']==owner.document_id and request['generation']==73
  assert request['export_only'] is export_only
 for export_only in (False,True):check('pre.contact.aster_freeze',export_only)
 assert metadata==before
 # A hard law from another user analysis must not select the Aster writer.
 metadata['contacts'][0]['analysis_id']='OtherStudy963'
 for export_only in (False,True):check('pre.contact.freeze',export_only)
 metadata['contacts'][0].update(analysis_id=analysis.Name,draft={'normal_law':'penalty'})
 for export_only in (False,True):check('pre.contact.freeze',export_only)
 analysis.removeObject(contact);metadata.clear()
 for export_only in (False,True):check('pre.freeze',export_only)
 assert len(sent)==len(refreshed)==8
 print('ACTUAL_CONNECTION_USER_HARD_AND_CCX_ROUTES_NO_SOLVER')
finally:
 App.closeDocument(doc.Name)
 assert not App.listDocuments()
 for widget in application.topLevelWidgets():widget.close()
 application.processEvents()
''')
    assert 'ACTUAL_CONNECTION_USER_HARD_AND_CCX_ROUTES_NO_SOLVER' in result


def test_actual_qt_aster_input_read_export_tamper_rejection_and_close(hard,tmp_path):
    source=freeze(tmp_path/'user-input',hard)
    result=_owned_freecad_check(tmp_path,r'''
import sys,hashlib,json
from pathlib import Path
sys.path.insert(0,sys.argv[1])
import FreeCAD
from PySide import QtCore as C, QtWidgets as W
from apps.desktop_pre.contact_input_dialog import show_input
application=W.QApplication.instance() or W.QApplication([])
manifest=Path(sys.argv[2]);outside=Path(sys.argv[3]);errors=[];exports=[]
original={p.name:p.read_bytes() for p in manifest.parent.iterdir()}
original_picker=W.QFileDialog.getSaveFileName
def inspect():
 dialog=application.activeModalWidget()
 try:
  assert dialog is not None
  selector=dialog.findChild(W.QComboBox);text=dialog.findChild(W.QPlainTextEdit)
  assert text.isReadOnly() and selector.count()==2
  export=next(b for b in dialog.findChildren(W.QPushButton) if b.text()=='입력 사본 저장…')
  names=set()
  for index in range(selector.count()):
   selector.setCurrentIndex(index);application.processEvents()
   row=selector.currentData();name=row['relative'];names.add(name)
   assert text.toPlainText()==original[name].decode('ascii')
   assert hashlib.sha256(original[name]).hexdigest()==row['sha256']
   target=outside/name
   def choose(*args,target=target):
    assert args[-1]=='Code_Aster (*.comm *.mail)'
    return str(target),'Code_Aster (*.comm *.mail)'
   W.QFileDialog.getSaveFileName=choose
   export.click();assert target.read_bytes()==original[name];exports.append(name)
  assert names=={'model.comm','mesh.mail'}
  # Refuse writes into the retained input even when the user picks that path.
  W.QFileDialog.getSaveFileName=lambda *args:(str(manifest.parent/'copy.comm'),'')
  export.click();assert not (manifest.parent/'copy.comm').exists()
  assert any('보존 입력 밖' in label.text() for label in dialog.findChildren(W.QLabel))
  index=next(i for i in range(selector.count()) if selector.itemData(i)['relative']=='mesh.mail')
  (manifest.parent/'mesh.mail').write_bytes(b'changed after opening')
  selector.setCurrentIndex(1-index);selector.setCurrentIndex(index)
  assert text.toPlainText()==''
  assert any('보존 입력이 변경되었습니다' in label.text() for label in dialog.findChildren(W.QLabel))
  rejected=outside/'must-not-export.mail'
  W.QFileDialog.getSaveFileName=lambda *args:(str(rejected),'')
  export.click();assert not rejected.exists()
  next(b for b in dialog.findChildren(W.QPushButton) if b.text()=='닫기').click()
  assert not dialog.isVisible()
 except BaseException as error:
  errors.append(error)
  if dialog:dialog.reject()
C.QTimer.singleShot(0,inspect)
try:
 show_input(manifest,W,C)
 assert not errors,errors
 assert set(exports)=={'model.comm','mesh.mail'}
 # Reopening a changed retained input fails before displaying a dialog.
 try:show_input(manifest,W,C)
 except ValueError:pass
 else:raise AssertionError('Tampered retained input opened')
finally:
 W.QFileDialog.getSaveFileName=original_picker
 for name,raw in original.items():(manifest.parent/name).write_bytes(raw)
 for widget in application.topLevelWidgets():widget.close()
 application.processEvents()
assert all((manifest.parent/name).read_bytes()==raw for name,raw in original.items())
print('ACTUAL_QT_COMM_MAIL_EXPORTED_TAMPER_REJECTED_CLOSED_NO_SOLVER')
''',source,tmp_path)
    assert 'ACTUAL_QT_COMM_MAIL_EXPORTED_TAMPER_REJECTED_CLOSED_NO_SOLVER' in result
