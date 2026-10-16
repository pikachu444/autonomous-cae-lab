"""Retained public CCX2.22 output: no new solver invocation."""
from pathlib import Path
from copy import deepcopy
import hashlib,json
import pytest
from caelab.adapters.pretension_results import solver_mesh,read,attach_nodal_resultants,responses
from caelab.adapters.frozen_fem import read_frd
from caelab.contact_deck import validate_model
from caelab.contact_steps import profile

FIXTURE=Path(__file__).parent/'fixtures/pretension'

def actual():
 model=json.loads((FIXTURE/'mesh.json').read_text(encoding='utf-8'))
 nodes,elements,_=validate_model(model);effective,nodes,elements,copies=solver_mesh(model,nodes,elements)
 parsed=read_frd(FIXTURE/'contact.frd',nodes,elements,
    contact_materials={'names':['M1'],'elements':{1:'M1',2:'M1'}},contact_profile=profile(model),require_contact=False)
 return model,parsed['frames']


def test_exact_native_cut_hold_force_and_stress_integral_are_distinct():
 pins={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in FIXTURE.iterdir() if p.is_file()}
 model,frames=actual();rows=attach_nodal_resultants(model,read(FIXTURE/'contact.dat',model,frames),frames)
 assert [r['assembled_cut_axis_N'] for r in rows]==pytest.approx([599.9996,599.9996,664.0905])
 assert [r['opposite_cut_axis_N'] for r in rows]==pytest.approx([-599.9996,-599.9996,-664.0905])
 assert [r['axial_force_N'] for r in rows]==[-1200.021,-1200.021,-1328.204]
 assert [r['rp_reaction_N'][0] for r in rows]==[-58.77743,-58.77743,-65.05591]
 assert all(r['rp_displacement_mm'][0]==.09361733 for r in rows)
 assert all(r['cut_pair_axis_differential_mm']==pytest.approx([.0936174]*6,abs=1e-12) for r in rows)
 assert all(r['support_nodal_axis_forces_N']['Top']['value']==pytest.approx(v)
    for r,v in zip(rows,[600.,600.,664.091]))
 result=responses(model,rows,frames)
 assert result['Pbolt.axial_force']['value']==pytest.approx([599.9996,599.9996,664.0905])
 assert result['Pbolt.stress_integral_axis']['value'][0]==-1200.021
 assert result['Pbolt.axial_force']['measure']!=result['Pbolt.stress_integral_axis']['measure']
 assert pins=={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in FIXTURE.iterdir() if p.is_file()}


def test_missing_rp_or_ambiguous_native_time_never_fills_zero(tmp_path):
 model,frames=actual();raw=(FIXTURE/'contact.dat').read_text(encoding='ascii')
 missing=tmp_path/'missing.dat';missing.write_text(raw[:raw.rfind(' displacements')],encoding='ascii')
 with pytest.raises(ValueError):read(missing,model,frames)
 duplicate=deepcopy(frames);duplicate.append(deepcopy(frames[0]));duplicate[-1]['static']['increment']=2
 with pytest.raises(ValueError,match='유일'):read(FIXTURE/'contact.dat',model,duplicate)


def test_missing_selected_clone_forc_is_rejected_not_sum_of_available_nodes():
 model,frames=actual();rows=read(FIXTURE/'contact.dat',model,frames);del frames[0]['fields']['FORC'][16]
 with pytest.raises(ValueError,match='누락'):attach_nodal_resultants(model,rows,frames)


@pytest.mark.parametrize('cancelled',[False,True])
def test_failed_native_attempt_preserves_committed_cut_prefix_without_rerun(tmp_path,monkeypatch,cancelled):
 from types import SimpleNamespace as NS
 from caelab.storage import save_json
 from caelab.native_cad import sha
 from caelab.adapters import contact_fem
 from caelab.adapters.pretension_fem import PretensionFemCalculixAdapter
 import shutil
 source=tmp_path/'input';source.mkdir();model=json.loads((FIXTURE/'mesh.json').read_text(encoding='utf-8'))
 for name in ('mesh.json','contact.inp'):shutil.copyfile(FIXTURE/name,source/name)
 (source/'editable.FCStd').write_bytes(b'CONTROLLED_NATIVE_EXPORT_ONLY')
 save_json(source/'snapshot.json',{'kind':'freecad-contact-frozen','schema_version':'1','id':'Ffixture','input_file':'contact.inp',
  'bodies':[{'body_id':b} for b in sorted({r['body_id'] for r in model['nodes']})],
  'files':[{'relative':p.name,'bytes':p.stat().st_size,'sha256':sha(p)} for p in source.iterdir()]})
 exe=tmp_path/'controlled-ccx.exe';exe.write_bytes(b'NOT_EXECUTED');monkeypatch.setattr(contact_fem.shutil,'which',lambda name:str(exe))
 calls=[]
 def native_double(command,cwd,label,**kw):
  calls.append(label)
  if label.endswith('_version'):return NS(returncode=201,stdout='This is Version 2.22\n',stderr='')
  for name in ('contact.dat','contact.frd','contact.sta'):shutil.copyfile(FIXTURE/name,Path(cwd)/name)
  if cancelled:
   from caelab.execution_control import ExecutionCancelled
   raise ExecutionCancelled('CONTROLLED_CANCELLED_WITH_RETAINED_NATIVE_FIXTURE')
  return NS(returncode=1,stdout='CONTROLLED_FAILURE_WITH_RETAINED_NATIVE_FIXTURE',stderr='')
 monkeypatch.setattr(contact_fem,'run_owned_command',native_double)
 result=PretensionFemCalculixAdapter().run({'data_id':'Dfixture','snapshot_path':str((source/'snapshot.json').resolve())},output=tmp_path/'attempt')
 assert calls==['ccx_contact_extension_version','ccx_contact']
 assert result['execution_status']==('CANCELLED' if cancelled else 'FAILED') and result['partial_result']['complete_analysis'] is False
 assert result['responses']['Pbolt.axial_force']['value']==pytest.approx([599.9996,599.9996,664.0905])
 assert result['responses']['Pbolt.axial_force']['metadata']['raw_rows']=='partial/pretension_resultants.json'
 assert (tmp_path/'attempt/partial/pretension_resultants.json').is_file()
 assert (tmp_path/'attempt/solver/contact.frd').read_bytes()==(FIXTURE/'contact.frd').read_bytes()
