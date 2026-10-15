"""Selected reads of EXISTING impact attempt artifacts and Post provenance.

There is no new project/store: impact_execution.json remains the attempt receipt,
input.json the declaration, native/frame*.vtk the original converter payloads,
and post/ the existing writer's artifacts. C2's generic pin operations are reused;
its CalculiX/FRD parser and result schema are deliberately not called.
"""
from collections.abc import Sequence
from copy import deepcopy
import json
from pathlib import Path

from .dynamic_result_store import file_pin, verify_pin, admit_pin
from .impact_native_io import read_bytes
from .execution_control import check_cancelled
from .storage import canonical_hash

BACKEND='explicit.opencourant.model'
SCHEMA='impact-existing-attempt-pins-v1'


def frame_record(root, path, raw):
    return {'artifact':file_pin(root,path),'time_s':raw['time'],
        'fields':{association:{name:item['components'] for name,item in raw[association].items() if name!='SourcePartID'}
                  for association in ('POINTS','CELLS')},'coverage':deepcopy(raw.get('coverage',{}))}


class FrameView(Sequence):
    """At most one native VTK payload per access; no unrelated frame hydration."""
    def __init__(self, root, frames, model, physics):
        self.root=Path(root);self.frames=deepcopy(frames);self.model=model;self.physics=physics
        times=[r['time_s'] for r in self.frames]
        if any(b<=a for a,b in zip(times,times[1:])):raise ValueError('Native frame clock is duplicate or non-monotonic')
    def __len__(self):return len(self.frames)
    def __getitem__(self,index):
        if isinstance(index,slice):return [self[i] for i in range(*index.indices(len(self)))]
        if type(index) is not int:raise TypeError('Use an exact integer frame index')
        if index<0:index+=len(self)
        if not 0<=index<len(self):raise IndexError(index)
        check_cancelled();meta=self.frames[index]
        path=admit_pin(self.root,meta['artifact'])
        from .adapters.impact_results import read_vtk,validate_frame_identity
        raw=read_vtk(path,expected_pin=meta['artifact'])
        if raw['time']!=meta['time_s']:raise ValueError('Native frame time differs from its exact source receipt')
        raw['coverage']=validate_frame_identity(raw,self.model,self.physics)
        if {a:{n:i['components'] for n,i in raw[a].items() if n!='SourcePartID'} for a in ('POINTS','CELLS')}!=meta['fields']:
            raise ValueError('Native array association/components changed')
        return path,raw


def artifact_receipt(output, frames=()):
    root=Path(output);fixed={}
    for name in ('input.json','initial_conditions.json','initial_mass_properties.json','physical_admission.json',
                 'source_bundle/manifest.json','generated_sets.json','damage_definition.json','source_lineage.json'):
        path=root/name
        if path.is_file():fixed[name]=file_pin(root,path)
    # These are original attempt artifacts, including failed native prefixes.
    # The directory itself is not treated as a trusted source of new files later.
    raw={}
    for directory,table in (('source_bundle',fixed),('native',raw)):
        for p in sorted((root/directory).rglob('*')):
            if p.is_symlink() or (hasattr(p,'is_junction') and p.is_junction()):
                raise ValueError('Linked input/result artifact cannot be retained: '+str(p))
            if p.is_file():table[p.relative_to(root).as_posix()]=file_pin(root,p)
    return {'schema':SCHEMA,'input_artifacts':fixed,'native_artifacts':raw,'frames':deepcopy(list(frames)),
            'clock':'NATIVE_PHYSICAL_SECONDS','sampling':'ANIMATION_SAMPLES_NOT_ALL_SOLVER_INCREMENTS',
            'transport':'C2_GENERIC_PINS_AND_WINDOWS_IDENTITY','reader':'impact_results.read_vtk; not FRD'}


def reference(output):
    root=Path(output)
    return {'kind':'IMPACT_RETAINED_ATTEMPT','impact_record':file_pin(root,root/'impact_execution.json')}


def _json(root,pin):
    path=admit_pin(root,pin)
    return json.loads(read_bytes(path,expected=pin,maximum=64*1024*1024))


def context(outcome, output):
    if not isinstance(outcome,dict) or outcome.get('kind')!='IMPACT_RETAINED_ATTEMPT':
        raise ValueError('Select the original impact attempt reference')
    pin=outcome.get('impact_record',{})
    if pin.get('relative')!='impact_execution.json':raise ValueError('The impact execution record is required')
    root=Path(output);record=_json(root,pin);retained=record.get('retained_native',{})
    if retained.get('schema')!=SCHEMA:raise ValueError('No retained native impact artifact contract exists')
    fixed=retained['input_artifacts']
    settings=_json(root,fixed['input.json'])
    from .impact_model import model_from_settings
    from .impact_source import resolve
    resolve(settings['source'])
    model=model_from_settings(settings)
    if canonical_hash(settings['source'])!=record['diagnostics']['source_sha256']:
        raise ValueError('Retained native result belongs to another input definition')
    if 'initial_conditions.json' not in fixed or 'physical_admission.json' not in fixed:
        raise ValueError('Attempt has no completed input/physics admission for native field reading')
    initial=_json(root,fixed['initial_conditions.json'])
    initial['nodes']={int(k):v for k,v in initial['nodes'].items()}
    model={**model,'nodes':initial['nodes']}
    physics=_json(root,fixed['physical_admission.json'])['physics']
    damage=_json(root,fixed['damage_definition.json']) if 'damage_definition.json' in fixed else {'elements':{},'geometry':{}}
    return root,record,settings,model,physics,damage


def inventory(outcome,output):
    _,record,_,_,_,_=context(outcome,output)
    return {'frames':deepcopy(record['retained_native']['frames']),
            'verification':'METADATA_ONLY_PAYLOAD_NOT_VERIFIED','execution_status':record['execution_status'],
            'native_execution_status':record['diagnostics'].get('native_execution_status','UNKNOWN'),
            'solver_execution':'NOT_PERFORMED'}


def select_frame(outcome,output,*,index,quantity,component,identity,metadata_only=False,verification='selected'):
    if metadata_only:raise ValueError('Payload selection cannot be VERIFIED with metadata_only=True; use inventory')
    if type(index) is not int or index<0:raise ValueError('Select an exact nonnegative frame index')
    if quantity=='contact_impulse' or quantity.startswith('cohesive_'):
        raise ValueError('Single native frame selection does not synthesize derived impulse or B-scope cohesive quantities')
    if verification not in ('selected','all'):raise ValueError('Choose selected or all payload verification')
    root,record,settings,model,physics,damage=context(outcome,output)
    from .impact_responses import validate,_sample,QUANTITIES
    row={'name':'selection','quantity':quantity,'component':component,'identity':identity}
    validate(model,[row]);frames=FrameView(root,record['retained_native']['frames'],model,physics)
    if verification=='all':
        for _ in frames:pass
    path,raw=frames[index];value,reason=_sample(raw,row,model,damage)
    association=QUANTITIES[quantity][1]
    entity=deepcopy(model.get('lineage',{}).get('nodes' if association=='POINTS' else 'elements',{}).get(str(identity)))
    if entity is not None and association=='POINTS':entity['initial_coordinates_mm']=deepcopy(model['nodes'][identity])
    return {'status':'AVAILABLE' if value is not None else 'UNKNOWN','value':value,'reason':reason,
        'time_s':raw['time'],'frame_index':index,'unit':QUANTITIES[quantity][3],'component':component,
        'coordinate_frame':'MODEL_GLOBAL','selection':row,'source_entity':entity,
        'source':frame_record(root,path,raw),'input_sha256':canonical_hash(settings['source']),
        'original_execution_status':record['execution_status'],
        'verification':'ALL_PAYLOADS_VERIFIED' if verification=='all' else 'SELECTED_PAYLOAD_VERIFIED',
        'solver_execution':'NOT_PERFORMED','origin':'NATIVE' if not quantity.startswith('cohesive_') and quantity!='contact_impulse' else 'DERIVED'}


def catalog(backend,outcome,output):
    if backend!=BACKEND:raise ValueError('Impact reader backend mismatch')
    root,record,settings,model,physics,damage=context(outcome,output)
    from .impact_responses import QUANTITIES
    result={};frames=record['retained_native']['frames']
    for quantity,(label,association,array,unit,components,measure) in QUANTITIES.items():
        # Derived fatigue/cohesive/impulse methods remain their existing explicitly
        # selected definitions. They are not advertised as newly measured channels.
        if quantity=='contact_impulse' or quantity.startswith('cohesive_'):continue
        if not any(r['fields'].get(association,{}).get(array)==len(components) for r in frames):continue
        for component in components:
            name=f'impact.{quantity}.{component}'
            result[name]={'kind':'series','unit':unit,'component':component,'frame':'MODEL_GLOBAL',
                'measure':measure,'reduction':'none','association':association,'label':label+' '+component,
                'selector_template':name+'@<exact-native-id>','quantity':quantity,
                'axes':[{'name':'time','unit':'s','semantics':'NATIVE_ANIMATION_SAMPLE_TIME'}],
                'source':{'backend':BACKEND,'artifact':'impact_execution.json',
                          'sha256':outcome['impact_record']['sha256'],'value_origin':'NATIVE_ANIMATION',
                          'input_sha256':canonical_hash(settings['source'])},
                'metadata':{'qualification':'UNKNOWN','execution_status':record['execution_status'],
                            'sampling':'ANIMATION_SAMPLES_NOT_ALL_SOLVER_INCREMENTS'}}
    return result


def read(backend,outcome,output,selector,*,start=None,stop=None):
    declared=catalog(backend,outcome,output);name,separator,token=selector.partition('@')
    if not separator or name not in declared or not token.isdecimal():raise ValueError('Select a declared native quantity/component and exact ID')
    descriptor=declared[name];identity=int(token)
    root,record,settings,model,physics,damage=context(outcome,output)
    frames=FrameView(root,record['retained_native']['frames'],model,physics)
    begin=0 if start is None else start;end=len(frames) if stop is None else stop
    if type(begin) is not int or type(end) is not int or not 0<=begin<end<=len(frames):raise ValueError('Select a nonempty bounded sample slice')
    # A bounded sequence view, not a materialized list of every native frame.
    class Slice(Sequence):
        def __len__(self):return end-begin
        def __getitem__(self,i):
            if type(i) is not int or not 0<=i<len(self):raise IndexError(i)
            return frames[begin+i]
    from .impact_responses import read_selected
    row={'name':'selected','quantity':descriptor['quantity'],'identity':identity,'component':descriptor['component']}
    responses,_=read_selected(Slice(),model,[row],damage);response=responses['selected']
    source_entity=model.get('lineage',{}).get('nodes' if descriptor['association']=='POINTS' else 'elements',{}).get(str(identity))
    response.update(source={**descriptor['source'],'selector':selector,'sample_slice':[begin,end]},
                    metadata={**response['metadata'],'source_entity':deepcopy(source_entity),
                              'original_execution_status':record['execution_status'],'solver_execution':'NOT_PERFORMED'})
    return response
