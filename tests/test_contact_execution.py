"""Focused retained/contact execution boundaries. Solver process is an explicit double."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace as NS
import pytest

from caelab.contact import separate_meshes, surface_union, default_contact
from caelab.contact_deck import UNITS, render, validate_model
from caelab.adapters import contact_fem
from caelab.adapters.contact_results import read_dat, geometric_gaps, CHANNELS
from caelab.adapters.frozen_fem import read_frd
from caelab.evaluation import normalize_evaluation
from caelab.execution_control import ExecutionCancelled


@pytest.fixture
def model():
    xyz = [(1,0,0),(0,0,0),(0,1,0),(0,0,1),(.5,0,0),(0,.5,0),(.5,.5,0),(.5,0,.5),(0,0,.5),(0,.5,.5)]
    bodies = [{'body_id': name, 'nodes': [{'node_id': n, 'position_mm': [x,y,z+offset]}
                for n,(x,y,z) in enumerate(xyz,1)],
               'elements': [{'element_id':73,'type':'C3D10','native_node_ids':list(range(1,11))}]}
              for name,offset in [('Pad',-.25),('Base',0)]]
    value = separate_meshes(bodies)
    for row in value['nodes']:
        row['native_position_mm'] = list(row['position_mm'])
    for row in value['elements']:
        row['type'] = 'C3D10'
    draft = dict(default_contact(), label='Pad contact', normal_law='linear', tangential_law='coulomb',
                 normal_stiffness_MPa_per_mm='1e5',friction_coefficient='.2',stick_stiffness_MPa_per_mm='5e4')
    faces = [{'face':'Face1','element_faces':[(73,1)]}]
    value.update(kind='freecad-contact-mesh',schema_version='1',units=dict(UNITS),
        materials=[{'body_id':name,'object_id':'Material','law':'isotropic_linear_elastic',
                    'young_modulus_MPa':1000.,'poisson_ratio':.3} for name in ('Pad','Base')],
        contacts=[{'object_id':'Contact','draft':draft,
                   'a':surface_union('Pad',faces,value['body_maps']),
                   'b':surface_union('Base',faces,value['body_maps'])}],
        boundary_dofs=[{'node_id':value['body_maps']['Base']['nodes'][n],'component':d,'value_mm':0.}
                       for n in (1,2,3) for d in (1,2,3)],
        loads=[{'node_id':value['body_maps']['Pad']['nodes'][4],'component':3,'force_N':-10.}],
        step={'initial':.5,'period':1.,'minimum':1e-6,'maximum':.5,'increments':100,
              'geometry':'nonlinear','automatic':True,'matrix_solver':'default','controls':None},
        conditions=[])
    return value


@pytest.fixture
def snapshot(model,tmp_path):
    folder=tmp_path/'input'
    folder.mkdir()
    (folder/'editable.FCStd').write_bytes(b'EXPLICIT_TEST_DOUBLE_NOT_NATIVE')
    (folder/'mesh.json').write_text(json.dumps(model),encoding='utf-8')
    (folder/'contact.inp').write_text(render(model),encoding='ascii',newline='\n')
    manifest={'kind':'freecad-contact-frozen','schema_version':'1','id':'Fcontact',
              'input_file':'contact.inp','bodies':[{'body_id':name} for name in ('Pad','Base')],
              'files':[{'relative':p.name,'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}
                       for p in sorted(folder.iterdir())]}
    path=folder/'snapshot.json'
    path.write_text(json.dumps(manifest),encoding='utf-8')
    return path


def native_outputs(model):
    """Fixed columns independently from official 2.22 writer, never solver acceptance."""
    nodes,elements,bodies=validate_model(model)
    names={body:i for i,body in enumerate(sorted(bodies),1)}
    material={row['element_id']:names[row['body_id']] for row in model['elements']}
    lines=['    1C','    1UPGM               CalculiX','    1UVERSION           Version 2.22']
    lines += [f'    1UMAT{i:5d}{("M"+str(i)):<58}' for i in names.values()]
    lines += [f'    1UMAT{len(names)+i:5d}{("INT"+pair["object_id"].upper()):<58}' for i,pair in enumerate(model['contacts'],1)]
    lines.append(f'    2C{len(nodes):30d}{1:38d}')
    def record(n,values):
        return ' -1'+f'{n:10d}'+''.join(f'{v:12.5E}' for v in values)
    lines += [record(n,xyz) for n,xyz in nodes.items()]
    lines += [' -3',f'    3C{len(elements):30d}{1:38d}']
    for e,ids in elements.items():
        lines += [' -1'+f'{e:10d}{6:5d}{0:5d}{material[e]:5d}',' -2'+''.join(f'{n:10d}' for n in ids)]
    lines.append(' -3')
    labels={'DISP':['D1 1 2 1 0','D2 1 2 2 0','D3 1 2 3 0','ALL 1 2 0 0 1ALL'],
            'CONTACT':['COPEN 1 1 0 0','CSLIP1 1 1 0 0','CSLIP2 1 1 0 0',
                       'CPRESS 1 1 0 0','CSHEAR1 1 1 0 0','CSHEAR2 1 1 0 0']}
    count,dat=0,[]
    for inc,time in [(1,.5),(2,1.)]:
        dat += [' S T E P 1',f' INCREMENT {inc}']
        for pair in model['contacts']:
            for key,force in [('CF',3.),('CFN',2.),('CFS',1.)]:
                dat += [f" statistics for slave set DEP{pair['object_id'].upper()}, master set IND{pair['object_id'].upper()} and time {time:.7E}",
                    '', ' total surface force (fx,fy,fz) and moment about the origin (mx,my,mz)', '',
                    f' 0 0 {force*time} 0 0 0', '', ' center of gravity and mean normal', '', ' 0 0 0 0 0 -1', '',
                    ' moment about the center of gravity(mx,my,mz)', '', ' 0 0 0', '',
                    ' area,  normal force (+ = tension) and shear force (size)', '', f' 1 {-force*time} 0']
        for name in ('DISP','CONTACT'):
            count+=1
            lines.append('    1PSTEP'+' '*14+f'{count:12d}{inc:12d}{1:12d}'+' '*10)
            lines.append('  100CL'+f'{100+inc:5d}{time:12.9f}{len(nodes):12d}'+' '*21+'0'+f'{inc:5d}'+' '*11+'1')
            lines.append(f' -4  {name:<12}{len(labels[name])}    1')
            lines += [' -5  '+label for label in labels[name]]
            for n in nodes:
                values=[0.,0.,0.] if name=='DISP' else [-1.2e-5*time,.01*time,-.02*time,12*time,-3*time,4*time]
                lines.append(record(n,values))
            lines.append(' -3')
    lines.append(' 9999')
    return '\n'.join(lines)+'\n','\n'.join(dat)+'\n',{'names':['M'+str(i) for i in names.values()]+['INT'+p['object_id'].upper() for p in model['contacts']],
        'elements':{e:'M'+str(i) for e,i in material.items()}}


def test_body_sections_surface_union_and_prescribed_dof_conflicts(model,snapshot):
    manifest,retained,pins,gates=contact_fem.validate_snapshot(snapshot)
    assert len(retained['nodes'])==20 and gates['mesh_components']==2
    assert render(model).count('*CONTACT PAIR')==1
    assert 'CF,CFN,CFS' in render(model)
    bad=deepcopy(model)
    bad['loads'].append({'node_id':bad['boundary_dofs'][0]['node_id'],'component':1,'force_N':1})
    with pytest.raises(ValueError,match='prescribed'):
        render(bad)
    bad=deepcopy(model)
    bad['materials'].pop()
    with pytest.raises(ValueError,match='material'):
        render(bad)
    # Repinning an extra card still cannot make it part of the supported operation.
    path=snapshot.parent/'contact.inp'
    path.write_text(path.read_text()+'\n*TIE\n',encoding='ascii')
    data=json.loads(snapshot.read_text())
    pin=next(p for p in data['files'] if p['relative']=='contact.inp')
    pin.update(bytes=path.stat().st_size,sha256=hashlib.sha256(path.read_bytes()).hexdigest())
    snapshot.write_text(json.dumps(data))
    with pytest.raises(ValueError,match='deck differs'):
        contact_fem.validate_snapshot(snapshot)


def test_frd_dat_exact_frame_channels_order_and_raw_signs(model,tmp_path):
    frd,dat,materials=native_outputs(model)
    f=tmp_path/'contact.frd';d=tmp_path/'contact.dat'
    f.write_text(frd);d.write_text(dat)
    nodes,elements,_=validate_model(model)
    parsed=read_frd(f,nodes,elements,contact_materials=materials)
    assert len(parsed['frames'])==2
    assert parsed['frames'][1]['fields']['CONTACT'][1]==[-1.2e-5,.01,-.02,12.,-3.,4.]
    rows=read_dat(d,model['contacts'],parsed['frames'])
    assert [row['quantity'] for row in rows]==['CF','CFN','CFS']*2
    assert rows[-3]['normal_projection_N']==-3. and rows[-3]['force_N'][2]==3.
    gaps=geometric_gaps(model,parsed['frames'][-1])
    finite=[row['value_mm'] for row in gaps['rows'] if row['quality_valid']]
    assert finite and all(value==pytest.approx(.25) for value in finite)
    assert gaps['recipe']['solver_active_state']=='UNKNOWN'
    d.write_text(dat.rsplit(' area,',1)[0])
    with pytest.raises(ValueError,match='headings|Truncated|Incomplete'):
        read_dat(d,model['contacts'],parsed['frames'])
    f.write_text(frd.replace('CSHEAR1','CSHEARX'))
    with pytest.raises(ValueError,match='component'):
        read_frd(f,nodes,elements,contact_materials=materials)


def test_managed_contact_adapter_retains_exact_outputs_and_series_without_physical_clock(model,snapshot,tmp_path,monkeypatch):
    executable=tmp_path/'ccx'
    executable.write_bytes(b'EXPLICIT_SOLVER_PROCESS_DOUBLE')
    monkeypatch.setattr(contact_fem.shutil,'which',lambda name:str(executable))
    frd,dat,_=native_outputs(model)
    calls=[]
    def command(argv,cwd,label):
        calls.append((argv,cwd,label))
        (cwd/'contact.frd').write_text(frd)
        (cwd/'contact.dat').write_text(dat)
        return NS(returncode=0)
    monkeypatch.setattr(contact_fem,'run_owned_command',command)
    result=normalize_evaluation(contact_fem.ContactFemCalculixAdapter().run(
        {'snapshot_path':str(snapshot),'data_id':'Dcontact'},output=tmp_path/'run'))
    assert result['execution_status']=='SUCCEEDED',result['diagnostics']
    assert len(calls)==1 and calls[0][0][-2:]==['-i','contact']
    curve=result['responses']['Contact.CF.FZ']
    assert curve['kind']=='series' and curve['value']==[1.5,3.]
    assert curve['axes']==[{'name':'load_parameter','unit':'1','values':[.5,1.]}]
    metadata=result['post_artifact']['native_metadata']
    assert metadata['static'] is None and metadata['time']=={
        'unit':'1','semantics':'STATIC_LOAD_PARAMETER','values':[.5,1.]}
    assert result['decision']=='NOT_RELEASED' and not result['engineering_valid']
    assert (tmp_path/'run/post/frame0002.vtu').exists()
    assert (tmp_path/'run/solver/contact.dat').read_text()==dat
    old=json.loads((tmp_path/'run/contact_execution.json').read_text())
    assert old['contact_outputs']['active_state']=='UNKNOWN'
    def cancel(*args):
        raise ExecutionCancelled('Explicit cancellation double')
    monkeypatch.setattr(contact_fem,'run_owned_command',cancel)
    cancelled=contact_fem.ContactFemCalculixAdapter().run({'snapshot_path':str(snapshot)},output=tmp_path/'cancelled')
    assert cancelled['execution_status']=='CANCELLED' and cancelled['responses']=={}
    assert (tmp_path/'cancelled/frozen_input/contact.inp').exists()
    assert (tmp_path/'run/contact_execution.json').exists()


def test_contact_snapshot_reuses_registered_native_input_and_keeps_original_files(snapshot,tmp_path):
    from caelab.native_inputs import register_frozen_input
    from caelab.native_commands import CAPABILITIES
    receipt=register_frozen_input(tmp_path/'store',snapshot.parent,snapshot,'Dcontact',
        root_id='explicit-test',relative='snapshot.json',limit=16*1024**2)
    assert receipt['kind']=='frozen_contact'
    retained=tmp_path/'store'/receipt['file']
    assert contact_fem.validate_snapshot(retained)[0]['id']=='Fcontact'
    assert {'pre.contact.freeze','pre.contact.set','pre.contact.preview_rebind'} <= CAPABILITIES['pre']
    assert snapshot.exists()


def test_contact_coverage_and_invalid_tokens_remain_distinct_from_measured_zero(model,tmp_path):
    text,dat,materials=native_outputs(model)
    lines=text.splitlines()
    begin=next(i for i,line in enumerate(lines) if line.startswith(' -4  CONTACT'))
    header=begin-1
    # One CONTACT row is genuinely absent in its explicitly declared coverage.
    start=begin+7
    removed=lines.pop(start+1)
    lines[header]=lines[header][:24]+f'{19:12d}'+lines[header][36:]
    # Node1 has a native NaN normal displacement and actual zero tangential slip.
    line=lines[start]
    lines[start]=line[:13]+'         NaN'+f'{0.:12.5E}'+line[37:]
    path=tmp_path/'partial.frd'
    path.write_text('\n'.join(lines)+'\n')
    nodes,elements,_=validate_model(model)
    observed=read_frd(path,nodes,elements,contact_materials=materials)
    first=observed['frames'][0]
    assert first['fields']['CONTACT'][1][0] is None
    assert first['fields']['CONTACT'][1][1]==0.
    assert 2 not in first['fields']['CONTACT']
    assert first['contact_tokens'][1][0]=='NaN'
    # Missing rows contrary to the written coverage remain a malformed field.
    lines[header]=lines[header][:24]+f'{20:12d}'+lines[header][36:]
    path.write_text('\n'.join(lines)+'\n')
    with pytest.raises(ValueError,match='coverage'):
        read_frd(path,nodes,elements,contact_materials=materials)



def test_native_face_force_table_values_are_already_newtons():
    from apps.desktop_pre.freeze_contact import _native_force_table

    class ConvertedQuantity:
        """Explicit FreeCAD getValueAs result double: Value has no unit."""
        def __init__(self, value):
            self.Value = value

        def getValueAs(self, unit):
            pytest.fail('Native integrated nodal forces must not be converted twice')

    table = [('Face1', {1: ConvertedQuantity(2.), 2: ConvertedQuantity(3.)}),
             ('Face9', {1: ConvertedQuantity(1.), 3: ConvertedQuantity(4.)})]
    assert _native_force_table(table) == {1: 3., 2: 3., 3: 4.}
    assert sum(_native_force_table(table).values()) == 10.
    assert _native_force_table([('Face1', {1: ConvertedQuantity(-2.)})]) == {1: -2.}
    with pytest.raises(ValueError):
        _native_force_table([('Face1', {1: ConvertedQuantity(float('nan'))})])



def test_dat_frame_match_uses_both_native_print_precisions(model, tmp_path):
    frd, dat, materials = native_outputs(model)
    # Official formats print the same physical increment at different precision.
    frd = frd.replace(f'{.5:12.9f}', ' 1.23457E-01')
    dat = dat.replace('5.0000000E-01', '0.1234568E+00')
    f, d = tmp_path/'contact.frd', tmp_path/'contact.dat'
    f.write_text(frd, encoding='ascii')
    d.write_text(dat, encoding='ascii')
    nodes, elements, _ = validate_model(model)
    frames = read_frd(f, nodes, elements, contact_materials=materials)['frames']
    rows = read_dat(d, model['contacts'], frames)
    assert len(rows) == 6
    assert rows[0]['static'] == frames[0]['static']
    assert '0.1234568E+00' in rows[0]['raw_text']
    # Adjacent wrong increments remain rejected, rather than using a broad tolerance.
    d.write_text(dat.replace('0.1234568E+00', '0.1234588E+00'), encoding='ascii')
    with pytest.raises(ValueError, match='actual FRD frame'):
        read_dat(d, model['contacts'], frames)
