"""INP effective formulation scope; Python conversion, no native physics."""
from copy import deepcopy
import json
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace
import pytest
from caelab import impact_model
from caelab.adapters import impact_admission as admission
from examples.impact.pair_response import settings as pair_settings
ROOT=Path(__file__).resolve()
while not (ROOT/'caelab/impact_model.py').is_file():ROOT=ROOT.parent


def converted(folder,settings):
    folder.mkdir(parents=True,exist_ok=True)
    text,initial=impact_model.render(settings)
    model=impact_model.model_from_settings(settings)
    model={**model,'nodes':initial['nodes']}
    inp=folder/'test.inp';inp.write_text(text,encoding='ascii')
    subprocess.run([sys.executable,str(ROOT/'caelab/adapters/inp2rad_worker.py'),str(inp)],capture_output=True,check=True,timeout=30)
    original=(folder/'test_0000.rad').read_bytes()
    native,_=admission.global_gravity(original.decode('ascii'),settings['gravity_mm_s2'])
    native=admission.normalize_contact_friction(native,settings)
    native,_=admission.normalize_surfaces(native,model)
    return settings,model,initial,native,original


@pytest.fixture(scope='module')
def pair(tmp_path_factory):return converted(tmp_path_factory.mktemp('formulation-pair'),pair_settings())


def test_exact_default_elastic_pair_only_changes_complete_property_tetra_slots(pair):
    settings,model,initial,native,original=pair;before=deepcopy((settings,model,initial))
    effective,receipt=admission.normalize_elastic_tetra4(native,model,initial,settings)
    assert receipt['changed'] and not receipt['unchanged']
    assert sorted(e for r in receipt['changed'] for e in r['element_ids'])==[1,2]
    physics=admission.validate_physics(effective,model,initial,settings)
    assert physics['effective_formulation']['Itetra4_by_element']=={'1':1000,'2':1000}
    # Reversing only each declared ten-column slot reconstructs ALL original bytes.
    a=native.splitlines(keepends=True);b=effective.splitlines(keepends=True)
    changes=[i for i,(x,y) in enumerate(zip(a,b)) if x!=y]
    assert len(a)==len(b) and len(changes)==len(receipt['changed'])
    for i in changes:
        assert a[i][:60]==b[i][:60] and a[i][70:]==b[i][70:]
        assert int(a[i][60:70])==3 and int(b[i][60:70])==1000
    assert (settings,model,initial)==before and b'      1000' not in original
    again,second=admission.normalize_elastic_tetra4(effective,model,initial,settings)
    assert again==effective and not second['changed']
    # Same existing admitted native-direct formulation; no equivalence to Abaqus integration claimed.
    from caelab.impact_native import settings_from_source,parse_source
    from caelab.impact_source import capture
    path=ROOT/'examples/impact/input_a/native'
    direct=parse_source(settings_from_source(capture(path/'impact_0000.rad',path,engine=path/'impact_0001.rad',units='Mg/mm/s'))['source'])
    assert direct['physics']['effective_formulation']['Itetra4']==physics['effective_formulation']['Itetra4']==1000
    assert physics['effective_formulation']['Abaqus_integration_equivalence']=='NOT_CLAIMED'


def simple_settings(kind,plastic=False,mixed=False):
    s=impact_model.default_settings()
    points=[(0,0,0),(10,0,0),(0,10,0),(0,0,10),(5,0,0),(5,5,0),(0,5,0),(0,0,5),(5,0,5),(0,5,5)]
    brick=[(20,0,0),(30,0,0),(30,10,0),(20,10,0),(20,0,10),(30,0,10),(30,10,10),(20,10,10)]
    if kind=='C3D8':points=brick
    nodes=points+(brick if mixed else [])
    rows=['*NODE']+[str(i)+','+','.join(map(str,p)) for i,p in enumerate(nodes,1)]
    n={'C3D4':4,'C3D10':10,'C3D8':8}[kind]
    rows+=['*ELEMENT,TYPE='+kind+',ELSET=BODY','1,'+','.join(map(str,range(1,n+1)))]
    if mixed:rows+=['*ELEMENT,TYPE=C3D8,ELSET=BRICK','2,'+','.join(map(str,range(len(points)+1,len(points)+9)))]
    rows+=['*MATERIAL,NAME=MAT','*DENSITY','7.8e-9','*ELASTIC','210000,.3']
    if plastic:rows+=['*PLASTIC','200,0','210,.01']
    rows+=['*SOLID SECTION,ELSET=BODY,MATERIAL=MAT']
    if mixed:rows+=['*SOLID SECTION,ELSET=BRICK,MATERIAL=MAT']
    s['source']['text']='\n'.join(rows)+'\n'
    return s


@pytest.mark.parametrize('kind,plastic',[('C3D8',False),('C3D10',False),('C3D4',True)])
def test_other_element_and_plastic_law_are_untouched(tmp_path,kind,plastic):
    s,m,i,text,_=converted(tmp_path,simple_settings(kind,plastic))
    effective,receipt=admission.normalize_elastic_tetra4(text,m,i,s)
    assert effective==text and not receipt['changed']


def test_shared_property_does_not_change_other_elements(tmp_path):
    s,m,i,text,_=converted(tmp_path,simple_settings('C3D4',mixed=True))
    blocks=admission.cards(text);parts=[key for key in blocks if key.startswith('/PART/')]
    prop=admission._int(blocks[parts[0]][1][:10])
    # Both original element families now explicitly use one allowed default property.
    for key in parts[1:]:
        row=blocks[key][1];text=text.replace(row,f'{prop:10d}'+row[10:])
    effective,receipt=admission.normalize_elastic_tetra4(text,m,i,s)
    assert effective==text and not receipt['changed']
    assert any(r['element_ids']==[1,2] for r in receipt['unchanged'])


def test_explicit_compatible_strain_is_not_overridden(pair):
    s,m,i,text,_=pair
    for key,rows in admission.cards(text).items():
        if key.startswith('/PROP/SOLID/'):
            row=rows[1];text=text.replace(row,row[:10]+f'{2:10d}'+row[20:])
    effective,receipt=admission.normalize_elastic_tetra4(text,m,i,s)
    assert effective==text and not receipt['changed']


@pytest.mark.parametrize('change',['law','modulus','formulation'])
def test_unverified_law_material_or_formulation_rejected_before_rewrite(pair,change):
    s,m,i,text,_=pair;bad=text
    if change=='law':bad=text.replace('/MAT/ELAST/','/MAT/PLAS_TAB/')
    else:
        prefix='/MAT/ELAST/' if change=='modulus' else '/PROP/SOLID/'
        for key,rows in admission.cards(text).items():
            if key.startswith(prefix):
                row=rows[2 if change=='modulus' else 1]
                value=f'{220000:20.8e}'+row[20:] if change=='modulus' else f'{25:10d}'+row[10:]
                bad=bad.replace(row,value)
    assert bad!=text
    with pytest.raises(ValueError):admission.normalize_elastic_tetra4(bad,m,i,s)


def test_adapter_records_mapping_and_retains_original_conversion_without_native(tmp_path,monkeypatch):
    from caelab.adapters import impact
    s=pair_settings();before=deepcopy(s);calls=[]
    monkeypatch.setattr(impact,'selected_runtime',lambda:({'starter':'NO_NATIVE_STARTER','engine':'NO_NATIVE_ENGINE'},{},{'controlled_boundary':True}))
    def command(argv,folder,label,**kwargs):
        calls.append(label)
        if label=='convert':return subprocess.run(argv,cwd=folder,capture_output=True,timeout=30)
        assert label=='starter' # Intentionally stop here; never masquerade as a physical run.
        return SimpleNamespace(returncode=1)
    monkeypatch.setattr(impact,'run_owned_command',command)
    output=tmp_path/'adapter';result=impact.ImpactAdapter().run(s,output=output,runtime={'threads':1})
    assert calls==['convert','starter'] and result['execution_status']=='FAILED'
    record=json.loads((output/'physical_admission.json').read_text())
    assert record['inp_elastic_tetra_formulation']['changed']
    raw=admission.cards((output/'converted_0000.rad').read_text(encoding='ascii'))
    effective=admission.cards((output/'native/impact_0000.rad').read_text(encoding='ascii'))
    for item in record['inp_elastic_tetra_formulation']['changed']:
        key='/PROP/SOLID/'+str(item['property_id'])
        assert int(raw[key][1][60:70])==3 and int(effective[key][1][60:70])==1000
    assert s==before and (output/'original.inp').read_text(encoding='ascii')==s['source']['text']
