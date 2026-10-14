"""Exact saved geometry and subprocess boundaries; native fields are explicit doubles."""
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace as NS
import json
import pytest
from test_contact_execution import model
from test_contact_steps import write_snapshot
from test_contact_tie import tie_draft, _native_tie_outputs, native, install_tie
from caelab.contact_deck import validate_model, render, contact_cards
from caelab.adapters.tie_adjustment import cases, expected_coordinates, retained_coordinates
from caelab.adapters.contact_fem import ContactFemCalculixAdapter, regenerate_post


def adjusted_model(model):
    m=deepcopy(model)
    for row in m['nodes']:
        if row['body_id']=='Pad':
            x,y,z=row['position_mm']
            row['position_mm']=[.4-.1*x,.2+.1*y,-.05-.2*(z+.25)]
            row['native_position_mm']=list(row['position_mm'])
    m['contacts'][0]['draft']=dict(tie_draft(),tie_adjust=True,tie_tolerance_mm='.06')
    return m


def test_adjust_admission_and_exact_standalone_program(model,tmp_path):
    m=adjusted_model(model); before=deepcopy(m)
    nodes,elements,_=validate_model(m)
    requests,rows=cases(m,nodes,elements)
    assert len(rows)==6 and all(p['point'][2]==-.05 for p in requests)
    expected,receipt=expected_coordinates(m,nodes,elements,tmp_path/'projection')
    assert all(expected[r['node_id']][2]==0. for r in rows)
    assert any(expected[r['node_id']][0]!=nodes[r['node_id']][0] for r in rows)  # Native search, not exact analytic projection.
    assert m==before
    reread,_=retained_coordinates(m,nodes,elements,tmp_path/'projection')
    assert reread==expected and receipt['expected_quality']['minimum_sampled_jacobian_mm3']>0
    assert 'ADJUST=NO' not in contact_cards(m['contacts'][0])
    assert '*TIE, POSITION TOLERANCE=0.06, NAME=' in render(m)
    m['contacts'][0]['draft']['tie_tolerance_mm']='.01'
    with pytest.raises(ValueError,match='큰 간극'):
        validate_model(m)


def test_adjust_rejects_boundary_curvature_overlap_and_chain(model):
    m=adjusted_model(model)
    for patch,match in [('boundary','경계'),('curved','중간절점'),('overlap','중복'),('chain','연쇄')]:
        bad=deepcopy(m)
        if patch=='boundary':
            bad['nodes'][0]['position_mm'][0]=0.; bad['nodes'][0]['native_position_mm'][0]=0.
        elif patch=='curved':
            node=next(r for r in bad['nodes'] if r['body_id']=='Base' and r['native_node_id']==5)
            node['position_mm'][2]=node['native_position_mm'][2]=.001
        elif patch=='overlap':
            face=bad['contacts'][0]['b']; face['element_faces'].append([2,1])
            # Test geometric admission directly: duplicate raw faces cannot become a unique candidate.
            nodes={r['node_id']:r['position_mm'] for r in bad['nodes']}; elements={r['element_id']:r['node_ids'] for r in bad['elements']}
            with pytest.raises(ValueError,match=match): cases(bad,nodes,elements)
            continue
        else:
            p=deepcopy(bad['contacts'][0]); p.update(object_id='Other',a=deepcopy(p['b']),b=deepcopy(p['a']))
            p['draft']['tie_adjust']=False
            bad['contacts'].append(p)
            nodes={r['node_id']:r['position_mm'] for r in bad['nodes']}; elements={r['element_id']:r['node_ids'] for r in bad['elements']}
            with pytest.raises(ValueError,match=match): cases(bad,nodes,elements)
            continue
        with pytest.raises(ValueError,match=match): validate_model(bad)


def test_adjust_adapter_strict_coordinate_check_post_and_reopen(model,tmp_path,monkeypatch):
    from caelab.adapters import contact_fem
    m=adjusted_model(model); snapshot=write_snapshot(m,tmp_path/'input')
    nodes,elements,_=validate_model(m)
    expected,_=expected_coordinates(m,nodes,elements,tmp_path/'reference-projection')
    raw,_=_native_tie_outputs(m)
    lines=raw.splitlines(); inside=False
    for i,line in enumerate(lines):
        if line.split()[:1]==['2C']: inside=True; continue
        if inside and line.strip()=='-3': break
        if inside:
            n=int(line[3:13]); lines[i]=' -1'+f'{n:10d}'+''.join(f'{v:12.5E}' for v in expected[n])
    frd='\n'.join(lines)+'\n'
    executable=tmp_path/'ccx.exe'; executable.write_bytes(b'EXPLICIT_PROCESS_DOUBLE')
    monkeypatch.setattr(contact_fem.shutil,'which',lambda name:str(executable))
    def command(argv,cwd,label):
        (cwd/'contact.frd').write_text(frd,encoding='ascii')
        return NS(returncode=0)
    monkeypatch.setattr(contact_fem,'run_owned_command',command)
    result=ContactFemCalculixAdapter().run({'snapshot_path':str(snapshot)},output=tmp_path/'run')
    assert result['execution_status']=='SUCCEEDED',result['diagnostics']
    metadata=result['post_artifact']['native_metadata']
    assert not metadata['geometry']['initial_adjustment_is_displacement']
    assert {'OriginalZ_mm','InitialAdjustmentZ_mm'}<={a['name'] for a in metadata['arrays']}
    detail=json.loads((tmp_path/'run/post/tie-adjustment.json').read_text())
    assert detail['rows'][0]['original_mm'][2]==-.05 and detail['rows'][0]['observed_mm'][2]==0.
    assert detail['rows'][0]['initial_adjustment_mm'][2]==.05
    monkeypatch.setattr(contact_fem,'run_owned_command',lambda *a:pytest.fail('Reopen must not solve'))
    reread=regenerate_post(tmp_path/'run',tmp_path/'reopened')
    assert reread['solver_execution']=='NOT_PERFORMED'
    assert json.loads((tmp_path/'reopened/tie-adjustment.json').read_text())==detail
    # A nearby unexpected movement is rejected with the original printed precision rule.
    moved=frd.replace(f'{expected[1][0]:12.5E}',f'{expected[1][0]+.001:12.5E}',1)
    def wrong(argv,cwd,label):
        (cwd/'contact.frd').write_text(moved,encoding='ascii'); return NS(returncode=0)
    monkeypatch.setattr(contact_fem,'run_owned_command',wrong)
    failed=ContactFemCalculixAdapter().run({'snapshot_path':str(snapshot)},output=tmp_path/'wrong')
    assert failed['execution_status']=='FAILED' and 'coordinates' in failed['diagnostics']['reason']
    assert failed['responses']=={} and (tmp_path/'wrong/frozen_input/contact.inp').is_file()


def test_adjust_native_choice_preserves_mesh_and_saved_boolean(native,monkeypatch):
    a,b=install_tie(native,monkeypatch); mesh=deepcopy(native.mesh.FemMesh.Nodes)
    record=native.editor.contact.set(native.analysis,{'draft':dict(tie_draft(),a_region_id=a['id'],b_region_id=b['id'],tie_adjust=True)})
    obj=native._object(record['object_id'])
    assert obj.Adjust is True and native.mesh.FemMesh.Nodes==mesh
    from apps.desktop_pre.contact import ContactEditor
    assert ContactEditor(native.editor).descriptor()['pairs'][0]['draft']['tie_adjust'] is True
    record=native.editor.contact.set(obj,{'draft':{'tie_adjust':False}})
    assert obj.Adjust is False and not record['draft']['tie_adjust']
