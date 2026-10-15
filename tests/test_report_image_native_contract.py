"""SCRIPTED ParaView/owner interface + REAL saved analytic VTK data.

The actual Workspace.export method is isolated from its module and executed with
SaveScreenshot replaced by a recorded PNG writer. This does NOT prove native
ParaView rendering, owner lifecycle or Windows integration.
"""
import ast
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys
import threading
from types import SimpleNamespace
import uuid

import pytest
vtk = pytest.importorskip('vtk')
from caelab.post_observation import file_pin
from caelab.report_image import completed_content, retained_analyses
from report_image_fixture import fixture, png_bytes
from report_image_block_fixture import RawRepresentation, Version
from test_report_image_vtk import tetra


class Proxy:
    def __init__(self, kind, identifier, properties=None, **attributes):
        self.kind, self.identifier = kind, identifier
        self.props = properties or {}; self.pending = []
        self.__dict__.update(attributes)
    def GetXMLName(self): return self.kind
    def GetGlobalIDAsString(self): return self.identifier


class Information:
    def __init__(self, data): self.data=data
    def GetHasTime(self): return self.data.GetInformation().Has(vtk.vtkDataObject.DATA_TIME_STEP())
    def GetTime(self): return self.data.GetInformation().Get(vtk.vtkDataObject.DATA_TIME_STEP())
    def GetPointDataInformation(self):
        return SimpleNamespace(GetArrayInformation=lambda name:self.data.GetPointData().GetArray(name))
    def GetCellDataInformation(self):
        return SimpleNamespace(GetArrayInformation=lambda name:self.data.GetCellData().GetArray(name))
    def GetBounds(self): return self.data.GetBounds()
    def GetNumberOfPoints(self):return self.data.GetNumberOfPoints()
    def GetNumberOfCells(self):return self.data.GetNumberOfCells()


@pytest.fixture
def native(tmp_path,monkeypatch):
    f=fixture(tmp_path/'공개 합성 native contract')
    data=tetra();data.GetInformation().Set(vtk.vtkDataObject.DATA_TIME_STEP(),.25)
    writer=vtk.vtkXMLUnstructuredGridWriter();writer.SetInputData(data);writer.SetFileName(str(f['result']))
    assert writer.Write()==1
    f['record'].update(result_files=[file_pin(f['result'])],result_sha256=file_pin(f['result'])['sha256'])
    f['manifest'].write_text(json.dumps(f['project'],ensure_ascii=False),encoding='utf-8')
    source=Proxy('Clip','source',GetDataInformation=lambda:SimpleNamespace(DataInformation=Information(data)))
    lut=Proxy('PVLookupTable','lut',{'VectorMode':'Magnitude','RGBPoints':[0,0,0,0,3,1,1,1]})
    color=SimpleNamespace(GetData=lambda:['POINTS','stress'])
    rep=Proxy('GeometryRepresentation','rep',{'Representation':'Surface','MapScalars':1},
        Input=source,Visibility=1,ColorArrayName=color,LookupTable=lut)
    rep.SMProxy = RawRepresentation()
    view=Proxy('RenderView','view',{'CameraPosition':[2.,3.,4.],'CameraFocalPoint':[0.,0.,0.],
        'CameraViewUp':[0.,0.,1.],'ViewSize':[640,480],'ViewTime':.25},Representations=[rep],ViewTime=.25)
    calls=[];changes=[]
    def screenshot(path,selected):
        assert selected is view
        calls.append(('SaveScreenshot',path))
        Path(path).write_bytes(png_bytes())
        for change in changes:change()
    p=SimpleNamespace(Render=lambda selected:calls.append(('Render',selected.identifier)),
                      SaveScreenshot=screenshot,GetAnimationScene=lambda:SimpleNamespace(AnimationTime=view.ViewTime))
    module=SimpleNamespace(simple=p,servermanager=SimpleNamespace(Fetch=lambda selected:data, vtkSMProxyManager=Version))
    monkeypatch.setitem(sys.modules,'paraview',module)
    main_thread=threading.get_ident()
    def assert_thread():
        if threading.get_ident()!=main_thread:raise RuntimeError('wrong native owner thread')
    owner=SimpleNamespace(document_id='Dpost',session_id='Snative',project_path=f['manifest'],
        generation=4,view_generation=3,assert_thread=assert_thread,refresh=lambda:None,
        native_properties=lambda proxy:(deepcopy(proxy.props),list(proxy.pending)),proxy_id=lambda proxy:proxy.identifier)
    tree=ast.parse((Path(__file__).parents[1]/'apps/desktop_post/workspace.py').read_text())
    klass=next(item for item in tree.body if isinstance(item,ast.ClassDef) and item.name=='Workspace')
    method=next(item for item in klass.body if isinstance(item,ast.FunctionDef) and item.name=='export')
    namespace={'__package__':'apps.desktop_post','p':p,'Path':Path,'uuid':uuid,
               'external':SimpleNamespace(sha=lambda path:hashlib.sha256(Path(path).read_bytes()).hexdigest())}
    exec(compile(ast.Module(body=[method],type_ignores=[]),'isolated-existing-Workspace.export','exec'),namespace)
    class Workspace:
        export=namespace['export']
        def object(self,ref):assert ref=='Fresult';return f['object']
        def _bundle(self,obj):return f['record'],{'source':source,'proxies':[source]}
        def _views(self):return [('RenderView1',view)]
        def _output_declaration(self,ref):return f['project']['sources']['Sinput']['native_metadata']
    workspace=Workspace();workspace.owner=owner;workspace.document=f['project']
    return SimpleNamespace(workspace=workspace,f=f,data=data,view=view,rep=rep,source=source,lut=lut,
                           calls=calls,changes=changes)


def test_existing_export_called_once_and_source_condition_bytes_bound(native):
    n=native
    receipt=n.workspace.export(object_ref='Fresult',format='png',report_snapshot=True)
    assert sum(call[0]=='SaveScreenshot' for call in n.calls)==1
    assert receipt['analysis_saved'] is False
    snapshot=receipt['report_snapshot']
    assert snapshot['scene']['field']['unit']=='MPa'
    assert snapshot['scene']['clock']['value']==.25
    assert snapshot['scene']['camera']['CameraPosition']==[2.,3.,4.]
    assert snapshot['data_match']['status']=='EXACT'
    assert snapshot['result_status']['execution_status']=='UNKNOWN'
    command=deepcopy(n.f['command']);command['outcome']['result']['result']=receipt
    ref,content=completed_content(command)
    n.view.props['CameraPosition']=[9,9,9]  # Later Post change cannot alter retained data.
    assert content['snapshot']['scene']['camera']['CameraPosition']==[2.,3.,4.]
    assert ref['kind']=='post_image'


@pytest.mark.parametrize('change',['camera','array','time','field','source'])
def test_change_inside_screenshot_does_not_publish_success(native,change):
    n=native
    if change=='camera':n.changes.append(lambda:n.view.props.update(CameraPosition=[9,9,9]))
    elif change=='array':n.changes.append(lambda:n.data.GetPointData().GetArray('stress').SetTuple1(1,7.))
    elif change=='time':n.changes.append(lambda:n.data.GetInformation().Set(vtk.vtkDataObject.DATA_TIME_STEP(),.26))
    elif change=='field':n.changes.append(lambda:setattr(n.rep,'ColorArrayName',SimpleNamespace(GetData=lambda:['CELLS','stress'])))
    else:n.changes.append(lambda:n.f['source'].write_text('changed source'))
    with pytest.raises((ValueError,OSError)):n.workspace.export(object_ref='Fresult',format='png',report_snapshot=True)
    assert sum(call[0]=='SaveScreenshot' for call in n.calls)==1


@pytest.mark.parametrize('problem',['nearest','old_frame','pending','overlay','uniform','texture','missing_view','unsaved'])
def test_unsupported_or_ambiguous_capture_fails_before_screenshot(native,problem):
    n=native
    if problem=='nearest':n.view.ViewTime=.25000001
    elif problem=='old_frame':
        n.view.ViewTime=.5;n.data.GetInformation().Set(vtk.vtkDataObject.DATA_TIME_STEP(),.5)
    elif problem=='pending':n.view.pending=['CameraPosition']
    elif problem=='overlay':n.view.Representations.append(Proxy('TextSourceRepresentation','annotation',Visibility=1))
    elif problem=='uniform':n.rep.ColorArrayName=SimpleNamespace(GetData=lambda:['POINTS',''])
    elif problem=='texture':n.rep.props['Texture']={'proxy_id':'texture'}
    elif problem=='missing_view':n.workspace._views=lambda:[]
    else:n.f['record']['recipe']['filter']='Slice'
    with pytest.raises((ValueError,OSError)):n.workspace.export(object_ref='Fresult',format='png',report_snapshot=True)
    assert not any(call[0]=='SaveScreenshot' for call in n.calls)


def test_native_absence_never_uses_another_renderer(native,monkeypatch):
    monkeypatch.setitem(sys.modules,'paraview',None)
    with pytest.raises(ModuleNotFoundError):native.workspace.export(object_ref='Fresult',format='png',report_snapshot=True)
    assert not native.calls


def test_unit_not_declared_remains_unknown(native):
    native.f['record']['summary'].pop('declarations')
    native.f['manifest'].write_text(json.dumps(native.f['project'],ensure_ascii=False),encoding='utf-8')
    native.workspace._output_declaration=lambda ref: {'arrays':[{'units':'BOGUS_CURRENT'}]}
    receipt=native.workspace.export(object_ref='Fresult',format='png',report_snapshot=True)
    field=receipt['report_snapshot']['scene']['field']
    assert field['unit'] is None and field['unit_status']=='UNKNOWN'


def test_scalar_bar_tied_to_selected_field(native):
    n=native
    n.view.Representations.append(Proxy('ScalarBarWidgetRepresentation','bar',{'Title':'응력'},Visibility=1,LookupTable=n.lut))
    receipt=n.workspace.export(object_ref='Fresult',format='png',report_snapshot=True)
    assert receipt['report_snapshot']['scene']['legend']==[{'Title':'응력'}]


def test_plain_export_is_still_plain_and_not_a_report_evidence(native):
    receipt=native.workspace.export(object_ref='Fresult',format='png')
    assert 'report_snapshot' not in receipt
    assert len(native.calls)==1
    command=deepcopy(native.f['command']);command['outcome']['result']['result']=receipt
    with pytest.raises(ValueError):completed_content(command)
