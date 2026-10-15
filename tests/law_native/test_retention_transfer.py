"""Actual research owners + explicitly controlled native transaction fixtures.

The fixtures are NOT FreeCAD/native FE runtime evidence.
"""
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
import json
import pytest
from caelab.workbench import Workbench
from caelab.storage import canonical_hash,save_json
from caelab.material_fe_transfer import source_snapshot,make_review,verify_review,cold_assignment,verify_source,enrich_command
from caelab import law_native_fe as fe
from plugins.material_point import law_native as law
from apps.desktop_pre import law_native_material as native


@pytest.fixture
def wb(tmp_path):
    instance=Workbench(tmp_path/'store')
    try:yield instance
    finally:assert instance.shutdown()['joined']


def cmd(wb,d,op,a=None,cid=None):
    return wb.document_command(d['id'],op,a or {},session_id=d['session_id'],
                              expected_generation=d['generation'],command_id=cid)


def saved_source(wb,model=law.dp.MODEL):
    d=wb.document_open(kind='material',draft={'backend':law.POINT,'settings':law.default_settings(model)})
    d=cmd(wb,d,'document.save')['document']
    source=source_snapshot(wb.material_documents,{'document_id':d['id'],'saved_revision':d['saved_revision'],
                                                'input_sha256':canonical_hash(d['draft'])})
    return d,source


def target():
    m=fe.cube_mesh()
    return {'document_id':'Ptest','session_id':'Sfixture','generation':0,
            'selection':dict(analysis_id='Analysis',material_id='Material',mesh_id='Mesh',solver_id='Solver',region_id='Rsolid'),
            'analysis_id':'Analysis','mesh':m,'mesh_sha256':canonical_hash(m),'admission_errors':[],
            'current_assignment_property':'','metadata_sha256':'fixture-exact-context'}


def review(source,t=None):
    s=fe.default_settings()
    return make_review(source,t or target(),{'solver':s['solver'],'boundary':s['boundary'],'purpose':'CONSTITUTIVE_SPECIMEN'})


def file_snapshot(root):
    snapshot={}
    for p in root.rglob('*'):
        if not p.is_file():continue
        relative=p.relative_to(root)
        if relative.as_posix()=='controller.lock':
            # Windows exclusively locks this live coordination file against byte reads.
            stat=p.stat();snapshot[str(relative)]=(stat.st_ino,stat.st_size,stat.st_mtime_ns)
        else:snapshot[str(relative)]=p.read_bytes()
    return snapshot


def test_actual_material_preview_is_pure_and_unit_conversion(wb):
    d,src=saved_source(wb);before=file_snapshot(wb.root);r=review(src)
    assert r['status']=='READY_FOR_EXPLICIT_APPLY'
    verify_review(r,target())
    assert file_snapshot(wb.root)==before and wb.manager.list()==[]
    s=deepcopy(d['draft']);s['settings']['stress_unit']='Pa'
    for k in ('E','k0','H'):s['settings']['parameters'][k]*=1e6
    from caelab.material_fe_transfer import map_to_mpa
    mapped,entries=map_to_mpa(s)
    assert mapped==d['draft']['settings']
    assert next(e for e in entries if e['coefficient']=='k0')['factor']==1e-6


@pytest.mark.parametrize('solver_id',['Material','Mesh'])
def test_native_capture_rejects_material_or_mesh_as_solver(monkeypatch,solver_id):
    material=SimpleNamespace(Name='Material',TypeId='Fem::MaterialCommon')
    mesh=SimpleNamespace(Name='Mesh',TypeId='Fem::FemMeshObject',FemMesh=object())
    objects={'Material':material,'Mesh':mesh}
    analysis=SimpleNamespace(Group=[material,mesh])
    fem=SimpleNamespace(owner=SimpleNamespace(_object=lambda name:objects[name],
        App=SimpleNamespace(Version=lambda:['1','1','4'])))
    monkeypatch.setattr(native,'_selection',lambda *args:analysis)
    selection=target()['selection'];selection['solver_id']=solver_id
    with pytest.raises(ValueError,match='CalculiX solver'):native.capture(fem,selection)


def test_source_revision_and_target_conflicts_are_not_rebased(wb):
    d,src=saved_source(wb);r=review(src)
    changed=target();changed['generation']+=1
    with pytest.raises(ValueError,match='TARGET_CONFLICT'):verify_review(r,changed)
    s=deepcopy(d['draft']);s['settings']['parameters']['k0']=300
    cmd(wb,d,'material.update',{'draft':s})
    with pytest.raises(ValueError,match='SOURCE_CONFLICT'):verify_review(r,target())
    assert r['source']['original_draft']['settings']['parameters']['k0']==250


def test_invalid_raw_saved_and_unavailable_strength_block(wb):
    d,src=saved_source(wb);draft=deepcopy(d['draft']);draft['settings']['parameters']['k0']='1e'
    changed=cmd(wb,d,'material.update',{'draft':draft})['document'];saved=cmd(wb,changed,'document.save')['document']
    assert saved['draft']==draft and saved['diagnostics']
    with pytest.raises(ValueError):cmd(wb,saved,'material.evaluate')
    source=source_snapshot(wb.material_documents,{'document_id':saved['id'],'saved_revision':saved['saved_revision'],
                                                 'input_sha256':canonical_hash(saved['draft'])})
    assert review(source)['status']=='BLOCKED'
    r=review(src);options=deepcopy(r['options']);options['purpose']='FAILURE_ASSESSMENT'
    assert make_review(src,target(),options)['status']=='BLOCKED'
    assert wb.manager.list()==[]


class NativeFixture:
    """Controlled transaction copy/abort only; never claims a FreeCAD operation."""
    def __init__(self):
        self.generation=0;self.data={};self.writes=0;self.fail_write=False
        self.base=SimpleNamespace(PropertiesList=[],CAELabLawNative='')
        self.base.addProperty=lambda kind,name,*args:self.base.PropertiesList.append(name)
        self.base.setEditorMode=lambda *a:None
        self.owner=SimpleNamespace(_object=lambda name:self.base,write_metadata=self.write)
    def _metadata(self):return deepcopy(self.data)
    def _assert_idle(self):pass
    def write(self,value):
        self.data=deepcopy(value);self.writes+=1
        if self.fail_write:raise RuntimeError('INJECTED_NATIVE_WRITE_FAILURE')
    def _transaction(self,title,change):
        old=deepcopy(self.data),self.base.CAELabLawNative,list(self.base.PropertiesList)
        try:change();self.generation+=1
        except Exception:
            self.data,self.base.CAELabLawNative,self.base.PropertiesList=old;raise
    def capture(self,selection):
        t=target();t['generation']=self.generation;t['current_assignment_property']=self.base.CAELabLawNative
        return t


def test_explicit_native_fixture_apply_freeze_cold_and_guard(wb,monkeypatch):
    d,src=saved_source(wb);f=NativeFixture();selection=target()['selection']
    monkeypatch.setattr(native,'capture',lambda fem,s:fem.capture(s))
    r=review(src);out=native.apply(f,selection,r)
    assert out['applied'] and not out['executed'] and f.generation==1
    settings=native.freeze(f,selection)['simulation_draft']['settings']
    assert settings['source_receipt']['review']==r
    fe.validate_settings(settings)
    changed=deepcopy(settings);changed['law']['parameters']['k0']=999
    with pytest.raises(ValueError,match='differs'):fe.validate_settings(changed)
    # A new Material draft does NOT change an already explicitly applied law.
    draft=deepcopy(d['draft']);draft['settings']['parameters']['k0']=300
    cmd(wb,d,'material.update',{'draft':draft})
    assert native.freeze(f,selection)['simulation_draft']['settings']['law']['parameters']['k0']==250
    f2=NativeFixture();f2.data=deepcopy(f.data);f2.base.CAELabLawNative=f.base.CAELabLawNative
    f2.base.PropertiesList=list(f.base.PropertiesList);f2.generation=0
    assert native.read(f2,selection)['assignment']==out['assignment']
    from caelab.material_fe_transfer import guard_other_export
    owner=SimpleNamespace(read_metadata=lambda:f.data)
    with pytest.raises(ValueError,match='LAW_NATIVE_INTERFACE_REQUIRED'):guard_other_export(owner,'Analysis')
    corrupted=deepcopy(out['assignment']);corrupted['review']['source']['original_draft']['settings']['parameters']['E']=1
    with pytest.raises(ValueError,match='hash'):cold_assignment(corrupted)


def test_native_fixture_failed_write_rolls_back_and_raw_draft_survives(wb,monkeypatch):
    d,src=saved_source(wb);f=NativeFixture();selection=target()['selection']
    monkeypatch.setattr(native,'capture',lambda fem,s:fem.capture(s))
    native.save(f,selection,{'literal_coefficient':'1e','source':src['reference']})
    before=deepcopy(f.data);r=review(src,f.capture(selection));f.fail_write=True
    with pytest.raises(RuntimeError,match='INJECTED'):native.apply(f,selection,r)
    assert f.data==before and f.base.CAELabLawNative=='' and f.generation==1


def test_actual_native_command_receipt_resolution_and_lost_ack(wb):
    d,src=saved_source(wb);nc=wb.native_commands
    descriptor={'id':'Ptest','kind':'pre','generation':0,'view_generation':0,'capabilities':list(native.OPERATIONS)}
    registration=nc.register(host_id='Hfixture',session_id='Sfixture',application='freecad',version='CONTROLLED_FIXTURE_NOT_FREECAD',
        execution_mode='headless',documents=[descriptor],registration_nonce='x'*64)
    args={'selection':target()['selection'],'source':src['reference'],'options':review(src)['options']}
    first=wb.document_command('Ptest','pre.fem.law_preview',args,session_id='Sfixture',expected_generation=0,command_id='Cpreview')
    entry=nc.next('Hfixture',session_id='Sfixture',host_token=registration['host_token'])
    # Native queue envelope key is verified below; not a hidden native evaluator.
    command=entry.get('command',entry)
    nc.event('Hfixture',session_id='Sfixture',host_token=registration['host_token'],event='started',command_id='Cpreview')
    r=review(command['arguments']['_source_snapshot'])
    nc.event('Hfixture',session_id='Sfixture',host_token=registration['host_token'],event='finished',command_id='Cpreview',
        outcome={'state':'SUCCEEDED','result':{'status':'COMPLETED','result':{'review':r}}},documents=[descriptor])
    apply_args={'selection':target()['selection'],'review_command_id':'Cpreview'}
    prior,enriched=enrich_command(wb,'Ptest','pre.fem.law_apply',apply_args,'Sfixture',0,'Capply')
    assert prior is None and enriched['_review']==r
    nc.submit('Ptest','pre.fem.law_apply',enriched,session_id='Sfixture',expected_generation=0,command_id='Capply')
    # Mutable source after a lost acknowledgment must not replace a queued receipt.
    draft=deepcopy(d['draft']);draft['settings']['parameters']['k0']=290
    cmd(wb,d,'material.update',{'draft':draft})
    receipt,args2=enrich_command(wb,'Ptest','pre.fem.law_apply',apply_args,'Sfixture',0,'Capply')
    assert args2 is None and receipt['command_id']=='Capply'
    with pytest.raises(ValueError,match='Private'):enrich_command(wb,'Ptest','pre.fem.law_apply',{'_review':r},'Sfixture',0,'Cinject')
