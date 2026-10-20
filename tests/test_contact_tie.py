"""TIE contracts and native-shaped owner/Qt checks; solver outputs are explicit doubles."""
from copy import deepcopy
from types import SimpleNamespace as NS
import json
import pytest

from caelab.contact import default_contact, law_errors
from caelab.contact_deck import contact_cards, render, validate_model
from caelab.adapters.contact_results import write_post, read_dat, CHANNELS
from caelab.adapters.frozen_fem import read_frd
from test_contact_execution import model, native_outputs
from test_pre_fem_edit import native, Object, Shape, Quantity, region, submit


def tie_draft(**patch):
    return dict(default_contact(), normal_law='tie', tangential_law='tied',
                tie_tolerance_mm='.001234567890123', **patch)


def test_tie_requires_explicit_tolerance_and_no_contact_surrogates(model):
    d = tie_draft()
    assert law_errors(d) == []
    for patch, field in [({'tie_tolerance_mm':'1e'},'tie_tolerance_mm'),
                         ({'tie_tolerance_mm':0},'tie_tolerance_mm'),
                         ({'tie_tolerance_mm':1e-10},'tie_tolerance_mm'),
                         ({'tie_adjust':'yes'},'tie_adjust'),
                         ({'tangential_law':'coulomb'},'tangential_law'),
                         ({'gap_policy':'prescribed','nominal_gap_mm':'.01'},'gap_policy')]:
        draft = dict(d, **patch); before = deepcopy(draft)
        assert any(e['path'] == field for e in law_errors(draft))
        assert draft == before
    pair = model['contacts'][0]; linear = contact_cards(pair)
    pair['draft'] = d
    cards = contact_cards(pair)
    assert '*TIE, POSITION TOLERANCE=0.001234567890123, ADJUST=NO, NAME=TIEContact' in cards
    assert 'TIE_DEPContact, TIE_INDContact' in cards
    assert '*CONTACT PAIR' not in cards and '*FRICTION' not in cards
    text = render(model)
    assert '*CONTACT FILE' not in text and '*CONTACT PRINT' not in text
    assert '*NODE FILE,GLOBAL=YES\nU,RF\n*EL FILE\nS' in text
    pair['draft'] = dict(default_contact(), normal_law='linear', tangential_law='coulomb',
                         normal_stiffness_MPa_per_mm='1e5', friction_coefficient='.2', stick_stiffness_MPa_per_mm='5e4')
    assert contact_cards(pair) == linear


def test_tie_rejects_dependent_spc_duplicate_and_preserves_mixed_outputs(model):
    pair = model['contacts'][0]; pair['draft'] = tie_draft()
    slave = model['elements'][0]['node_ids'][0]
    model['boundary_dofs'].append({'node_id':slave,'component':1,'value_mm':0.})
    with pytest.raises(ValueError, match='변위 구속'):
        validate_model(model)
    model['boundary_dofs'].pop()
    duplicate = deepcopy(pair); duplicate['object_id'] = 'TieOther'
    model['contacts'].append(duplicate)
    with pytest.raises(ValueError, match='다른 묶음'):
        validate_model(model)
    model['contacts'].pop()
    linear = deepcopy(pair); linear['object_id'] = 'Linear'
    linear['draft'] = dict(default_contact(),normal_law='linear',tangential_law='frictionless',normal_stiffness_MPa_per_mm=1e5)
    model['contacts'].append(linear)
    deck = render(model)
    assert '*CONTACT PRINT,SLAVE=DEPLinear,MASTER=INDLinear' in deck
    assert '*CONTACT PRINT,SLAVE=DEPContact' not in deck


def _native_tie_outputs(model):
    """Independent fixed-column protocol fixture, not a physics calculation."""
    raw, _, materials = native_outputs(model)
    start = raw.index('    1PSTEP')
    lines = [line for line in raw[:start].splitlines() if 'INTCONTACT' not in line]
    materials['names'] = [n for n in materials['names'] if not n.startswith('INT')]
    from caelab.adapters.frozen_fem import _FRD_LABELS
    count = 0
    for inc, time in [(1,.5),(2,1.)]:
        for name, width in [('DISP',3),('FORC',3),('STRESS',6)]:
            count += 1
            lines += ['    1PSTEP'+' '*14+f'{count:12d}{inc:12d}{1:12d}'+' '*10,
                      '  100CL'+f'{100+inc:5d}{time:12.9f}{len(model["nodes"]):12d}'+' '*21+'0'+f'{inc:5d}'+' '*11+'1',
                      f' -4  {name:<12}{len(_FRD_LABELS[name])}    1']
            lines += [' -5  '+label for label in _FRD_LABELS[name]]
            lines += [' -1'+f'{n["node_id"]:10d}'+''.join(f'{j*time:12.5E}' for j in range(width)) for n in model['nodes']]
            lines.append(' -3')
    return '\n'.join(lines+[' 9999','']), materials


def test_tie_frd_requires_real_structural_fields_without_fake_contact(model,tmp_path):
    model['contacts'][0]['draft'] = tie_draft()
    raw, materials = _native_tie_outputs(model)
    path = tmp_path/'contact.frd'; path.write_text(raw,encoding='ascii')
    nodes, elements, _ = validate_model(model)
    with pytest.raises(ValueError,match='CONTACT'):
        read_frd(path,nodes,elements,contact_materials=materials)
    frames = read_frd(path,nodes,elements,contact_materials=materials,require_contact=False)['frames']
    assert set(frames[-1]['fields']) == {'DISP','FORC','STRESS'}
    assert read_dat(tmp_path/'absent.dat',model['contacts'],frames) == []
    metadata = write_post(tmp_path/'post',model,frames,[],provenance={'public_test_double':True})
    names = {a['name'] for a in metadata['arrays']}
    assert not names.intersection(CHANNELS)
    assert {'U_mm','FX_N','FY_N','FZ_N','SXX_MPa','SYZ_MPa'} <= names
    assert 'contact_inspection' not in metadata
    assert json.loads((tmp_path/'post/frame0002.json').read_text())['channels'] == []
    changed = raw.replace(f'{nodes[1][0]:12.5E}',f'{nodes[1][0]+1:12.5E}',1)
    path.write_text(changed,encoding='ascii')
    with pytest.raises(ValueError,match='coordinates'):
        read_frd(path,nodes,elements,contact_materials=materials,require_contact=False)


def install_tie(native, monkeypatch):
    import ObjectsFem
    monkeypatch.setattr(ObjectsFem, 'makeConstraintTie', lambda doc: Object(doc,'Tie','Fem::ConstraintPython',
        Proxy=NS(Type='Fem::ConstraintTie'),References=[],Tolerance=Quantity('0 mm'),Adjust=False,CyclicSymmetry=False),raising=False)
    editor = native.editor.contact
    from apps.desktop_pre.fem_edit import _target
    monkeypatch.setattr(editor,'snapshot',lambda obj,names,region_id=None:{'region_id':region_id,'label':obj.Label,
        'target':_target(obj,names),'faces':[{'name':n,'area_mm2':1.,'preview_points_mm':[],'preview_triangles':[]} for n in names]})
    second = Object(native.doc,'Base','Part::Feature',Shape=Shape('second'))
    a = region(native)
    b = submit(native,'region_set',{'label':'B 접합면','subelements':['Face1']},second)
    return a,b


@pytest.mark.parametrize('has_dat',[False,True])
def test_tie_adapter_execution_and_rebuild_preserve_only_requested_fields(model,tmp_path,monkeypatch,has_dat):
    from caelab.adapters import contact_fem
    from test_contact_steps import write_snapshot
    model['contacts'][0]['draft'] = tie_draft()
    snapshot = write_snapshot(model,tmp_path/'input')
    executable=tmp_path/'ccx.exe'; executable.write_bytes(b'EXPLICIT_PROCESS_DOUBLE')
    monkeypatch.setattr(contact_fem.shutil,'which',lambda name:str(executable))
    raw,_ = _native_tie_outputs(model)
    calls=[]
    def command(argv,cwd,label):
        calls.append(argv)
        (cwd/'contact.frd').write_text(raw,encoding='ascii')
        if has_dat:
            (cwd/'contact.dat').write_text('',encoding='ascii')
        return NS(returncode=0)
    monkeypatch.setattr(contact_fem,'run_owned_command',command)
    result=contact_fem.ContactFemCalculixAdapter().run({'snapshot_path':str(snapshot)},output=tmp_path/'run')
    assert result['execution_status']=='SUCCEEDED',result['diagnostics']
    assert set(result['responses'])=={'displacement','nodal_force','stress'}
    assert result['responses']['stress']['unit']=='MPa'
    assert result['responses']['nodal_force']['value'][0]==[0.,1.,2.]
    assert result['qualification']=='UNKNOWN' and len(calls)==1
    monkeypatch.setattr(contact_fem,'run_owned_command',lambda *a:pytest.fail('Reopen must not solve'))
    receipt=contact_fem.regenerate_post(tmp_path/'run',tmp_path/'reopened-post')
    assert receipt['solver_execution']=='NOT_PERFORMED'
    assert ('solver/contact.dat' in receipt['source_pins']) == has_dat
    assert not {a['name'] for a in receipt['post_artifact']['native_metadata']['arrays']}.intersection(CHANNELS)
    def missing(argv,cwd,label):
        command(argv,cwd,label)
        (cwd/'contact_WarnNodeMissTiedContact.nam').write_text('*NSET,NSET=WarnNodeMissTiedContact\n1,\n')
        return NS(returncode=0)
    monkeypatch.setattr(contact_fem,'run_owned_command',missing)
    rejected=contact_fem.ContactFemCalculixAdapter().run({'snapshot_path':str(snapshot)},output=tmp_path/'missing')
    assert rejected['execution_status']=='FAILED' and rejected['responses']=={}
    assert '허용거리' in rejected['diagnostics']['reason']
    assert (tmp_path/'missing/solver/contact.frd').exists()


def test_native_tie_draft_reopen_type_guard_and_failed_transaction(native,monkeypatch):
    a,b = install_tie(native,monkeypatch)
    editor = native.editor.contact
    d = dict(tie_draft(),a_region_id=a['id'],b_region_id=b['id'])
    record = editor.set(native.analysis,{'draft':d})
    obj = native._object(record['object_id'])
    assert obj.Proxy.Type == 'Fem::ConstraintTie' and not obj.Adjust
    assert obj.Tolerance.Value == pytest.approx(float(d['tie_tolerance_mm']))
    assert not editor.errors(record)
    record = editor.set(obj,{'draft':{'tie_tolerance_mm':'1e'}})
    from apps.desktop_pre.contact import ContactEditor
    reopened = ContactEditor(native.editor)
    assert reopened.descriptor()['pairs'][0]['draft']['tie_tolerance_mm'] == '1e'
    assert obj.Tolerance.Value == pytest.approx(float(d['tie_tolerance_mm']))
    record = editor.set(obj,{'draft':{'normal_law':'linear','normal_stiffness_MPa_per_mm':'1e5','tangential_law':'frictionless'}})
    assert obj.Proxy.Type == 'Fem::ConstraintTie'
    assert any(e['path']=='normal_law' for e in editor.errors(record))
    before = deepcopy(native.metadata)
    monkeypatch.setattr(native,'write_metadata',lambda data:(_ for _ in ()).throw(ValueError('save rejected')))
    with pytest.raises(ValueError,match='save rejected'):
        editor.set(obj,{'draft':{'normal_law':'tie','tangential_law':'tied','tie_tolerance_mm':'.02'}})
    assert native.metadata == before and obj.Tolerance.Value == pytest.approx(float(d['tie_tolerance_mm']))


def test_tie_step_prefix_keeps_converged_structural_fields_and_raw_source(model,tmp_path):
    from test_contact_steps import staged
    from caelab.contact_status import read_status, retained_prefix
    m=staged(model); m['contacts'][0]['draft']=tie_draft()
    text=render(m)
    assert text.count('*EL FILE,FREQUENCY=1\nS')==2
    assert '*CONTACT FILE' not in text and '*CONTACT PRINT' not in text
    raw,materials=_native_tie_outputs(m)
    path=tmp_path/'native.frd'; path.write_text(raw,encoding='ascii')
    status_path=tmp_path/'native.sta'; status_path.write_text(' 1 1 1 3 .5 .5 .5\n',encoding='ascii')
    status=read_status(status_path,m); nodes,elements,_=validate_model(m)
    before=path.read_bytes()
    parsed=retained_prefix(path,tmp_path/'prefix.frd',nodes,elements,materials,m,status)
    assert len(parsed['frames'])==1 and set(parsed['frames'][0]['fields'])=={'DISP','FORC','STRESS'}
    assert path.read_bytes()==before
    m['contacts'][0]['draft']=dict(default_contact(),normal_law='linear',tangential_law='frictionless',normal_stiffness_MPa_per_mm=1e5)
    with pytest.raises(ValueError,match='CONTACT'):
        retained_prefix(path,tmp_path/'linear-prefix.frd',nodes,elements,materials,m,status)


@pytest.mark.parametrize('cancelled',[False,True])
def test_unconnected_tie_never_becomes_a_converged_partial_result(model,tmp_path,monkeypatch,cancelled):
    from test_contact_steps import staged, write_snapshot
    from caelab.adapters import contact_fem
    from caelab.execution_control import ExecutionCancelled
    m=staged(model); m['contacts'][0]['draft']=tie_draft()
    snapshot=write_snapshot(m,tmp_path/'input')
    executable=tmp_path/'ccx.exe'; executable.write_bytes(b'EXPLICIT_PROCESS_DOUBLE')
    monkeypatch.setattr(contact_fem.shutil,'which',lambda name:str(executable))
    raw,_=_native_tie_outputs(m)
    def command(argv,cwd,label):
        (cwd/'contact.frd').write_text(raw,encoding='ascii')
        (cwd/'contact.sta').write_text(' 1 1 1 3 .5 .5 .5\n',encoding='ascii')
        (cwd/'contact_WarnNodeMissTiedContact.nam').write_text('*NSET,NSET=WarnNodeMissTiedContact\n1\n',encoding='ascii')
        if cancelled:
            raise ExecutionCancelled('Explicit process cancellation double')
        return NS(returncode=1)
    monkeypatch.setattr(contact_fem,'run_owned_command',command)
    result=contact_fem.ContactFemCalculixAdapter().run({'snapshot_path':str(snapshot)},output=tmp_path/'run')
    assert result['execution_status']==('CANCELLED' if cancelled else 'FAILED')
    assert result['responses']=={} and result['increment_history']['last_converged']
    assert 'post_artifact' not in result and 'partial_result' not in result
    assert '묶음' in result['diagnostics']['tie_readback']
    assert (tmp_path/'run/solver/contact.frd').read_text()==raw
