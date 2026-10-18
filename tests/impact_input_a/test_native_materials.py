from copy import deepcopy
import pytest
from native_material_fixtures import make_native
from caelab.impact_native import parse_source, settings_from_source, edit_field, export_direct
from caelab.impact_input_edits import original_files, edited_files, replace_range
from caelab.impact_model import validate_settings
from caelab.storage import canonical_hash
from caelab.impact_source import SourceError


@pytest.fixture(scope='module')
def native_sources(tmp_path_factory):
    root=tmp_path_factory.mktemp('native-materials')
    return {kind:make_native(root/kind,kind)[3] for kind in ('bulk','interface','mixed')}


def changed_card(source,prefix,row,start,end,replacement):
    from caelab.impact_input_edits import original_offset
    card=next(card for card in parse_source(source)['cards'] if card['key'].startswith(prefix))
    where=card['rows'][row]['origin'];raw=edited_files(source)[where['file']]
    offset=sum(len(line) for line in raw.splitlines(keepends=True)[:where['line']-1])
    return replace_range(source,where['file'],original_offset(source,where['file'],offset+start),
        original_offset(source,where['file'],offset+end),replacement,reason='UNIT 명시 반례',expected_source_sha256=canonical_hash(source))


@pytest.mark.parametrize('kind',['bulk','interface'])
def test_existing_public_native_material_import_exact_edit_and_export(tmp_path, kind):
    declared, model, definition, source = make_native(tmp_path/'input',kind)
    parsed = parse_source(source)
    assert parsed['model']['nodes'] == model['nodes']
    assert parsed['model']['assignment'] == model['assignment']
    assert {e:row['nodes'] for e,row in parsed['model']['elements'].items()} == {e:row['nodes'] for e,row in model['elements'].items()}
    settings = settings_from_source(source); validate_settings(settings)
    key = 'gf_n_mm' if kind=='bulk' else 'normal_strength_mpa'
    field = next(f for f in parsed['fields'] if f['field']==key)
    value = .025 if kind=='bulk' else 2.1
    changed = edit_field(settings,field['id'],value,reason='명시 물성 수정',expected_source_sha256=canonical_hash(source))
    validate_settings(changed)
    assert changed['source']['bundle']==source['bundle']
    assert original_files(changed['source'])==original_files(source)
    assert len(changed['source']['edits'])==1
    path = tmp_path/'export'; receipt=export_direct(changed,path)
    assert receipt['converter_execution']=='NOT_PERFORMED'
    for name,raw in edited_files(changed['source']).items(): assert (path/name).read_bytes()==raw
    assert not list(path.rglob('*.inp'))
    with pytest.raises(ValueError):edit_field(changed,field['id'],value,reason='stale',expected_source_sha256=canonical_hash(source))


@pytest.mark.parametrize('kind,prefix,row,start,end,value',[
    ('bulk','/FAIL/INIEVO/',0,0,10,'1.00000001'),
    ('bulk','/FAIL/INIEVO/',0,70,80,'       2.0'),
    ('bulk','/FAIL/INIEVO/',0,30,70,' '*39+'1'),
    ('bulk','/FAIL/INIEVO/',1,10,20,'         3'),
    ('bulk','/FAIL/INIEVO/',3,0,10,'         1'),
    ('bulk','/FAIL/INIEVO/',4,40,60,'  0.000000000000e+00'),
    ('bulk','/MAT/PLAS_TAB/',2,40,60,'  1.000000000000e+00'),
    ('bulk','/MAT/PLAS_TAB/',3,0,10,'         2'),
    ('bulk','/TABLE/1/',2,20,40,' -1.000000000000e-03'),
    ('bulk','/TH/BRIC/',3,0,10,'       999'),
    ('interface','/MAT/LAW117/',2,40,50,'       2.0'),
    ('interface','/MAT/LAW117/',2,40,50,'2.00000001'),
    ('interface','/MAT/LAW117/',3,0,10,'         1'),
    ('interface','/MAT/LAW117/',4,0,20,'  1.000000000000e-03'),
    ('interface','/PROP/TYPE43/',1,0,10,'         1'),
])
def test_native_material_fixed_profile_rejects_actual_options(native_sources,kind,prefix,row,start,end,value):
    source=changed_card(native_sources[kind],prefix,row,start,end,value)
    with pytest.raises((SourceError,ValueError)) as failure:parse_source(source)
    assert str(failure.value)


def test_native_mixed_laws_and_exact_scope_receipts(native_sources):
    source=native_sources['mixed'];parsed=parse_source(source);settings=settings_from_source(source)
    validate_settings(settings)
    definition=parsed['b_definition']
    assert set(definition['bulk']['elements'])=={'1','3'}
    assert set(definition['cohesive']['elements'])=={'2'}
    assert {row['material_id'] for row in definition['cohesive']['elements'].values()}=={2}
    assert '/FAIL/INIEVO/1' in parsed['starter_text'] and '/MAT/LAW117/2' in parsed['starter_text']
    assert settings['bulk_damage'][0]['initiation']['rates_s_inv']==[0.,100.]
    assert settings['bulk_damage'][0]['calibration']['temperature_range_K'] is None
    assert 'UNKNOWN' in settings['bulk_damage'][0]['calibration']['source']
    # The runtime deck is never replaced by the private pre-extension check copy.
    assert parsed['starter_text']==source['text'] and '/MAT/LAW59/' not in source['text']
    raw=original_files(source)['impact_0000.rad'];position=raw.index(b'/FAIL/INIEVO/1')
    wrong=replace_range(source,'impact_0000.rad',position,position+len('/FAIL/INIEVO/1'),'/FAIL/INIEVO/2',reason='UNIT wrong material',expected_source_sha256=canonical_hash(source))
    with pytest.raises(ValueError):parse_source(wrong)


def test_source_authority_selections_sets_and_unknown_bytes(native_sources,tmp_path):
    from caelab.impact_input_workflow import apply_native_field,apply_effective_text,inspect
    source=native_sources['bulk'];settings=settings_from_source(source)
    for key in ('bulk_damage','cohesive','interface_controls'):
        stale=deepcopy(settings);stale[key]=[] if settings.get(key) else [{'unsupported':'separate override'}]
        with pytest.raises(ValueError,match='원문'):validate_settings(stale)
    parsed=parse_source(source);field=next(f for f in parsed['fields'] if f['field']=='member_1')
    with pytest.raises(ValueError):edit_field(settings,field['id'],1.2,reason='fractional ID',expected_source_sha256=canonical_hash(source))
    # Advanced source keeps unadmitted cards and exposes an actionable execution blocker.
    buffer=source['text'];raw=original_files(source)['impact_0000.rad'];position=raw.index(b'/END')
    result=apply_effective_text(settings,file='impact_0000.rad',start=position,end=position,replacement='/UNIT/9\n',reason='explicit unsupported card',expected_definition_sha256=canonical_hash(settings))
    assert result['inspection']['readiness']=='BLOCKED'
    assert b'/UNIT/9' in edited_files(result['settings']['source'])['impact_0000.rad']
    assert result['settings']['source']['bundle']==source['bundle']
    with pytest.raises(ValueError):export_direct(result['settings'],tmp_path/'blocked')


def test_native_b_selects_only_exact_actual_material_members(native_sources):
    from caelab.impact_native_b import select_material_response
    for kind,scope,identity,quantity in [('bulk','bulk',1,'active'),('interface','interface',2,'cohesive_active')]:
        settings=settings_from_source(native_sources[kind])
        chosen=select_material_response(settings,scope=scope,native_element_id=identity,quantity=quantity,component='scalar',name='selected')
        assert chosen['source']==settings['source'] and chosen['b_responses']==[{'name':'selected','scope':scope,'identity':identity,'quantity':quantity,'component':'scalar'}]
        assert not settings.get('b_responses')
        with pytest.raises(ValueError):select_material_response(settings,scope=scope,native_element_id=999,quantity=quantity,component='scalar',name='wrong')


def test_native_material_failed_runtime_and_cancel_keep_input(native_sources,tmp_path,monkeypatch):
    from caelab.adapters.impact import ImpactAdapter
    from caelab.execution_control import CancellationToken,cancellation_scope,ExecutionCancelled
    def missing():raise FileNotFoundError('UNIT deliberately unavailable runtime')
    def forbidden(*a,**k):raise AssertionError('No converter/solver is authorized for this negative case')
    monkeypatch.setattr('caelab.adapters.impact.run_owned_command',forbidden)
    for kind in ('bulk','interface'):
        monkeypatch.setattr('caelab.adapters.impact.selected_runtime',missing)
        settings=settings_from_source(native_sources[kind]);before=deepcopy(settings)
        folder=tmp_path/kind;result=ImpactAdapter().run(settings,output=folder)
        assert result['execution_status']=='FAILED' and result['diagnostics']['native_execution_status']=='NOT_STARTED'
        assert result['diagnostics']['last_phase']=='runtime' and 'unavailable runtime' in result['diagnostics']['reason']
        for name,raw in edited_files(settings['source']).items():assert (folder/'native'/name).read_bytes()==raw
        assert settings==before and (folder/'b_definition.json').is_file()
        token=CancellationToken();token.request()
        monkeypatch.setattr('caelab.adapters.impact.selected_runtime',lambda:({'starter':'UNUSED','engine':'UNUSED'},{},{'unit_only':True}))
        with cancellation_scope(token):cancelled=ImpactAdapter().run(settings,output=tmp_path/(kind+'-cancel'))
        assert token.observed and settings==before and cancelled['execution_status']=='CANCELLED'
        assert cancelled['diagnostics']['native_execution_status']=='NOT_STARTED'


def test_existing_native_delayed_contact_is_projected_without_rewrite(tmp_path):
    _,_,_,source=make_native(tmp_path/'delayed','delayed')
    settings=settings_from_source(source);parsed=parse_source(source)
    assert settings['interface_controls'][0]['contact_start_s']==.003
    assert parsed['starter_text']==source['text']
    control=parsed['b_definition']['interface']['controls'][0]
    assert control['gate']=='explicit native Tstart, not event-driven deletion'
    field=next(row for row in parsed['fields'] if row['field']=='contact_start_s')
    changed=edit_field(settings,field['id'],.0025,reason='원 접촉 시각 명시 편집',expected_source_sha256=canonical_hash(source))
    assert changed['interface_controls'][0]['contact_start_s']==.0025
    assert original_files(changed['source'])==original_files(source)
    validate_settings(changed)
    with pytest.raises(ValueError):edit_field(settings,field['id'],0,reason='중복 압축',expected_source_sha256=canonical_hash(source))


@pytest.mark.parametrize('numeric,title',[(True,False),(False,True),(True,True)])
def test_law117_legal_native_spelling_exact_snapshot_and_tamper(native_sources,tmp_path,numeric,title):
    from caelab.impact_b import verify
    source=deepcopy(native_sources['interface'])
    if numeric:source=changed_card(source,'/MAT/LAW117/',3,20,40,'                   2')
    if title:
        # Header/card syntax stays unchanged; the material's original title may be lowercase.
        source=changed_card(source,'/MAT/LAW117/',0,0,4,'bond')
    parsed=parse_source(source);definition=parsed['b_definition'];settings=settings_from_source(source)
    validate_settings(settings)
    actual=next(c for c in parsed['cards'] if c['key']=='/MAT/LAW117/2')
    assert definition['cohesive']['native_cards']['/MAT/LAW117/2']==[row['text'] for row in actual['rows']]
    path=tmp_path/'export';export_direct(settings,path)
    for name,raw in edited_files(source).items():assert (path/name).read_bytes()==raw
    verify(parsed['starter_text'],parsed['model'],settings,definition)
    # Even a semantically equal post-admission spelling change must break its exact receipt.
    token='                   2' if numeric else '  2.000000000000e+00'
    replacement='  2.000000000000e+00' if numeric else '                   2'
    tampered=parsed['starter_text'].replace(token,replacement,1)
    assert tampered!=parsed['starter_text']
    with pytest.raises(ValueError):verify(tampered,parsed['model'],settings,definition)


def test_native_constant_function_cannot_collide_with_initiation_table(native_sources):
    source=native_sources['bulk'];parsed=parse_source(source)
    tid=next(c['key'].rsplit('/',1)[1] for c in parsed['cards'] if c['key'].startswith('/TABLE/1/'))
    file='impact_0000.rad';raw=original_files(source)[file];position=raw.index(b'/END')
    addition='/FUNCT/'+tid+'\nUNRELATED CONSTANT\n'+f'{0.:20.12e}{1.:20.12e}\n{1.:20.12e}{1.:20.12e}\n'
    changed=replace_range(source,file,position,position,addition,reason='UNIT unrelated FUNCT namespace collision',expected_source_sha256=canonical_hash(source))
    with pytest.raises(SourceError,match='FUNCT.*TABLE') as caught:parse_source(changed)
    assert caught.value.file==file and caught.value.line==raw[:position].count(b'\n')+1
    assert caught.value.impact['card']=='/FUNCT/'+tid
