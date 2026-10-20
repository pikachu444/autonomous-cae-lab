"""Owner/deck regressions; native-shaped doubles, no FreeCAD or solver execution."""
from copy import deepcopy
import json
import pytest
from test_pre_fem_edit import native, Object
from test_contact_execution import model
from test_contact_steps import staged
from test_ns1_native_collect import native_fixture
from apps.desktop_pre import convergence as edit
from apps.desktop_pre import freeze_contact
from apps.desktop_pre.fem_edit import FEMEditor
from caelab.calculix_controls import default_draft, draft_errors, cards, resolved, validate_step_controls
from caelab.contact_deck import render


def draft():
    d=default_draft(['4,8,9,200,10,400,,200,,','0.25,0.5,0.75,0.85,,,1.5,'])
    d.update(field_use=True,field='0.005,0.01,,,0.02,1e-5,1e-3,1e-8')
    return d


def test_native_time_strings_preserved_and_freecad_defaults_not_ccx_defaults(native):
    n=native;d=draft()
    n.solver.IterationsControlParameterTimeUse=True
    n.solver.IterationsControlParameterIter=d['iterations']
    n.solver.IterationsControlParameterCutb=d['factors']
    info=edit.read(n.editor,n.solver,n.analysis.Name)
    assert info['draft']['iterations']==d['iterations']
    assert resolved({})['iterations']['ic']['value']==16
    assert not info['draft']['field_use']
    before=n.material.Material.copy()
    saved=edit.apply(n.editor,n.solver,n.analysis.Name,d)
    assert saved['applied'] and n.material.Material==before and n.metadata['keep_other_owner_field']
    effective=edit.effective(n.editor,n.analysis,n.solver)
    assert effective['controls']==[d['iterations'],d['factors']]
    assert cards(effective)==['*CONTROLS,PARAMETERS=TIME INCREMENTATION',d['iterations'],d['factors'],
        '*CONTROLS,PARAMETERS=FIELD',d['field']]
    assert resolved(effective)['iterations']['ic']['value']==200
    assert resolved(effective)['field']['qa0']['value']==0


@pytest.mark.parametrize('field,value,path',[
    ('field','nan','field.0'),('field','1e-','field.0'),('field','-1','field.0'),
    ('field','1.234567891234567e-05','field.0'),
    ('iterations','4,8,9,2e2','iterations.3'),('iterations','4,8,9,0','iterations.3'),
    ('iterations','4,8,9,16,10,4,1','iterations.6'),
    ('factors','1.0','factors.0'),('factors',',,,,,,1','factors.6'),
    ('field','0.005\n*STATIC','field'),('field',',,,,,,,1,2','field')])
def test_invalid_raw_draft_can_reopen_but_not_apply_or_export(native,field,value,path):
    n=native;d=draft();edit.apply(n.editor,n.solver,n.analysis.Name,d)
    old=deepcopy(n.metadata['convergence_drafts'][0]['applied_draft'])
    d[field]=value
    info=edit.save(n.editor,n.solver,n.analysis.Name,d)
    assert any(e['path']==path for e in info['errors'])
    n.metadata=json.loads(json.dumps(n.metadata));n.editor=FEMEditor(n)
    assert edit.read(n.editor,n.solver,n.analysis.Name)['draft']==d
    assert n.metadata['convergence_drafts'][0]['applied_draft']==old
    with pytest.raises(ValueError):edit.apply(n.editor,n.solver,n.analysis.Name,d)
    with pytest.raises(ValueError):edit.effective(n.editor,n.analysis,n.solver)


def test_external_native_change_requires_explicit_reapplication(native):
    n=native;d=draft();edit.apply(n.editor,n.solver,n.analysis.Name,d)
    n.solver.IterationsControlParameterIter='4,8,9,32,10,4,,5,,'
    before=deepcopy(n.metadata)
    with pytest.raises(ValueError,match='FreeCAD'):edit.effective(n.editor,n.analysis,n.solver)
    info=edit.read(n.editor,n.solver,n.analysis.Name)
    assert not info['applied'] and info['native']['iterations']!=d['iterations']
    d.update(info['native']);edit.apply(n.editor,n.solver,n.analysis.Name,d)
    assert edit.effective(n.editor,n.analysis,n.solver)['controls'][0]==d['iterations']
    assert before['convergence_drafts'][0]['applied_draft']['iterations']!=d['iterations']


def test_disabled_groups_preserve_drafts_without_emitting_them(native):
    n=native;d=draft();d.update(field_use=False,field='1e-',time_use=False)
    edit.apply(n.editor,n.solver,n.analysis.Name,d)
    assert cards(edit.effective(n.editor,n.analysis,n.solver))==[]
    assert edit.read(n.editor,n.solver,n.analysis.Name)['draft']['field']=='1e-'
    assert n.solver.IterationsControlParameterIter==d['iterations']


def test_supported_card_positions_blank_rows_and_line_search_contract(model):
    m=deepcopy(model);m['step'].update(edit._cards(draft()),line_search_controls=',.25,1.01,,')
    result=render(m)
    assert '*CONTROLS,PARAMETERS=LINE SEARCH\n,.25,1.01,,\n' in result
    assert '*STATIC' in result and 'STABILIZE' not in result
    m['contacts']=[]
    with pytest.raises(ValueError,match='LINE SEARCH'):validate_step_controls(m['step'],penalty=False)
    with pytest.raises(ValueError):validate_step_controls(m['step'],procedure='dynamic',penalty=True)
    with pytest.raises(ValueError):validate_step_controls({'line_search_controls':',2,1,,'},penalty=True)
    with pytest.raises(ValueError):validate_step_controls({'line_search_controls':'1,.25,1.01,,'},penalty=True)
    assert cards({'controls':['',''],'field_controls':''})==[
        '*CONTROLS,PARAMETERS=TIME INCREMENTATION',','*9,','*7,'*CONTROLS,PARAMETERS=FIELD',','*7]


def test_stage_cards_preserve_old_native_values_and_global_field_controls(model):
    m=staged(model);m['step'].update(edit._cards(draft()))
    d=render(m)
    assert d.count('*CONTROLS,PARAMETERS=FIELD\n'+draft()['field'])==2
    assert d.count('*CONTROLS,PARAMETERS=TIME INCREMENTATION\n'+draft()['iterations'])==2
    dynamic=staged(model,dynamic=True)
    dynamic['step']['controls']=[draft()['iterations'],draft()['factors']]
    assert render(dynamic).count('*DYNAMIC')==2  # Existing dynamic TIME path stays available.
    dynamic['step']['field_controls']='.005'
    deck=render(dynamic)
    assert deck.count('*DYNAMIC')==2
    assert deck.count('*CONTROLS,PARAMETERS=FIELD\n.005\n')==2
    assert deck.count('*CONTROLS,PARAMETERS=TIME INCREMENTATION\n'+draft()['iterations']+'\n'+draft()['factors'])==2
    dynamic['step']['line_search_controls']=',.25,1.01,,'
    with pytest.raises(ValueError,match='LINE SEARCH'):render(dynamic)


@pytest.mark.parametrize('single',[False,True])
def test_native_collect_and_freeze_use_exact_applied_snapshot_and_block_invalid(model,monkeypatch,tmp_path,single):
    n=native_fixture(model,monkeypatch,single)
    d=draft();n.solver.IterationsControlParameterTimeUse=True
    n.solver.IterationsControlParameterIter=d['iterations'];n.solver.IterationsControlParameterCutb=d['factors']
    n.metadata['convergence_drafts']=[{'analysis_id':'Analysis','solver_id':'Solver',
        'draft':deepcopy(d),'applied_draft':deepcopy(d),'applied_native':edit.signature(n.solver)}]
    actual,_=freeze_contact.collect(n.analysis,n.solver,n.fem)
    assert actual['step']['field_controls']==d['field']
    assert '*CONTROLS,PARAMETERS=FIELD\n'+d['field'] in render(actual)
    n.metadata['convergence_drafts'][0]['draft']['field']='1e-'
    with pytest.raises(ValueError):freeze_contact.collect(n.analysis,n.solver,n.fem)
    with pytest.raises(ValueError):freeze_contact.freeze_contact(n.analysis,n.solver,tmp_path/'blocked',fem=n.fem)
    assert not (tmp_path/'blocked').exists()
