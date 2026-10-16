"""Laminate editing on the existing native document/transaction/material owners."""
from copy import deepcopy
import json
import uuid

from caelab.composite_shell import default_draft, prepare_mesh, validate, material_values
from caelab.shell_model import digest, ShellError
from .shell_edit import ShellEditor, native_type, SETTINGS

OPERATIONS=tuple('pre.composite.'+name for name in ('inspect','begin','selection','add_region','draft','apply','freeze'))
READ_ONLY={'pre.composite.inspect','pre.composite.selection'}
NAMESPACE='composite_shells'
MATERIAL_KEYS={'E1_MPa':'YoungsModulusX','E2_MPa':'YoungsModulusY','E3_MPa':'YoungsModulusZ',
               'nu12':'PoissonRatioXY','nu13':'PoissonRatioXZ','nu23':'PoissonRatioYZ',
               'G12_MPa':'ShearModulusXY','G13_MPa':'ShearModulusXZ','G23_MPa':'ShearModulusYZ',
               'E_MPa':'YoungsModulus','nu':'PoissonRatio'}


class CompositeEditor(ShellEditor):
    def _all(self):
        data=deepcopy(self.owner.read_metadata());data.setdefault(NAMESPACE,{})
        if not isinstance(data[NAMESPACE],dict):raise ValueError('저장된 적층 초안을 읽을 수 없습니다.')
        return data

    def _record(self,analysis_id):
        if analysis_id not in self._all()[NAMESPACE]:raise ValueError('해석과 8절점 셸 메시에서 적층 설정을 만드세요.')
        return self._all()[NAMESPACE][analysis_id]

    def _store(self,analysis_id,record,title):
        def change():
            data=self._all();data[NAMESPACE][analysis_id]=deepcopy(record);self.owner.write_metadata(data)
        self.owner._transaction('CAE Lab '+title,change)

    def catalog(self):
        rows=[]
        for obj in self.owner.doc.Objects:
            if native_type(obj)!='Fem::MaterialCommon' or getattr(obj,'Category',None)!='Solid':continue
            material=dict(obj.Material);law=material.get('CAELabLinearLaw','isotropic_linear')
            from caelab.composite_shell import ORTHOTROPIC,ISOTROPIC
            names=ORTHOTROPIC if law=='orthotropic_linear' else ISOTROPIC
            constants={}
            for name in names:
                raw=material.get(MATERIAL_KEYS[name],'')
                try:
                    constants[name]=(str(self.owner.App.Units.Quantity(raw).getValueAs('MPa').Value)
                                     if name.endswith('_MPa') else str(raw))
                except (ValueError,TypeError,RuntimeError):constants[name]=''
            rows.append({'id':obj.Name,'label':obj.Label,'law':law,'constants':constants})
        return rows

    def begin(self,args):
        aid=args['analysis_id']
        if aid in self._all()[NAMESPACE]:return self.inspect(aid)
        analysis=self._object(aid);mesh=self._object(args['mesh_id']);solver=self._object(args['solver_id'])
        if native_type(analysis)!='Fem::FemAnalysis' or mesh not in analysis.Group or solver not in analysis.Group or native_type(solver)!='Fem::SolverCcxTools':
            raise ValueError('현재 해석의 셸 메시와 CalculiX 솔버를 선택하세요.')
        if aid in self.owner.read_metadata().get('shells',{}):
            raise ValueError('기존 S8 해석을 적층으로 덮지 않습니다. 별도 해석에서 S8R 적층을 설정하세요.')
        draft=default_draft(aid,mesh.Name,solver.Name)
        _,_,elements=self._mesh(draft);draft['elements']=sorted(elements)
        draft['materials']={row['id']:{'label':row['label'],'law':row['law'],'constants':row['constants']} for row in self.catalog()}
        self._store(aid,{'draft':draft,'applied':None,'feature_id':None},'적층 초안 만들기')
        return self.inspect(aid)

    def selection(self,aid):
        from .shell_region_native import selection
        return selection(self,aid)

    def add_region(self,aid,label):
        record=self._record(aid);draft=record['draft']
        if draft.get('binding'):self._binding(draft)
        selected=self.selection(aid)
        if any(set(r['elements']).intersection(selected['elements']) for r in draft['regions']):
            raise ValueError('선택한 요소가 다른 적층 영역에 포함돼 있습니다.')
        draft['regions'].append({'id':'R'+uuid.uuid4().hex,'label':label or '적층 영역',
            **selected,'orientation':'','axis':['1','0','0'],'offset':'0','pressure_MPa':'0.001','plies':[]})
        draft['binding']=self._stamp(draft)
        self._store(aid,record,'선택 면에 적층 영역 추가')
        return self.inspect(aid)

    def save_draft(self,aid,draft):
        old=self._record(aid);original=old['draft']
        if not isinstance(draft,dict) or len(json.dumps(draft,ensure_ascii=False).encode('utf-8'))>2*1024**2:
            raise ValueError('적층 초안이 너무 크거나 잘못됐습니다.')
        for key in ('analysis_id','mesh_id','solver_id','binding','elements','fixed_nodes'):
            if draft.get(key)!=original.get(key):raise ValueError('대상·고정조건은 native 선택 작업에서만 변경할 수 있습니다.')
        targets={r['id']:r for r in original['regions']}
        for row in draft.get('regions',[]):
            if row.get('id') not in targets or any(row.get(k)!=targets[row['id']].get(k) for k in ('elements','face_refs')):
                raise ValueError('새 영역은 native 화면의 실제 면/메시 선택으로 추가하세요.')
        # Invalid numeric strings remain editable/saveable; Apply owns validation.
        old['draft']=deepcopy(draft);self._store(aid,old,'적층 초안 저장')
        return self.inspect(aid)

    def _members(self,draft,*,complete=False):
        analysis=self._object(draft['analysis_id']);solver=self._object(draft['solver_id']);mesh=self._object(draft['mesh_id'])
        if native_type(analysis)!='Fem::FemAnalysis' or solver not in analysis.Group or mesh not in analysis.Group:
            raise ValueError('적층 해석의 원 메시와 솔버가 없거나 해석 소속이 바뀌었습니다.')
        allowed={'Fem::SolverCcxTools','Fem::MaterialCommon','Fem::ConstraintFixed'}
        feature=self._record(draft['analysis_id'])['feature_id']
        for obj in analysis.Group:
            if getattr(obj,'Suppressed',False) or obj is mesh or obj.Name==feature or native_type(obj).startswith(('Fem::FemResult','Fem::FemMeshResult')):continue
            if native_type(obj) not in allowed:
                raise ValueError(obj.Label+': 적층 경로가 읽지 않는 활성 조건입니다. 별도 해석으로 분리하세요.')
        for name in {p.get('material_id') for r in draft['regions'] for p in r.get('plies',[])}:
            material=self._object(name)
            if native_type(material)!='Fem::MaterialCommon' or getattr(material,'Category',None)!='Solid':
                raise ValueError('원 FreeCAD 고체 재료를 선택하세요.')
        if any(hasattr(obj,'FemMesh') and obj is not mesh for obj in analysis.Group):raise ValueError('적층 해석에는 선택한 셸 메시 하나만 참여해야 합니다.')
        return analysis,{}

    def _native_state(self,draft):
        self._members(draft)
        record=self._record(draft['analysis_id']);obj=self._object(record['feature_id'])
        used={p['material_id'] for r in draft['regions'] for p in r['plies']}
        materials={name:dict(self._object(name).Material) for name in used}
        return {'binding':self._stamp(draft),'definition':obj.CAELabCompositeDefinition,
                'feature_id':obj.Name,'materials':materials,
                'solver':{k:getattr(self._object(draft['solver_id']),k) for k in SETTINGS}}

    def apply(self,aid):
        record=self._record(aid);draft=record['draft'];self._binding(draft);analysis,_=self._members(draft)
        _,nodes,elements=self._mesh(draft);mesh=prepare_mesh(nodes,elements,draft);self._fixed(draft,mesh)
        def change():
            if not record['feature_id']:
                obj=self.owner.doc.addObject('App::FeaturePython','CAELabComposite')
                obj.Label='적층 셸';obj.addProperty('App::PropertyString','CAELabCompositeDefinition','적층 셸')
                analysis.addObject(obj);record['feature_id']=obj.Name
            obj=self._object(record['feature_id'])
            obj.CAELabCompositeDefinition=json.dumps(draft,sort_keys=True,ensure_ascii=False)
            for name,values in mesh['values']['materials'].items():
                material=self._object(name);updated=dict(material.Material)
                updated['CAELabLinearLaw']=values['law']
                for key,value in values['constants'].items():
                    updated[MATERIAL_KEYS[key]]=format(value,'.17g')+(' MPa' if key.endswith('_MPa') else '')
                material.Material=updated
            for key,value in SETTINGS.items():setattr(self._object(draft['solver_id']),key,value)
            data=self._all();data[NAMESPACE][aid]=record;self.owner.write_metadata(data)
            record['applied']={'draft':deepcopy(draft),'native':self._native_state(draft)}
            data=self._all();data[NAMESPACE][aid]=record;self.owner.write_metadata(data)
        self.owner._transaction('CAE Lab 적층 속성 적용',change)
        return self.inspect(aid)

    def effective(self,aid):
        record=self._record(aid);draft=record['draft'];self._binding(draft)
        _,nodes,elements=self._mesh(draft);mesh=prepare_mesh(nodes,elements,draft);fixed=self._fixed(draft,mesh)
        if (record.get('applied') or {}).get('draft')!=draft or record['applied']['native']!=self._native_state(draft):
            raise ValueError('적층·재료·대상·native 조건을 확인하고 명시적으로 적용하세요.')
        return record,mesh,fixed

    def inspect(self,aid=None):
        if aid is None:
            return {'analyses':[{'id':o.Name,'label':o.Label} for o in self.owner.doc.Objects if native_type(o)=='Fem::FemAnalysis'],
                    'meshes':[{'id':o.Name,'label':o.Label} for o in self.owner.doc.Objects if hasattr(o,'FemMesh')],
                    'solvers':[{'id':o.Name,'label':o.Label} for o in self.owner.doc.Objects if native_type(o)=='Fem::SolverCcxTools'],
                    'materials':self.catalog(),'records':list(self._all()[NAMESPACE])}
        record=self._record(aid);errors,_=validate(record['draft'])
        can_freeze=False
        try:self.effective(aid);can_freeze=True
        except (ValueError,KeyError,TypeError) as error:
            if not errors:errors=[{'path':'apply','message':str(error)}]
        return {'analysis_id':aid,**record,'errors':errors,'can_freeze':can_freeze,'materials':self.catalog()}

    def export_binding_evidence(self,*,include_shells=False):
        # Same established BREP proof format, consumed by the existing Project save.
        records={'composite:'+k:v for k,v in self._all()[NAMESPACE].items()}
        if include_shells:records.update({'shell:'+k:v for k,v in self._all().get('shells',{}).items()})
        from types import SimpleNamespace
        source=SimpleNamespace(_all=lambda:{'shells':records},_binding_brep=self._binding_brep)
        return ShellEditor.export_binding_evidence(source)

    def dispatch(self,operation,args,target=None):
        if target:raise ValueError('적층 명령은 명시 해석 인수를 사용합니다.')
        allowed={'pre.composite.inspect':{'analysis_id'},'pre.composite.begin':{'analysis_id','mesh_id','solver_id'},
                 'pre.composite.selection':{'analysis_id'},'pre.composite.add_region':{'analysis_id','label'},
                 'pre.composite.draft':{'analysis_id','draft'},'pre.composite.apply':{'analysis_id'},
                 'pre.composite.freeze':{'analysis_id'}}
        if operation not in allowed or not isinstance(args,dict) or set(args)-allowed[operation]:
            raise ValueError('적층 명령의 인수를 확인하세요.')
        if operation!='pre.composite.inspect' and (not isinstance(args.get('analysis_id'),str) or not args['analysis_id']):
            raise ValueError('원 해석을 선택하세요.')
        aid=args.get('analysis_id')
        if operation=='pre.composite.inspect':return self.inspect(aid)
        if operation=='pre.composite.begin':return self.begin(args)
        if operation=='pre.composite.selection':return self.selection(aid)
        if operation=='pre.composite.add_region':return self.add_region(aid,args.get('label',''))
        if operation=='pre.composite.draft':return self.save_draft(aid,args['draft'])
        if operation=='pre.composite.apply':return self.apply(aid)
        if operation=='pre.composite.freeze':
            from .composite_freeze import freeze
            return freeze(self,aid)
        raise ValueError('알 수 없는 적층 명령입니다.')
