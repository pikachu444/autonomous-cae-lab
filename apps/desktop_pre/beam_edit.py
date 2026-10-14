"""Native beam handler; shares bridge.Owner/metadata/transactions with shell/NS1.

The beam end object is a persisted, editable FreeCAD extension, not a rigid
body or a synthetic pair of forces. Its exact CLOAD/BOUNDARY projection is
owned by beam_deck and executed only through the beam command.
"""
from copy import deepcopy
from caelab.storage import canonical_hash
from caelab.beam_model import (NAMESPACE, BeamInputError, default_draft, validate_draft,
                              number, section_properties, check_draft_shape, OPERATIONS)
from . import beam_native
from .beam_mesh_binding import REFERENCE_KEY, capture_reference, require_same_binding


class BeamEndProxy:
    Type='CAELab::BeamEnd'
    def __init__(self,obj):obj.Proxy=self
    def execute(self,obj):pass
    def onDocumentRestored(self,obj):
        # PropertyQuantity stores its scalar, but custom units are supplied by
        # the feature proxy again when restoring the native document.
        import FreeCAD as App
        for axis in 'XYZ':
            if obj.getTypeIdOfProperty('Moment'+axis)=='App::PropertyQuantity':
                setattr(obj,'Moment'+axis,App.Units.Unit('N*mm'))
    def dumps(self):return None
    def loads(self,state):pass
    def __getstate__(self):return None
    def __setstate__(self,state):pass


def make_end(doc,name):
    obj=doc.addObject('App::FeaturePython',name)
    BeamEndProxy(obj)
    obj.addProperty('App::PropertyLinkSubList','References','끝 조건')
    obj.addProperty('App::PropertyEnumeration','CoordinateSystem','끝 조건')
    obj.CoordinateSystem=['global','local'];obj.CoordinateSystem='global'
    for axis in 'XYZ':
        obj.addProperty('App::PropertyForce','Force'+axis,'힘 (N)')
        obj.addProperty('App::PropertyMoment','Moment'+axis,'모멘트 (Nmm)')
        setattr(obj,'Moment'+axis,'0 N*mm')
        obj.addProperty('App::PropertyBool','TranslationFree'+axis,'구속')
        obj.addProperty('App::PropertyBool','RotationFree'+axis,'구속')
        setattr(obj,'TranslationFree'+axis,True);setattr(obj,'RotationFree'+axis,True)
        obj.addProperty('App::PropertyDistance','Displacement'+axis,'변위 (mm)')
        obj.addProperty('App::PropertyAngle','Rotation'+axis,'회전 (deg)')
    return obj


def _refs(obj,source,subelement):
    obj.References=[(source,[subelement])]


def project_properties(owner,record):
    """Only called inside the same native transaction as the draft update."""
    d=record['draft'];analysis=beam_native.get_object(owner,d['analysis_id'],'analysis_id')
    source=beam_native.get_object(owner,d['edge']['object'],'edge')
    import ObjectsFem
    spec=(('section','object_id','Fem::ElementGeometry1D',ObjectsFem.makeElementGeometry1D,'BeamSection'),
          ('section','rotation_id','Fem::ElementRotation1D',ObjectsFem.makeElementRotation1D,'BeamRotation'),
          ('material','object_id','Fem::MaterialCommon',ObjectsFem.makeMaterialSolid,'BeamMaterial'))
    objects={}
    for group,key,kind,factory,name in spec:
        name_id=d[group][key]
        obj=beam_native.get_object(owner,name_id,group+'.'+key) if name_id else factory(owner.doc,name=name)
        if name_id and (obj not in analysis.Group or beam_native.native_type(obj)!=kind):
            raise BeamInputError(group+'.'+key,'선택한 해석의 해당 native 객체를 선택하세요.')
        if not name_id:analysis.addObject(obj)
        d[group][key]=obj.Name;objects[group+'.'+key]=obj
    sec=objects['section.object_id'];rot=objects['section.rotation_id'];mat=objects['material.object_id']
    sec.SectionType='Rectangular'
    sec.RectWidth=f"{number(d['section']['width_mm']):.16g} mm"
    sec.RectHeight=f"{number(d['section']['height_mm']):.16g} mm"
    rot.Rotation=f"{number(d['section']['rotation_deg']):.16g} deg"
    _refs(sec,source,d['edge']['subelement']);_refs(rot,source,d['edge']['subelement']);_refs(mat,source,d['edge']['subelement'])
    mat.Material=dict(mat.Material,Name=mat.Material.get('Name','빔 재료'),
        YoungsModulus=f"{number(d['material']['young_MPa']):.16g} MPa",PoissonRatio=str(number(d['material']['poisson'])))
    names=record.get('end_object_ids',[])
    if names and len(names)!=2:raise BeamInputError('ends','저장된 끝 조건 목록이 잘못됐습니다.')
    if not names:
        names=[]
        for i in range(2):
            obj=make_end(owner.doc,'BeamEnd');analysis.addObject(obj);names.append(obj.Name)
    for i,name in enumerate(names):
        obj=beam_native.get_object(owner,name,f'ends.{i}')
        if obj not in analysis.Group or getattr(getattr(obj,'Proxy',None),'Type',None)!='CAELab::BeamEnd':
            raise BeamInputError(f'ends.{i}','빔 끝 조건의 원 객체를 선택하세요.')
        row=d['ends'][i];obj.Label=row.get('label') or f'끝 {i+1}'
        target=beam_native.get_object(owner,row['reference']['object'],f'ends.{i}.reference')
        _refs(obj,target,row['reference']['subelement']);obj.CoordinateSystem=row['system']
        for k,axis in enumerate('XYZ'):
            setattr(obj,'Force'+axis,f"{number(row['force_N'][k]):.16g} N")
            setattr(obj,'Moment'+axis,f"{number(row['moment_Nmm'][k]):.16g} N*mm")
            for key,prefix,free,units in (('translation_mm','Displacement','TranslationFree','mm'),
                                        ('rotation_deg','Rotation','RotationFree','deg')):
                text=row[key][k];is_free=text is None or isinstance(text,str) and not text.strip()
                setattr(obj,free+axis,is_free)
                if not is_free:setattr(obj,prefix+axis,f'{number(text):.16g} {units}')
    record['end_object_ids']=names


class BeamEditor:
    def __init__(self,owner):self.owner=owner
    def _records(self):return self.owner.read_metadata().get(NAMESPACE,{})
    def _get(self,analysis_id):
        record=self._records().get(analysis_id)
        if record is None:raise BeamInputError('analysis_id','빔 설정을 먼저 만드세요.')
        return deepcopy(record)
    def _put(self,key,record):
        data=self.owner.read_metadata();data.setdefault(NAMESPACE,{})[key]=deepcopy(record)
        self.owner.write_metadata(data)
    def discover(self):
        rows=[]
        for obj in self.owner.doc.Objects:
            try:kind=beam_native.native_type(obj)
            except Exception:continue
            if kind=='Fem::FemAnalysis':
                rows.append({'id':obj.Name,'label':obj.Label,'meshes':[
                    {'id':m.Name,'label':m.Label} for m in obj.Group if hasattr(m,'FemMesh') and
                    not m.FemMesh.Volumes and not m.FemMesh.Faces and m.FemMesh.Edges]})
        return rows
    def inspect(self,analysis_id=None):
        self.owner.assert_thread()
        result={'analyses':self.discover(),'models':deepcopy(self._records())}
        if analysis_id:
            r=self._get(analysis_id);errors=validate_draft(r['draft'])
            model=None
            if not errors:
                try:
                    model,_=beam_native.geometry(self.owner,r['draft'])
                    errors=validate_draft(r['draft'],model['axes'])
                    beam_native.validate_model(model)
                except BeamInputError as exc:errors.append(exc.record())
                except Exception as exc:errors.append({'path':'mesh_id','message':str(exc)})
            applied=r.get('applied_draft_hash')==canonical_hash(r['draft'])
            if not errors and applied:
                try:beam_native.collect(self.owner,r)
                except BeamInputError as exc:errors.append(exc.record())
                except Exception as exc:errors.append({'path':'native','message':str(exc)})
            result.update(record=r,errors=errors,can_freeze=applied and not errors,
                          preview=None if model is None else {'axes':model['axes'],'length_mm':model['length_mm'],
                            'ends':model['end_conditions'],'properties':section_properties(r['draft'])})
        return result
    def create(self,args):
        if set(args)!={'analysis_id','mesh_id','edge'}:
            raise ValueError('Select one Analysis, 1D mesh and Edge')
        if args['analysis_id'] in self._records():
            raise BeamInputError('analysis_id','이미 빔 설정이 있습니다. 기존 설정을 편집하세요.')
        d=default_draft(**args)
        analysis=beam_native.get_object(self.owner,d['analysis_id'],'analysis_id')
        mesh=beam_native.get_object(self.owner,d['mesh_id'],'mesh_id')
        if beam_native.native_type(analysis)!='Fem::FemAnalysis' or mesh not in analysis.Group:
            raise BeamInputError('mesh_id','같은 해석에 속한 선 메시를 선택하세요.')
        # Reuse an unambiguous section/material/rotation, never choose by list order.
        for kind,g,k in [('Fem::ElementGeometry1D','section','object_id'),('Fem::ElementRotation1D','section','rotation_id'),
                         ('Fem::MaterialCommon','material','object_id')]:
            found=[o for o in analysis.Group if beam_native.native_type(o)==kind]
            if len(found)>1:raise BeamInputError(g,'첫 빔 경로는 하나의 균일 단면·재료만 지원합니다.')
            if found:d[g][k]=found[0].Name
        if d['section']['object_id']:
            o=self.owner.doc.getObject(d['section']['object_id'])
            if str(o.SectionType)!='Rectangular':
                raise BeamInputError('section.object_id','첫 빔 경로는 Rectangular 단면만 지원합니다. 기존 단면을 자동 변환하지 않습니다.')
            d['section'].update(width_mm=str(beam_native._quantity(o,'RectWidth','mm')),
                                height_mm=str(beam_native._quantity(o,'RectHeight','mm')))
        if d['section']['rotation_id']:
            d['section']['rotation_deg']=str(beam_native._quantity(self.owner.doc.getObject(d['section']['rotation_id']),'Rotation','deg'))
        if d['material']['object_id']:
            mat=self.owner.doc.getObject(d['material']['object_id']).Material
            d['material'].update(young_MPa=str(float(self.owner.App.Units.Quantity(mat['YoungsModulus']).getValueAs('MPa').Value)),
                                 poisson=str(number(mat['PoissonRatio'])))
        self.owner._transaction('빔 설정 만들기',lambda:self._put(d['analysis_id'],{'draft':d,'end_object_ids':[]}))
        return self.inspect(d['analysis_id'])
    def save_draft(self,key,draft):
        r=self._get(key)
        check_draft_shape(draft)
        if draft.get('analysis_id')!=key:raise ValueError('Analysis identity cannot change in a beam edit')
        # Metadata.write enforces JSON/size safety. Invalid numeric strings are intentional.
        r['draft']=deepcopy(draft)
        self.owner._transaction('빔 초안 저장',lambda:self._put(key,r))
        return self.inspect(key)
    def apply(self,key,draft=None,*,rebind=False):
        r=self._get(key)
        if draft is not None:r['draft']=deepcopy(draft)
        if r['draft'].get('analysis_id')!=key:raise ValueError('Analysis identity changed')
        errors=validate_draft(r['draft'])
        if errors:raise BeamInputError(errors[0]['path'],errors[0]['message'])
        model,binding=beam_native.geometry(self.owner,r['draft'])
        beam_native.validate_model(model)
        if ('binding' in r or r.get('applied_draft_hash')) and not rebind:
            require_same_binding(r,model,binding)
        reference=capture_reference(model,binding)
        if r.get('native_property_stamp') and beam_native.property_stamp(self.owner,self._get(key))!=r['native_property_stamp']:
            if not rebind or beam_native.property_stamp(self.owner,self._get(key),values_only=True)!=r.get('native_value_stamp'):
                raise BeamInputError('native','native 속성이 변경됐습니다. 속성 불러오기로 먼저 확인하세요.')
        def change():
            project_properties(self.owner,r)
            self.owner.doc.recompute()
            # Recompute may touch the native mesh. Admit only the same exact
            # geometry, even if its native storage compacted the labels.
            current,current_binding=beam_native.geometry(self.owner,r['draft'])
            require_same_binding({'binding':binding,REFERENCE_KEY:reference},current,current_binding)
            beam_native.validate_model(current)
            r.update(binding=current_binding,applied_draft_hash=canonical_hash(r['draft']))
            r[REFERENCE_KEY]=capture_reference(current,current_binding)
            r['native_property_stamp']=beam_native.property_stamp(self.owner,r)
            r['native_value_stamp']=beam_native.property_stamp(self.owner,r,values_only=True)
            self._put(key,r)
        self.owner._transaction('빔 참조 다시 지정' if rebind else '빔 설정 적용',change)
        return self.inspect(key)
    def import_properties(self,key):
        r=self._get(key);r['draft']=beam_native.native_values(self.owner,r)
        r['native_property_stamp']=beam_native.property_stamp(self.owner,r)
        r['native_value_stamp']=beam_native.property_stamp(self.owner,r,values_only=True)
        r.pop('applied_draft_hash',None)
        self.owner._transaction('빔 속성 불러오기',lambda:self._put(key,r))
        return self.inspect(key)
    def dispatch(self,operation,args,target):
        if target:raise ValueError('Beam commands use exact analysis_id, not an alternate target')
        if operation=='pre.beam.inspect':
            if set(args)-{'analysis_id'}:raise ValueError('Unexpected beam inspection argument')
            return self.inspect(args.get('analysis_id'))
        self.owner.before_design_action(operation)
        if operation=='pre.beam.create':return self.create(args)
        key=args.get('analysis_id')
        allowed={'analysis_id','draft'} if operation in ('pre.beam.draft','pre.beam.apply','pre.beam.rebind') else {'analysis_id'}
        if set(args)!=allowed:raise ValueError('Unexpected beam command arguments')
        if operation=='pre.beam.draft':return self.save_draft(key,args['draft'])
        if operation in ('pre.beam.apply','pre.beam.rebind'):
            return self.apply(key,args['draft'],rebind=operation.endswith('rebind'))
        if operation=='pre.beam.import_properties':return self.import_properties(key)
        if operation=='pre.beam.freeze':return beam_native.freeze(self.owner,self._get(key))
        raise ValueError('Unknown beam command')
