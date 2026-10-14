"""Real VTK data, explicit ParaView proxy/state and command-boundary doubles.

Not a native ParaView/GUI acceptance test. The supplied archive omits commands
and source_repair: their narrow reader-path/health boundaries are doubled here.
The code under test is the unmodified shared registrar plus patched external.py.
"""
from copy import deepcopy
import hashlib
import importlib
import json
import os
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace as NS
import xml.etree.ElementTree as ET


class Source:
    def __init__(self, kind, filename, name):
        self.kind=kind;self.FileName=filename;self.name=name;self.SMProxy=self;self.grid=None
        self.frames=[]
        if kind=='PVDReader':
            path=Path(filename)
            self.frames=[(float(row.get('timestep')),path.parent/row.get('file')) for row in ET.parse(path).findall('./Collection/DataSet')]
        self.TimestepValues=[time for time,_ in self.frames]
        self.UpdatePipeline()
    def GetXMLName(self):return self.kind
    def UpdatePipeline(self,time=None):
        import vtk
        if self.frames:
            chosen=self.frames[0][0] if time is None else time
            path=next(path for t,path in self.frames if t==chosen)
        else:path=Path(self.FileName[0] if isinstance(self.FileName,list) else self.FileName)
        reader=vtk.vtkXMLUnstructuredGridReader();reader.SetFileName(str(path));reader.Update()
        if reader.GetErrorCode():raise ValueError('Real VTK reader failed')
        self.grid=reader.GetOutput()
        for label,getter in [('PointData','GetPointData'),('CellData','GetCellData'),('FieldData','GetFieldData')]:
            data=getattr(self.grid,getter)()
            setattr(self,label,{data.GetArrayName(i):data.GetArray(i) for i in range(data.GetNumberOfArrays())})
    def GetDataInformation(self):return self.grid


class Display:
    def __init__(self):self.selection=None
    def RescaleTransferFunctionToDataRange(self,*args):pass
    def SetScalarBarVisibility(self,view,visible):self.visible=visible


class ProxyStateDouble:
    def __init__(self):
        self.sources={};self.views={};self.displays={};self.bars={};self.source=None;self.view=None
        self.scene=NS(AnimationTime=0.,UpdateAnimationUsingDataTimeSteps=lambda:None)
    def _reader(self,kind,registrationName,FileName):
        source=Source(kind,FileName,registrationName);self.sources[(registrationName,len(self.sources)+1)]=source;self.source=source;return source
    def PVDReader(self,registrationName,FileName):return self._reader('PVDReader',registrationName,FileName)
    def XMLUnstructuredGridReader(self,registrationName,FileName):return self._reader('XMLUnstructuredGridReader',registrationName,FileName)
    def GetSources(self):return self.sources
    def FindSource(self,name):return next((s for (n,_),s in self.sources.items() if n==name),None)
    def GetActiveSource(self):return self.source
    def SetActiveSource(self,source):self.source=source
    def GetActiveView(self):return self.view
    def SetActiveView(self,view):self.view=view
    def GetViews(self):return list(self.views.values())
    def GetAnimationScene(self):return self.scene
    def CreateLayout(self,**kwargs):return NS(**kwargs)
    def CreateView(self,kind):
        name='View'+str(len(self.views)+1);view=NS(name=name,kind=kind,ViewTime=self.scene.AnimationTime,GetXMLName=lambda:kind)
        self.views[(name,len(self.views)+1)]=view;return view
    def AssignViewToLayout(self,**kwargs):pass
    def Show(self,source,view):return self.displays.setdefault((source.name,view.name),Display())
    def ResetCamera(self,view):pass
    def ColorBy(self,display,selection):display.selection=selection
    def GetColorTransferFunction(self,name):return name
    def GetScalarBar(self,transfer,view):return self.bars.setdefault((transfer,view.name),NS(Title='',ComponentTitle=''))
    def HideUnusedScalarBars(self,view):
        used={d.selection[1] for (source,name),d in self.displays.items()
              if name==view.name and d.selection}
        for (transfer,name),bar in self.bars.items():
            if name==view.name:bar.Visibility=int(transfer in used)
    def UpdateScalarBarsComponentTitle(self,transfer,display):
        component=display.selection[2] if len(display.selection)>2 else ''
        self.GetScalarBar(transfer,self.view).ComponentTitle=component
    def Delete(self,source):
        self.sources={key:value for key,value in self.sources.items() if value is not source}
    def SaveState(self,path):
        payload={'format':'TEST_PROXY_STATE_NOT_NATIVE_PVSM','time':self.scene.AnimationTime,
            'sources':[{'name':s.name,'kind':s.kind,'file':s.FileName} for s in self.sources.values()],
            'views':[{'name':v.name,'kind':v.kind,'time':v.ViewTime} for v in self.views.values()],
            'displays':[{'source':s,'view':v,'selection':d.selection} for (s,v),d in self.displays.items()],
            'bars':[{'array':a,'view':v,'title':b.Title,'component':b.ComponentTitle} for (a,v),b in self.bars.items()]}
        Path(path).write_text(json.dumps(payload,ensure_ascii=False),encoding='utf-8')
    def LoadState(self,path):
        state=json.loads(Path(path).read_text(encoding='utf-8'));assert state['format']=='TEST_PROXY_STATE_NOT_NATIVE_PVSM'
        self.sources.clear();self.views.clear();self.displays.clear();self.bars.clear();self.scene.AnimationTime=state['time']
        for row in state['sources']:
            source=self._reader(row['kind'],row['name'],row['file']);source.UpdatePipeline(time=state['time'])
        for row in state['views']:
            view=self.CreateView(row['kind']);assert view.name==row['name'];view.ViewTime=row['time']
        for row in state['displays']:
            display=Display();display.selection=tuple(row['selection']) if row['selection'] else None
            self.displays[(row['source'],row['view'])]=display
        for row in state['bars']:
            self.bars[(row['array'],row['view'])]=NS(Title=row['title'],ComponentTitle=row['component'])


def install(monkeypatch=None):
    put=(lambda name,value:monkeypatch.setitem(sys.modules,name,value)) if monkeypatch else sys.modules.__setitem__
    p=ProxyStateDouble()
    sm=NS(Fetch=lambda s:s.grid,ProxyManager=lambda:NS(GetProxiesInGroup=lambda group:p.views if group=='views' else p.sources),
          vtkSMCoreUtilities=NS(GetFileNameProperty=lambda s:'FileName' if hasattr(s,'FileName') else None))
    pv=ModuleType('paraview');pv.simple=p;pv.servermanager=sm
    put('paraview',pv);put('paraview.simple',p);put('paraview.servermanager',sm)
    commands=ModuleType('apps.desktop_post.commands')
    commands.sha=lambda path:hashlib.sha256(Path(path).read_bytes()).hexdigest()
    def reader_input_files(source):
        name=sm.vtkSMCoreUtilities.GetFileNameProperty(source.SMProxy)
        if not name:return []
        values=getattr(source,name);values=[values] if isinstance(values,str) else values
        return [Path(str(value)).resolve(strict=True) for value in values]
    commands.reader_input_files=reader_input_files
    commands.project=lambda:(Path(os.environ['CAE_POST_PROJECT']),json.loads(Path(os.environ['CAE_POST_PROJECT']).read_text(encoding='utf-8')))
    put('apps.desktop_post.commands',commands)
    if 'apps.desktop_post.external' in sys.modules:
        external=importlib.reload(sys.modules['apps.desktop_post.external'])
    else:external=importlib.import_module('apps.desktop_post.external')
    repair=ModuleType('apps.desktop_post.source_repair')
    def source_issues(document):
        issues=[]
        for ref,record in document.get('sources',{}).items():
            try:external.verify_sources(None,{'sources':{ref:record}})
            except (OSError,ValueError,RuntimeError) as error:
                issues.append({'source_ref':ref,'input_id':record.get('input_id'),'reader_name':record['reader_name'],'message':str(error)})
        return issues
    def verify_analysis_files(document):
        for obj in document.get('analysis',{}).get('objects',{}).values():
            for revision in obj.get('history',[]):
                for record in revision.get('result_files',[]):
                    file=Path(record['path'])
                    if not file.is_file() or file.stat().st_size!=record['bytes'] or commands.sha(file)!=record['sha256']:
                        raise ValueError('Retained analysis result changed')
    def partial_state(*args,**kwargs):raise AssertionError('Native PVSM repair is not part of this proxy double')
    repair.source_issues=source_issues;repair.verify_analysis_files=verify_analysis_files;repair.partial_state=partial_state
    put('apps.desktop_post.source_repair',repair)
    # Python package attributes can outlive patched sys.modules between tests.
    package=importlib.import_module('apps.desktop_post')
    if monkeypatch:
        monkeypatch.setattr(package,'commands',commands,raising=False)
        monkeypatch.setattr(package,'source_repair',repair,raising=False)
    else:package.commands=commands;package.source_repair=repair
    return p,sm,external
