"""Connector editing in the existing native FreeCAD Owner and project archive.

Capture is read-only. Apply rechecks the actual selected CAD/mesh and commits one
metadata transaction. A selected region is exported only as explicitly accepted
rigid representation; no deformable FE stiffness/mass is silently transferred.
"""
from copy import deepcopy
import hashlib
from pathlib import Path
import shutil
import uuid

from caelab.connector_model import (NAMESPACE,OPERATIONS,READ_ONLY,BACKEND,
    ConnectorInputError,default_draft,check_shape,model)
from caelab.storage import canonical_hash,save_json
from .mesh_binding import global_placement


def _hash(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def _xyz(p): return [float(p.x),float(p.y),float(p.z)]


def _selection(owner, references):
    """Read exact native geometry; no searching by label or reconstructed mesh."""
    points=[]; proof=[]; labels=[]; reference_mm=None
    for ref in references:
        if not isinstance(ref,dict) or set(ref)!={'object_id','subelements'}:
            raise ConnectorInputError('selection','원 모델의 대상과 하위 형상을 다시 선택하세요.')
        obj=owner.doc.getObject(ref['object_id'])
        if obj is None or obj.TypeId in ('App::Link','App::LinkElement'):
            raise ConnectorInputError('selection','같은 문서의 직접 CAD 또는 메시 대상을 선택하세요. 링크 배치를 추정하지 않습니다.')
        pose=global_placement(obj)
        # Native Shape vertex coordinates already include object Placement.
        # Assembly occurrences need an explicit occurrence mapping, not an extra
        # guessed transform which can apply object Placement twice.
        if hasattr(obj,'Placement'):
            p=obj.Placement
            if pose!=[*_xyz(p.Base),*[float(v) for v in p.Rotation.Q]]:
                raise ConnectorInputError('selection','상위 부품의 별도 배치가 있는 대상은 아직 지원하지 않습니다. 직접 대상을 선택하세요.')
        names=ref['subelements']
        if not isinstance(names,list) or len(names)!=len(set(names)):
            raise ConnectorInputError('selection','서로 다른 실제 하위 대상을 선택하세요.')
        if hasattr(obj,'FemMesh'):
            if any(abs(v)>1e-12 for v in pose[:6]) or abs(abs(pose[6])-1)>1e-12:
                raise ConnectorInputError('selection','별도 배치가 있는 메시는 원 절점 좌표와의 대응을 먼저 확인해야 합니다.')
            native=obj.FemMesh; selected=[]
            for name in names:
                if not isinstance(name,str) or not name.startswith('Node') or not name[4:].isdigit():
                    raise ConnectorInputError('selection','메시에서는 실제 Node 번호를 명시 선택하세요.')
                n=int(name[4:])
                if n not in native.Nodes: raise ConnectorInputError('selection','선택 절점이 없습니다. 다시 선택하세요.')
                selected.append((n,_xyz(native.Nodes[n])))
            if not selected: raise ConnectorInputError('selection','메시의 실제 절점을 선택하세요.')
            all_nodes=[(int(n),_xyz(v)) for n,v in sorted(native.Nodes.items())]
            proof.append({'object_id':obj.Name,'type':obj.TypeId,'global_placement':pose,
                'mesh_nodes_hash':canonical_hash(all_nodes),'selected_nodes':selected})
            points.extend(v for _,v in selected)
        elif hasattr(obj,'Shape') and not obj.Shape.isNull() and obj.Shape.isValid():
            import re
            shapes=[]
            for name in names:
                if not isinstance(name,str) or not re.fullmatch(r'(Vertex|Edge|Face|Solid)[1-9][0-9]*',name):
                    raise ConnectorInputError('selection','꼭짓점·모서리·면·솔리드 영역을 선택하세요.')
                try: shapes.append(obj.Shape.getElement(name))
                except Exception as exc: raise ConnectorInputError('selection','원 하위 형상이 변경됐습니다. 다시 선택하세요.') from exc
            if not names: shapes=[obj.Shape]
            points.extend(_xyz(v.Point) for shape in shapes for v in shape.Vertexes)
            proof.append({'object_id':obj.Name,'type':obj.TypeId,'global_placement':pose,
                'brep_sha256':hashlib.sha256(obj.Shape.exportBrepToString().encode('utf-8')).hexdigest(),
                'subelements':[{'name':name,'brep_sha256':hashlib.sha256(shape.exportBrepToString().encode('utf-8')).hexdigest()}
                               for name,shape in zip(names,shapes)]})
        else: raise ConnectorInputError('selection','유효한 CAD 형상 또는 실제 메시 절점을 선택하세요.')
        if ref is references[-1] and names and names[-1].startswith('Vertex'):
            reference_mm=_xyz(obj.Shape.getElement(names[-1]).Point)
        labels.append(str(obj.Label)+(' '+', '.join(names) if names else ''))
    # Shared vertices inside one selected surface are a single native point.
    points=sorted({tuple(p) for p in points})
    if not points: raise ConnectorInputError('selection','선택 영역에 실제 점이 없습니다.')
    if reference_mm is None:
        if len(points)!=1:
                raise ConnectorInputError('selection','영역과 함께 실제 기준 꼭짓점 하나를 마지막에 선택하세요.')
        reference_mm=list(points[0])
    return {'label':' / '.join(labels),'reference_mm':list(reference_mm),'points_mm':[list(p) for p in points],
            'kind':'vertex' if len(points)==1 else 'region','native_refs':deepcopy(references),
            'identity':{'document_id':owner.document_id,'native_document':owner.doc.Name,'objects':proof}}


def _same_selection(owner,saved,current):
    if saved==current:return True
    if not isinstance(saved,dict) or set(saved)!=set(current):return False
    if any(saved[k]!=current[k] for k in saved if k!='identity'):return False
    old=saved['identity'];new=current['identity']
    if set(old)!=set(new) or any(old[k]!=new[k] for k in old if k!='objects'):return False
    if len(old['objects'])!=len(new['objects']):return False
    # Existing FEM v3 source proof authenticates serialization-only differences
    # against the retained original BRep and exact subelement order/orientation.
    return all(a==b or owner.fem._same_condition_target(a,b) for a,b in zip(old['objects'],new['objects']))


def check_targets(owner,draft):
    for i,end in enumerate(draft['endpoints']):
        old=end['selection']
        if not isinstance(old,dict): raise ConnectorInputError(f'endpoints.{i}.selection','대상 A와 B를 실제 모델에서 선택하세요.')
        current=_selection(owner,old['native_refs'])
        if not _same_selection(owner,old,current):
            raise ConnectorInputError(f'endpoints.{i}.selection','원 모델 형상·메시·배치가 달라졌습니다. 해당 대상을 다시 선택하세요.')
    from .connector_fe_native import revalidate
    revalidate(owner,draft)


class ConnectorEditor:
    def __init__(self,owner): self.owner=owner
    def _records(self): return self.owner.read_metadata().get(NAMESPACE,{})
    def _get(self,key):
        if key not in self._records(): raise ConnectorInputError('connector_id','연결요소 설정을 먼저 만드세요.')
        return deepcopy(self._records()[key])
    def _put(self,key,record):
        data=self.owner.read_metadata();data.setdefault(NAMESPACE,{})[key]=deepcopy(record);self.owner.write_metadata(data)
    def inspect(self,connector_id=None):
        self.owner.assert_thread()
        result={'records':[{'id':key,'label':r['draft']['label']} for key,r in self._records().items()]}
        if connector_id is None: return result
        record=self._get(connector_id);errors=[]
        try:
            model(record['draft']);check_targets(self.owner,record['draft'])
            if record.get('applied_draft_hash')!=canonical_hash(record['draft']):
                raise ConnectorInputError('draft','수정한 초안을 먼저 적용하세요.')
        except ConnectorInputError as exc: errors.append(exc.record())
        except (ValueError,KeyError,TypeError,OverflowError,AttributeError) as exc:
            errors.append({'path':'fe' if record['draft'].get('fe') is not None else 'draft','message':str(exc)})
        result.update(record={'id':connector_id,**record},errors=errors,can_freeze=not errors)
        return result
    def create(self,label='연결요소'):
        key='C'+uuid.uuid4().hex;record={'draft':default_draft(label)}
        self.owner._transaction('연결요소 만들기',lambda:self._put(key,record))
        return self.inspect(key)
    def discover_fe(self):
        from .fem_edit import _native_type
        self.owner.assert_thread()
        return [{'analysis_id':a.Name,'label':a.Label,'solver_id':s.Name,'solver_label':s.Label}
                for a in self.owner.doc.Objects if _native_type(a)=='Fem::FemAnalysis'
                for s in a.Group if _native_type(s)=='Fem::SolverCcxTools' and not getattr(s,'Suppressed',False)]
    def save_draft(self,key,draft):
        check_shape(draft);record=self._get(key);record['draft']=deepcopy(draft)
        self.owner._transaction('연결요소 초안 저장',lambda:self._put(key,record))
        return self.inspect(key)
    def apply(self,key,draft):
        model(draft);check_targets(self.owner,draft);record=self._get(key)
        record.update(draft=deepcopy(draft),applied_draft_hash=canonical_hash(draft))
        self.owner._transaction('연결요소 적용',lambda:self._put(key,record))
        return self.inspect(key)
    def capture(self,key,endpoint_index):
        self._get(key)
        if type(endpoint_index) is not int or endpoint_index not in (0,1):
            raise ConnectorInputError('endpoint_index','대상 A 또는 B를 선택하세요.')
        selected=self.owner.Gui.Selection.getSelectionEx()
        refs=[{'object_id':s.Object.Name,'subelements':list(s.SubElementNames)} for s in selected]
        if not refs: raise ConnectorInputError('selection','CAD 영역과 질량중심 기준 꼭짓점을 선택하세요.')
        # One selected vertex alone is a reference. For a region, the last
        # selection must be its explicit reference vertex; it is not averaged.
        return {'selection':_selection(self.owner,refs)}
    def capture_fe(self,key,draft,analysis_id,solver_id):
        """Return a local draft; explicit Apply still owns the metadata write."""
        self._get(key);check_shape(draft)
        from .connector_fe_native import capture
        current=deepcopy(draft);current['fe']=capture(self.owner,analysis_id,solver_id,current)
        return {'draft':current,'mass_source':'existing FE nodal mass; no manual endpoint mass/inertia added'}
    def freeze(self,key):
        from .freeze_analysis import require_ready_model
        require_ready_model(self.owner.doc,owner=self.owner)
        record=self._get(key)
        if self.inspect(key)['errors']: raise ConnectorInputError('draft','입력 오류를 수정하고 적용한 뒤 입력을 준비하세요.')
        check_targets(self.owner,record['draft']);m=model(record['draft'])
        saved=self.owner.project.save()
        generation=self.owner.generation
        folder=self.owner.export_root/self.owner.document_id/('F'+uuid.uuid4().hex)
        folder.mkdir(parents=True,exist_ok=False)
        shutil.copyfile(saved['retained_project'],folder/'editable.caepre')
        settings={'connector':deepcopy(record['draft'])}
        save_json(folder/'input.json',settings)
        if m['fe'] is None:
            from caelab.connector_deck import starter,engine
            (folder/'connector_0000.rad').write_text(starter(m),encoding='ascii',newline='\n')
            (folder/'connector_0001.rad').write_text(engine(m),encoding='ascii',newline='\n')
        else:
            from caelab.impact_model import render
            text,_=render(m['fe']['settings'])
            (folder/'original-fe.inp').write_text(text,encoding='ascii',newline='\n')
        check_targets(self.owner,record['draft'])
        if generation!=self.owner.generation:
            raise ConnectorInputError('draft','입력 준비 중 원 모델이 바뀌었습니다. 보존한 입력을 실행하지 말고 다시 준비하세요.')
        save_json(folder/'snapshot.json',{'kind':'freecad-connector-frozen','schema_version':'1',
            'id':folder.name,'document_id':self.owner.document_id,'connector_id':key,
            'backend':BACKEND,'input_file':'input.json','editable_project':'editable.caepre',
            'qualification':'UNKNOWN','source_selections':[e['selection'] for e in m['endpoints']],
            'files':[{'relative':p.name,'bytes':p.stat().st_size,'sha256':_hash(p)} for p in sorted(folder.iterdir()) if p.is_file()]})
        return {'snapshot_relative':(folder/'snapshot.json').relative_to(self.owner.export_root).as_posix(),
                'label':record['draft']['label'],'backend':BACKEND,
                'draft':{'backend':BACKEND,'settings':settings},'calculation':'NOT_STARTED'}
    def dispatch(self,operation,args,target):
        if target: raise ValueError('연결요소는 저장된 실제 대상 A와 B를 사용합니다.')
        fields={'inspect':set(),'create':{'label'},'draft':{'connector_id','draft'},
                'apply':{'connector_id','draft'},'capture':{'connector_id','endpoint_index'},'freeze':{'connector_id'}}
        op=operation.removeprefix('pre.connector.')
        if op not in fields or (set(args)!=fields[op] and not(op=='inspect' and set(args)=={'connector_id'})):
            raise ValueError('지원되지 않는 연결요소 명령 인수입니다.')
        if op=='inspect': return self.inspect(args.get('connector_id'))
        if op=='create': return self.create(args['label'])
        if op=='draft': return self.save_draft(args['connector_id'],args['draft'])
        if op=='apply': return self.apply(args['connector_id'],args['draft'])
        if op=='capture': return self.capture(args['connector_id'],args['endpoint_index'])
        return self.freeze(args['connector_id'])
