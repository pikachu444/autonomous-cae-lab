"""Owned-process public roller-support delivery; every invocation uses a new directory.

Reuses the fixture adapter, native Gmsh/Tasks/writer, broker and JobManager.
This is a reproducible synthetic connection check, never engineering qualification.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import importlib.util
import json
import os
from pathlib import Path
import shutil
import sys
import threading
import time
import traceback
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')
    temporary.replace(path)


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def verify_retained_a(config, output):
    from caelab.evaluation import read_result
    from caelab.native_cad import sha
    prior = read(Path(config['resume_delivery'])/'delivery.json')
    identifier = next(row['value']['id'] for row in prior['stages'] if row['stage']=='job-A')
    root = Path(config['store'])/'workbench'
    result = read_result(root/'results'/identifier)
    assert result['execution_status']=='SUCCEEDED'
    files = []
    for row in result['artifacts']:
        path = root/'native'/identifier/row['relative']
        assert path.is_file() and path.stat().st_size==row['bytes'] and sha(path)==row['sha256'], path
        files.append({'relative':row['relative'],'sha256':row['sha256'],'bytes':row['bytes']})
    write(output,{'job_id':identifier,'solver_reexecuted':False,'result_hash_verified':True,'artifacts':files})


def wait(check, seconds=120):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        value = check()
        if value:
            return value
        time.sleep(.1)
    raise TimeoutError('Native delivery stage did not complete within its bound')


def source_stage(config):
    from caelab.adapters.fixture_freecad import FixtureFreeCADAdapter
    os.environ['FREECAD_CMD'] = config['freecad_cmd']
    answer = FixtureFreeCADAdapter(Path(config['store'])).create_sample('roller_support')
    write(Path(config['root']) / 'source.json', answer)


def native_stage(config, *, cold=False):
    """Runs inside actual FreeCAD GUI, on its main thread."""
    import FreeCAD as App
    import FreeCADGui as Gui
    from PySide import QtCore, QtGui
    from apps.desktop_pre import bridge
    out = Path(config['root'])
    report = {'engineering_valid': False, 'qualification': 'UNKNOWN', 'freecad_version': list(App.Version())}
    bindings = []

    def close():
        for owner, dispatcher, broker in bindings:
            broker.close()
            dispatcher.close()
        for name in list(App.listDocuments()):
            App.closeDocument(name)
        QtCore.QTimer.singleShot(100, QtCore.QCoreApplication.quit)

    try:
        if cold:
            from caelab.native_cad import unpack_project
            from apps.desktop_pre.projects import remember_open
            prior = read(out / 'native.json')
            project = Path(prior['project'])
            manifest, entry = unpack_project(project, out / 'cold-pre')
            doc = App.openDocument(str(entry))
            remember_open(doc, manifest, project)
            owner = bridge.Owner(doc, config['export_root'], App=App, Gui=Gui)
            report.update(success=True, document_id=owner.document_id,
                          force_N=float(doc.getObject('DeliveryForce').Force.getValueAs('N').Value),
                          project=str(project), links=owner.read_metadata().get('links'))
            assert report['force_N'] == 20
            owner.close()
            write(out / 'cold-pre.json', report)
            close()
            return
        source = read(out / 'source.json')
        if config.get('resume_project'):
            from caelab.native_cad import unpack_project
            from apps.desktop_pre.projects import remember_open
            manifest, entry = unpack_project(config['resume_project'],out/'resumed-pre')
            doc = App.openDocument(str(entry))
            remember_open(doc,manifest,config['resume_project'])
        else:
            doc = App.openDocument(str(out/'prepared.FCStd') if config.get('prepared_source') else str(Path(config['store']) / 'native_designs' / source['design'] / 'editable.FCStd'))
        spec = importlib.util.spec_from_file_location('delivery_upstream', ROOT / 'plugins/fixture_design/upstream/fixturelab/freecad_worker.py')
        worker = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(worker)
        solid = worker._final(doc, worker._registry(doc))
        assert solid.Shape.isValid() and len(solid.Shape.Solids) == 1
        tolerance = max(float(solid.Shape.getTolerance(1)), 1e-7)
        def near(a, b):
            return abs(a-b) <= tolerance
        bottom, saddle = [], []
        for index, face in enumerate(solid.Shape.Faces, 1):
            box, surface = face.BoundBox, face.Surface
            if near(box.ZMin, 0) and near(box.ZMax, 0):
                bottom.append('Face' + str(index))
            if (hasattr(surface, 'Radius') and near(surface.Radius, 4.15)
                    and abs(abs(surface.Axis.y)-1) <= tolerance
                    and near(surface.Center.x, 0) and near(surface.Center.z, 26)
                    and near(box.YMin, -20) and near(box.YMax, 20)
                    and near(box.ZMin, 21.85) and near(box.ZMax, 26)):
                saddle.append('Face' + str(index))
        if config.get('resume_project'):
            write(out/'resume-geometric-predicate.json', {'bottom':bottom,'saddle':saddle,
                'selection_policy':'Reuse exact saved condition references; native saved BRep/mesh binding gates remain authoritative'})
            bottom = list(doc.getObject('DeliveryFixed').References[0][1])
            saddle = list(doc.getObject('DeliveryForce').References[0][1])
        assert len(bottom) == len(saddle) == 1, (bottom, saddle)
        if config.get('prepared_source'):
            analysis, solver, fixed, force, mesh = [doc.getObject(name) for name in ('DeliveryAnalysis','DeliverySolver','DeliveryFixed','DeliveryForce','DeliveryMesh')]
            assert all((analysis,solver,fixed,force,mesh)) and mesh.Shape is solid
            assert float(force.Force.getValueAs('N').Value) == 10
            assert list(fixed.References[0][1]) == bottom and list(force.References[0][1]) == saddle
            vertical = [force.Direction[1][0]]
            import FemGui
            FemGui.setActiveAnalysis(analysis)
            doc.saveAs(str(out/'working.FCStd'))
            write(out/'native-progress.json', {'phase':'verified-mesh-reused'})
        else:
            import ObjectsFem
            import FemGui
            from femmesh.gmshtools import GmshTools
            analysis = ObjectsFem.makeAnalysis(doc, 'DeliveryAnalysis')
            solver = ObjectsFem.makeSolverCalculiXCcxTools(doc, 'DeliverySolver')
            solver.AnalysisType = 'static'
            solver.GeometricalNonlinearity = 'linear'
            solver.MaterialNonlinearity = 'linear'
            solver.ModelSpace = '3D'
            solver.SplitInputWriter = False
            analysis.addObject(solver)
            material = ObjectsFem.makeMaterialSolid(doc, 'DeliveryMaterial')
            material.Material = {'Name':'Synthetic connection material', 'YoungsModulus':'1000 MPa', 'PoissonRatio':'0.25'}
            analysis.addObject(material)
            fixed = ObjectsFem.makeConstraintFixed(doc, 'DeliveryFixed')
            fixed.References = [(solid, bottom)]
            analysis.addObject(fixed)
            force = ObjectsFem.makeConstraintForce(doc, 'DeliveryForce')
            force.References = [(solid, saddle)]
            force.Force = '10 N'
            force.EnableAmplitude = False
            vertical = []
            for index, edge in enumerate(solid.Shape.Edges, 1):
                if len(edge.Vertexes) == 2:
                    delta = edge.Vertexes[-1].Point - edge.Vertexes[0].Point
                    if abs(delta.z) > tolerance and near(delta.x, 0) and near(delta.y, 0):
                        vertical.append('Edge' + str(index))
            assert vertical, 'Global Z direction needs an actual straight vertical edge'
            force.Direction = (solid, [vertical[0]])
            doc.recompute()
            if force.DirectionVector.z > 0:
                force.Reversed = True
            doc.recompute()
            assert tuple(force.DirectionVector) == (0., 0., -1.), tuple(force.DirectionVector)
            analysis.addObject(force)
            mesh = ObjectsFem.makeMeshGmsh(doc, 'DeliveryMesh')
            mesh.Shape = solid
            mesh.CharacteristicLengthMax = 4
            mesh.CharacteristicLengthMin = 1
            mesh.ElementOrder = '2nd'
            # Native curved high-order optimization repairs the six inverted
            # elements observed in the retained unoptimized first attempt.
            mesh.HighOrderOptimize = 'Elastic+Optimization'
            analysis.addObject(mesh)
            FemGui.setActiveAnalysis(analysis)
            App.ParamGet('User parameter:BaseApp/Preferences/Mod/Fem/Gmsh').SetString('gmshBinaryPath', config['gmsh'])
            doc.recompute()
            tool = GmshTools(mesh)
            tool.create_mesh()
            assert mesh.FemMesh.Volumes, 'Native Gmsh did not produce a volume mesh'
            mesh_evidence = out/'native-mesh'
            mesh_evidence.mkdir()
            for name in ('temp_file_geo','temp_file_geometry','temp_file_mesh'):
                path = Path(getattr(tool,name))
                if path.is_file():
                    shutil.copy2(path, mesh_evidence/path.name)
            doc.recompute()
            doc.saveAs(str(out / 'working.FCStd'))
            write(out/'native-progress.json', {'phase':'mesh-created'})
        owner = bridge.Owner(doc, config['export_root'], App=App, Gui=Gui)
        write(out/'native-progress.json', {'phase':'owner-created'})
        for condition in (fixed, force):
            owner.fem._confirm_native_condition(condition)
        write(out/'native-progress.json', {'phase':'conditions-confirmed'})
        bindings.append(bridge.start(doc, config, QtCore, _existing_owner=owner))
        write(out/'native-progress.json', {'phase':'broker-started'})
        Gui.activateWorkbench('FemWorkbench')
        for obj in doc.Objects:
            if hasattr(obj, 'Shape') and hasattr(obj, 'ViewObject'):
                obj.ViewObject.Visibility = obj is solid
        mesh.ViewObject.Visibility = False
        solid.ViewObject.Visibility = True
        Gui.activeDocument().activeView().viewAxonometric()
        Gui.activeDocument().activeView().fitAll()
        Gui.Selection.clearSelection()
        Gui.Selection.addSelection(solid, saddle[0])
        Gui.getMainWindow().resize(1440, 960)
        write(out/'native-progress.json', {'phase':'before-capture'})
        Gui.getMainWindow().grab().save(str(out / 'pre-selection.png'))
        Gui.activeDocument().activeView().saveImage(str(out/'pre-saddle-viewport.png'),1200,800,'Current')
        report.update(document_id=owner.document_id, session_id=owner.session_id,
                      solid=solid.Name, fixed_face=bottom[0], force_face=saddle[0],
                      direction_edge=vertical[0], nodes=len(mesh.FemMesh.Nodes), elements=len(mesh.FemMesh.Volumes),
                      project=str(Path(config['export_root']) / owner.document_id / 'design.caepre'))
        write(out / 'native-ready.json', report)
        seen = set()

        def tick():
            try:
                action_path = out / 'action.json'
                if not action_path.is_file():
                    return
                action = read(action_path)
                if action['id'] in seen:
                    return
                if action['kind'] == 'quit':
                    seen.add(action['id'])
                    report.update(success=True, generation=owner.generation, force_N=float(force.Force.getValueAs('N').Value))
                    write(out / 'native.json', report)
                    timer.stop()
                    close()
                    return
                # Edit the actual native quantity widget and native dialog buttons.
                tasks = Gui.getMainWindow().findChild(QtGui.QDockWidget, 'Tasks')
                write(out / 'task-widgets.json', [{'name':w.objectName(), 'class':w.metaObject().className()} for w in tasks.findChildren(QtGui.QWidget)])
                field = tasks.findChild(QtGui.QWidget,'spinForce')
                if field is None:
                    raise ValueError('Actual native Force quantity field was not found')
                # QuantitySpinBox.h at the installed FreeCAD source commit
                # declares rawValue as the native double quantity property.
                assert field.setProperty('rawValue',float(App.Units.Quantity('20 N').Value))
                field.clearFocus()
                Gui.getMainWindow().grab().save(str(out / ('task-' + action['kind'] + '.png')))
                box = tasks.findChild(QtGui.QDialogButtonBox)
                role = QtGui.QDialogButtonBox.Cancel if action['kind'] == 'cancel' else QtGui.QDialogButtonBox.Ok
                button = box.button(role)
                assert button is not None
                button.click()
                doc.recompute()
                seen.add(action['id'])
                write(out / (action['id'] + '.json'), {'force_N':float(force.Force.getValueAs('N').Value), 'active_dialog':bool(Gui.Control.activeDialog()), 'generation':owner.generation})
            except BaseException as error:
                write(out / 'native-error.json', {'error':str(error), 'traceback':traceback.format_exc()})
                timer.stop()
                close()
        timer = QtCore.QTimer()
        timer.timeout.connect(tick)
        timer.start(200)
        # Keep native Python/Qt objects alive until quit, without a nested event loop.
        App._caelab_delivery = (timer, bindings, tick, report)
    except BaseException as error:
        report.update(success=False, error=str(error), traceback=traceback.format_exc())
        write(out / ('cold-pre.json' if cold else 'native-error.json'), report)
        close()


def post_stage(config, *, cold=False):
    """Use retained real jobs in installed ParaView, without solving again."""
    from copy import deepcopy
    import numpy as np
    from paraview import simple as p, servermanager
    from paraview.numpy_support import vtk_to_numpy
    from apps.desktop_post import external
    from apps.desktop_post.bridge import Owner
    out = Path(config['root'])
    if cold:
        prior = read(out / 'post.json')
        desktop = (read(out/'post-render.json') if (out/'post-render.json').is_file() else
                   read(out/'post-desktop.json') if (out/'post-desktop.json').is_file() else prior)
        project = Path(desktop['project'])
        doc = read(project)
        os.environ['CAE_POST_PROJECT'] = str(project)
        external.restore_workspace(project, doc)
        owner = Owner()
        assert not owner.workspace.restore_issues, owner.workspace.restore_issues
        if prior.get('comparison_id'):
            assert owner.workspace.sample(object_ref=prior['comparison_id'], preview=False, limit=1000)['rows'] == prior['rows']
        assert len(owner.workspace.document['sources']) == 2
        write(out / 'cold-post.json', {'success':True, 'solver_executed':False, 'project':str(project)})
        return
    inputs = read(out / 'post-inputs.json')
    a, b = inputs['A'], inputs['B']
    assert a['native_metadata']['static'] == b['native_metadata']['static']
    assert a['native_metadata']['static']['load_parameter'] == 1
    def admit(record, directory=None):
        args = (record['path'],)
        kwargs = {'input_id':record['id'], 'source_pins':record['source_pins'],
                  'native_metadata':record.get('native_metadata'), 'registration_origin':record.get('registration_origin')}
        return (external.open_result(*args, directory, **kwargs) if directory else external.admit_result(*args, **kwargs))
    os.environ['CAELAB_ORIGIN_JOB_ID'] = inputs['job_A']
    os.environ['CAELAB_DESKTOP_PYTHON'] = config.get('desktop_python',config['source_python'])
    os.environ['CAELAB_REPO_ROOT'] = str(ROOT)
    os.environ['CAE_POST_SERVICE_URL'] = config['service_url']
    admit(a, out / 'post-project')
    owner = Owner()
    bsource, brecord = admit(b)
    brecord.update(source_ref='changed', label='하중 20 N')
    owner.workspace.document['sources']['changed'] = brecord
    asource = p.FindSource(owner.workspace.document['sources']['result']['reader_name'])
    ad, bd = (servermanager.Fetch(source) for source in (asource, bsource))
    def identity(data):
        return (vtk_to_numpy(data.GetPointData().GetArray('NativeNodeId')),
                vtk_to_numpy(data.GetPoints().GetData()),
                vtk_to_numpy(data.GetCells().GetConnectivityArray()),
                vtk_to_numpy(data.GetCellData().GetArray('NativeElementId')))
    same = all(np.array_equal(left, right) for left, right in zip(identity(ad), identity(bd)))
    report = {'same_native_node_coordinates_elements':same,
              'comparison_mode':'same_mesh_difference' if same else 'side_by_side_only', 'solver_executed':False,
              'engineering_valid':False, 'qualification':'UNKNOWN', 'native_static':a['native_metadata']['static']}
    view = p.GetActiveView()
    p.Hide(bsource, view)
    layout = p.GetLayout(view)
    layout.SplitHorizontal(0, .5)
    right = p.CreateView('RenderView')
    p.AssignViewToLayout(view=right, layout=layout, hint=2)
    z_values = [vtk_to_numpy(data.GetPointData().GetArray('UZ_mm')) for data in (ad,bd)]
    common_z = [min(float(np.min(values)) for values in z_values),max(float(np.max(values)) for values in z_values)]
    for source, target in ((asource, view), (bsource, right)):
        display = p.Show(source, target)
        p.ColorBy(display, ('POINTS','UZ_mm'))
        display.SetScalarBarVisibility(target,True)
        scalar_bar = p.GetScalarBar(p.GetColorTransferFunction('UZ_mm'),target)
        scalar_bar.Title = 'Z displacement (mm)'
        scalar_bar.ComponentTitle = ''
        p.ResetCamera(target)
    p.GetColorTransferFunction('UZ_mm').RescaleTransferFunction(*common_z)
    report['common_UZ_color_range_mm'] = common_z
    p.SaveScreenshot(str(out/'post-comparison.png'), layout, ImageResolution=[1440,900],FontScaling='Do not scale fonts')
    if same:
        side = {'source_ref':'result','array':'U_mm','association':'POINTS',
                'quantity':'displacement','units':'mm','measure':'displacement',
                'frame':a['native_metadata']['coordinate_frame'], 'coordinate_units':'mm',
                'coordinate_frame':a['native_metadata']['coordinate_frame'],
                'layout':{'kind':'vector','components':['x','y','z']},
                'time':None,'time_units':None,'time_origin':None,
                'sampling':{'mode':'exact','time':None}, 'clock_offset':0., 'validity_masks':[]}
        recipe = {'version':2,'a':side,'b':deepcopy(side),'method':'same_mesh','tolerance':0.,
                  'target':{'units':'mm'},'selection':'z','difference':'selected_difference','percent':'disabled',
                  'clock':{'value':None,'unit':None,'semantics':None},
                  'alignment':{'geometry_rotation':[[1.,0.,0.],[0.,1.,0.],[0.,0.,1.]],
                               'response_rotation':[[1.,0.,0.],[0.,1.,0.],[0.,0.,1.]],
                               'translation':[0.,0.,0.],'geometry_declared':False,'response_declared':False}}
        recipe['b']['source_ref'] = 'changed'
        obj = owner.workspace.edit_comparison(draft=recipe, title='하중 변경의 Z 변위')
        owner.workspace.validate(object_ref=obj['id'])
        owner.workspace.apply(object_ref=obj['id'], show=False)
        report.update(comparison_id=obj['id'], rows=owner.workspace.sample(object_ref=obj['id'], preview=False, limit=1000)['rows'])
        for channel in ('UZ_mm','U_magnitude_mm'):
            av, bv = [vtk_to_numpy(data.GetPointData().GetArray(channel)) for data in (ad,bd)]
            report[channel] = {'maximum_A_mm':float(np.max(np.abs(av))), 'maximum_B_mm':float(np.max(np.abs(bv))),
                               'maximum_abs_B_minus_2A_mm':float(np.max(np.abs(bv-2*av)))}
    report.update(project=str(owner.save_project()), success=True)
    write(out/'post.json', report)


def runner_stage(config):
    from PySide6.QtWidgets import QApplication
    from apps.research.runner_window import RunnerWindow
    from caelab.workbench_client import Client
    out = Path(config['root'])
    jobs = [row['value']['id'] for row in read(out/'delivery.json')['stages'] if row['stage'] in ('job-A','job-B')]
    app = QApplication.instance() or QApplication([])
    window = RunnerWindow(Client(config['service_url']), job_id=jobs[-1], poll_interval=0)
    window.show()
    def until(check):
        deadline = time.monotonic()+30
        while time.monotonic()<deadline:
            app.processEvents()
            if check():
                return
            time.sleep(.02)
        raise TimeoutError('Actual Runner operation did not finish')
    try:
        until(lambda:window.selected_job_id==jobs[-1] and not window._pending)
        for index, identifier in enumerate(jobs):
            window.select_job(identifier)
            until(lambda:window.selected_job_id==identifier and not window._pending)
            window.result_button.click()
            until(lambda:not window._pending)
            window.grab().save(str(out/('runner-'+str(index)+'.png')))
        window.origin_button.click()
        until(lambda:not window._pending)
        assert '열었' in window.message.text(), window.message.text()
        write(out/'runner.json', {'success':True,'job_ids':jobs,'return_message':window.message.text()})
    finally:
        window.close()
        app.processEvents()


def gui_post_reopen(config, *, desktop=True):
    """Inspect the saved two-result project in the actual ParaView desktop."""
    import ctypes
    from ctypes import wintypes
    import subprocess
    from paraview import simple as p, servermanager
    from paraview.numpy_support import vtk_to_numpy
    import numpy as np
    from apps.desktop_post import external
    from apps.desktop_post.bridge import Owner
    from apps.desktop_post.native_controls import _Windows
    out = Path(config['root'])
    prior = read(out/'post.json')
    project = Path(prior['project'])
    doc = read(project)
    os.environ['CAE_POST_PROJECT'] = str(project)
    external.restore_workspace(project,doc)
    owner = Owner()
    sources = [p.FindSource(owner.workspace.document['sources'][ref]['reader_name']) for ref in ('result','changed')]
    values = [vtk_to_numpy(servermanager.Fetch(source).GetPointData().GetArray('UZ_mm')) for source in sources]
    color_range = [min(float(np.min(v)) for v in values), max(float(np.max(v)) for v in values)]
    views = [v for v in p.GetViews() if v.GetXMLName()=='RenderView']
    assert len(views)==2
    layout = p.GetLayout(views[0])
    layout.SetSize(1600,1000)
    for index,(source,view) in enumerate(zip(sources,views)):
        for other in sources:
            p.Hide(other,view)
        display = p.Show(source,view)
        p.ColorBy(display,('POINTS','UZ_mm'))
        display.SetScalarBarVisibility(view,True)
        bar = p.GetScalarBar(p.GetColorTransferFunction('UZ_mm'),view)
        bar.Title,bar.ComponentTitle = 'U_Z [mm]',''
        bar.TitleFontSize,bar.LabelFontSize = 14,12
        bar.Orientation = 'Horizontal'
        bar.WindowLocation = 'Lower Center'
        bar.ScalarBarLength = .7
        bar.ScalarBarThickness = 12
        text = p.Text(registrationName='Load case '+str(index+1))
        text.Text = (('A: requested 10 N\nassembled 9.980906 N' if index==0 else 'B: requested 20 N\nassembled 19.961813 N')
                     + '\nForce conservation: FAIL; qualification: UNKNOWN')
        shown = p.Show(text,view)
        shown.FontSize = 14
        shown.WindowLocation = 'Upper Left Corner'
        p.ResetCamera(view)
    for name in ('CameraPosition','CameraFocalPoint','CameraViewUp','CameraParallelScale'):
        setattr(views[0],name,getattr(views[1],name))
    p.GetColorTransferFunction('UZ_mm').RescaleTransferFunction(*color_range)
    p.RenderAllViews()
    p.SaveScreenshot(str(out/'post-desktop-labelled.png'),layout,ImageResolution=[1600,1000],FontScaling='Do not scale fonts')
    saved = owner.save_project()
    if not desktop:
        write(out/'post-render.json',{'success':True,'project':str(saved),'native_render_views':len(views),
            'common_UZ_color_range_mm':color_range,'solver_executed':False,'desktop_visual_acceptance':False})
        owner.close()
        return
    platform = _Windows()
    window = platform.main_window()
    assert window, 'Actual ParaView main window was not found on its GUI thread'
    platform.user.GetWindowRect.argtypes = [wintypes.HWND,ctypes.POINTER(wintypes.RECT)]
    platform.user.GetWindowRect.restype = wintypes.BOOL
    platform.user.SetForegroundWindow.argtypes = [wintypes.HWND]
    platform.user.SetForegroundWindow.restype = wintypes.BOOL
    platform.user.PostMessageW.argtypes = [wintypes.HWND,wintypes.UINT,wintypes.WPARAM,wintypes.LPARAM]
    platform.user.PostMessageW.restype = wintypes.BOOL
    rectangle = wintypes.RECT()
    assert platform.user.GetWindowRect(window,ctypes.byref(rectangle))
    platform.user.SetForegroundWindow(window)
    capture = "import sys;from PIL import ImageGrab;im=ImageGrab.grab(bbox=tuple(map(int,sys.argv[2:])));im.save(sys.argv[1]);h=im.convert('L').histogram();print(1-h[0]/(im.width*im.height))"
    box = [rectangle.left,rectangle.top,rectangle.right,rectangle.bottom]
    captured = subprocess.run([config.get('desktop_python',config['source_python']),'-c',capture,str(out/'post-desktop-window.png'),*[str(v) for v in box]],check=True,timeout=20,capture_output=True,text=True)
    capture_available = float(captured.stdout.strip()) > .01
    write(out/'post-desktop.json',{'success':True,'pid':os.getpid(),'hwnd':int(window),'project':str(saved),
        'native_render_views':len(views),'common_UZ_color_range_mm':color_range,'solver_executed':False,
        'desktop_capture':'AVAILABLE' if capture_available else 'UNAVAILABLE_BLACK_CAPTURE',
        'desktop_visual_acceptance':False})
    owner.close()
    platform.user.PostMessageW(window,0x10,0,0)


def run(config):
    from scripts.native_check import run_native_check
    from apps.lab.server import LabHTTPServer
    from apps.lab.service import LabService
    from caelab.workbench_client import Client
    out = Path(config['root'])
    out.mkdir(parents=True, exist_ok=False)
    write(out / 'config.json', config)
    def native(command, name, seconds=300):
        result = run_native_check(command, out / name, seconds, cwd=ROOT)
        assert result.exit_code == 0 and not result.timed_out, result
        return result
    if config.get('prepared_source'):
        previous = Path(config['prepared_source'])
        shutil.copy2(previous/'working.FCStd', out/'prepared.FCStd')
        shutil.copy2(previous/'source.json', out/'source.json')
        from caelab.native_cad import sha
        write(out/'source-reuse.json', {'prepared_source':str(previous), 'prepared_sha256':sha(out/'prepared.FCStd'), 'remeshed':False})
    else:
        native([config['source_python'], str(Path(__file__)), '--source-stage', str(out / 'config.json')], 'source-process', 240)
    server = LabHTTPServer(LabService(Path(config['store'])), 0)
    thread = threading.Thread(target=server.serve_forever, kwargs={'poll_interval':.05}, daemon=True)
    thread.start()
    config.update(service_url='http://127.0.0.1:' + str(server.server_port), export_root=str(server.workbench.desktop.root), output=str(out / 'pre-output'))
    write(out / 'config.json', config)
    macro = out / 'delivery.FCMacro'
    macro.write_text("import sys\nsys.path.insert(0," + repr(str(ROOT)) + ")\nfrom scripts.check_native_fixture_delivery import native_stage,read\nnative_stage(read(" + repr(str(out / 'config.json')) + "))\n", encoding='utf-8')
    client = Client(config['service_url'])
    records = {'engineering_valid':False, 'qualification':'UNKNOWN', 'workflow_state':'RUNNING', 'stages':[]}
    if config.get('resume_delivery'):
        previous = read(Path(config['resume_delivery'])/'delivery.json')
        records['stages'] = [row for row in previous['stages'] if row['stage'] in
            {'input-A','force-conservation-A','submit-A','job-A','navigation-A'}]
        assert next(row['value'] for row in records['stages'] if row['stage']=='job-A')['state']=='SUCCEEDED'
        write(out/'retained-A-reuse.json', {'previous_delivery':config['resume_delivery'],
            'job_id':next(row['value']['id'] for row in records['stages'] if row['stage']=='job-A'), 'solver_reexecuted':False})
        verify_retained_a(config,out/'retained-A-before.json')
    def progress(label, value):
        records['stages'].append({'stage':label, 'value':value})
        write(out / 'delivery.json', records)
        print(label, json.dumps(value, ensure_ascii=True), flush=True)
    def check_file(path):
        if (out / 'native-error.json').is_file():
            raise RuntimeError(read(out / 'native-error.json'))
        return read(path) if path.is_file() else None
    def command(operation, arguments=None):
        descriptor = client.document_read(ready['document_id'])
        identifier = 'C' + uuid.uuid4().hex
        submitted = client.document_command(ready['document_id'], operation, arguments or {},
            session_id=descriptor['session_id'], expected_generation=descriptor['generation'], command_id=identifier)
        answer = wait(lambda: (row if (row := client.command_status(identifier))['state'] in {'SUCCEEDED','FAILED','INTERRUPTED','CANCELLED'} else None), 180)
        progress(operation, answer)
        assert answer['state'] == 'SUCCEEDED', answer
        return answer
    try:
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(native, [config['freecad'], '--user-cfg',str(out/'user.cfg'), '--system-cfg',str(out/'system.cfg'), str(macro)], 'pre-process', 600)
            try:
                ready = wait(lambda: check_file(out / 'native-ready.json'), 240)
                progress('native-ready', ready)
                wait(lambda:any(row['id']==ready['document_id'] and row.get('connected')
                                for row in client.documents()['documents']))
                phases = [('A',10,None), ('cancelled',10,'cancel'), ('B',20,'accept')]
                if config.get('resume_delivery'):
                    prior_job = next(row['value']['id'] for row in records['stages'] if row['stage']=='job-A')
                    assert client.status(prior_job)['state']=='SUCCEEDED'
                    command('pre.links.record',{'job_id':prior_job})
                    command('document.save')
                    baseline = next(row['value']['snapshot_relative'] for row in records['stages'] if row['stage']=='input-A')
                    baseline_loads = read(Path(config['export_root'])/Path(baseline).parent/'mesh.json')['loads']
                    phases = phases[1:]
                for label, expected, action in phases:
                    if action:
                        command('pre.fem.task_edit', {'target':{'object_id':'DeliveryForce'}})
                        action_id = 'A' + uuid.uuid4().hex
                        write(out / 'action.json', {'id':action_id,'kind':action})
                        edited = wait(lambda: check_file(out / (action_id + '.json')))
                        progress('task-' + action, edited)
                        assert edited['force_N'] == expected and not edited['active_dialog'], edited
                        # Let the broker publish the exact final human-edit generation.
                        wait(lambda: client.document_read(ready['document_id'])['generation'] == edited['generation'])
                    frozen = command('pre.freeze', {'analysis_id':'DeliveryAnalysis','solver_id':'DeliverySolver'})
                    relative = frozen['outcome']['result']['result']['snapshot_relative']
                    snapshot = read(Path(config['export_root']) / relative)
                    force_record = next(row for row in snapshot['conditions'] if row['name']=='DeliveryForce')
                    assert force_record['force_N'] == expected, force_record
                    mesh = read(Path(config['export_root']) / Path(relative).parent / 'mesh.json')
                    resultant = [sum(row['force_N'] for row in mesh['loads'] if row['component']==component) for component in (1,2,3)]
                    progress('input-' + label, {'snapshot_relative':relative,'resultant_N':resultant})
                    force_difference = [resultant[0],resultant[1],resultant[2]+expected]
                    progress('force-conservation-'+label, {'requested_force_N':expected, 'assembled_force_N':resultant, 'difference_N':force_difference,
                        'criterion_absolute_N':1e-8, 'verdict':'PASS' if max(abs(value) for value in force_difference)<1e-8 else 'FAIL',
                        'workflow_admission':'Existing native table/deck, mesh, constraint and hash gates; conservation remains a separate failed numerical claim'})
                    assert resultant[:2] == [0,0] and resultant[2] < 0
                    if label == 'A':
                        baseline_loads = mesh['loads']
                    elif label == 'B':
                        assert [(v['node_id'],v['component']) for v in mesh['loads']] == [(v['node_id'],v['component']) for v in baseline_loads]
                        nodal_delta = max(abs(v['force_N']-2*a['force_N']) for v,a in zip(mesh['loads'],baseline_loads))
                        progress('actual-nodal-load-scaling', {'expected_scale':2.,'maximum_abs_B_minus_2A_N':nodal_delta})
                        assert nodal_delta < 1e-10
                    if label == 'cancelled':
                        continue
                    submitted = client.native_submit(frozen['command_id'])
                    progress('submit-' + label, submitted)
                    job_id = submitted['job']['id']
                    job = wait(lambda: (row if (row := client.status(job_id))['state'] in {'SUCCEEDED','FAILED','CANCELLED','INTERRUPTED'} else None), 180)
                    progress('job-' + label, job)
                    assert job['state'] == 'SUCCEEDED', job
                    command('pre.links.record', {'job_id':job_id})
                    progress('navigation-' + label, client.job_navigation(job_id))
                command('document.save')
                native([sys.executable,str(Path(__file__)),'--runner-stage',str(out/'config.json')],'runner-process',100)
                from apps.research.desktop import open_origin
                progress('return-to-live-design', open_origin(client, job_id))
            finally:
                write(out / 'action.json', {'id':'quit','kind':'quit'})
                future.result(timeout=620)
        assert read(out / 'native.json')['success']
        inputs = {}
        for label in ('A','B'):
            navigation = next(row['value'] for row in records['stages'] if row['stage']=='navigation-'+label)
            job = next(row['value'] for row in records['stages'] if row['stage']=='job-'+label)
            inputs[label] = client.native_input(navigation['post_input']['id'])
            inputs['job_'+label] = job['id']
        write(out/'post-inputs.json', inputs)
        native([config['pvpython'],str(Path(__file__)),'--post-stage',str(out/'config.json')], 'post-process',180)
        gui_script = out/'gui-post.py'
        gui_script.write_text("import sys\nsys.path.insert(0,"+repr(str(ROOT))+")\nfrom scripts.check_native_fixture_delivery import gui_post_reopen,read\ngui_post_reopen(read("+repr(str(out/'config.json'))+"))\n",encoding='utf-8')
        native([str(Path(config['pvpython']).with_name('paraview.exe')),'--dr','--script='+str(gui_script)],'post-desktop-process',120)
        native([config['pvpython'],str(Path(__file__)),'--cold-post-stage',str(out/'config.json')], 'cold-post-process',180)
        cold_macro = out/'cold.FCMacro'
        cold_macro.write_text("import sys\nsys.path.insert(0,"+repr(str(ROOT))+")\nfrom scripts.check_native_fixture_delivery import native_stage,read\nnative_stage(read("+repr(str(out/'config.json'))+"),cold=True)\n",encoding='utf-8')
        native([config['freecad'],'--user-cfg',str(out/'cold-user.cfg'),
                '--system-cfg',str(out/'cold-system.cfg'),str(cold_macro)],'cold-pre-process',180)
        assert read(out/'cold-pre.json')['success']
        if config.get('resume_delivery'):
            verify_retained_a(config,out/'retained-A-after.json')
        records['success'] = True
        records['workflow_state'] = 'COMPLETED_WITH_NUMERICAL_LIMITATIONS'
        write(out / 'delivery.json', records)
    except BaseException as error:
        records.update(success=False, workflow_state='FAILED', error=str(error), traceback=traceback.format_exc())
        write(out/'delivery.json',records)
        raise
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-stage', type=Path)
    parser.add_argument('--post-stage', type=Path)
    parser.add_argument('--cold-post-stage', type=Path)
    parser.add_argument('--runner-stage', type=Path)
    parser.add_argument('--root', type=Path)
    parser.add_argument('--source-python', type=Path)
    parser.add_argument('--freecad-root', type=Path)
    parser.add_argument('--pvpython',type=Path)
    parser.add_argument('--prepared-source',type=Path,help='Reuse an existing verified working.FCStd and mesh without remeshing')
    parser.add_argument('--resume-delivery',type=Path,help='Resume this check after retained A succeeded, without rerunning A')
    args = parser.parse_args()
    if args.source_stage:
        source_stage(read(args.source_stage))
        return
    if args.post_stage or args.cold_post_stage:
        post_stage(read(args.post_stage or args.cold_post_stage), cold=bool(args.cold_post_stage))
        return
    if args.runner_stage:
        runner_stage(read(args.runner_stage))
        return
    if not all((args.root, args.source_python, args.freecad_root)):
        parser.error('--root, --source-python and --freecad-root are required')
    fc = args.freecad_root.resolve()
    config = {'root':str(args.root.resolve()), 'store':str(args.root.resolve() / 'store'),
              'source_python':str(args.source_python.resolve()), 'freecad':str(fc/'bin/FreeCAD.exe'),
              'freecad_cmd':str(fc/'bin/FreeCADCmd.exe'), 'gmsh':str(fc/'bin/gmsh.exe')}
    if args.prepared_source:
        config['prepared_source'] = str(args.prepared_source.resolve())
    if args.resume_delivery:
        prior = args.resume_delivery.resolve()
        prior_config = read(prior/'config.json')
        ready = read(prior/'native-ready.json')
        config.update(prepared_source=str(prior),resume_delivery=str(prior),
                      resume_project=ready['project'],store=prior_config['store'])
    config['pvpython'] = str((args.pvpython or fc.parent/'ParaView-6.2.0-Windows-Python3.12-msvc2017-AMD64/bin/pvpython.exe').resolve())
    os.environ['PATH'] = str(fc/'bin') + os.pathsep + os.environ['PATH']
    for key in ('source_python','freecad','freecad_cmd','gmsh'):
        if not Path(config[key]).is_file():
            raise FileNotFoundError(config[key])
    run(config)


if __name__ == '__main__':
    main()
