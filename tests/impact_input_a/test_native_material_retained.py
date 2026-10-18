"""Real existing B reader and pinned include artifacts; synthetic TH, no solver."""
from copy import deepcopy
from pathlib import Path
import re
import runpy
import pytest
from native_material_fixtures import make_native
from caelab.impact_source import capture
from caelab.impact_native import parse_source,settings_from_source,export_direct
from caelab.impact_native_b import select_material_response
from caelab.impact_retained import artifact_receipt
from caelab.dynamic_result_store import file_pin
from caelab.impact_b import append_readback
from caelab.storage import save_json

history_bytes=runpy.run_path(str(Path(__file__).resolve().parents[1]/'impact_b_fixtures.py'))['history_bytes']


@pytest.fixture(scope='module')
def with_card_include(tmp_path_factory):
    result={}
    for target in ('MAT','BRICK'):
        folder=tmp_path_factory.mktemp('native-'+target)
        make_native(folder/'input','bulk');root=folder/'input';path=root/'impact_0000.rad'
        raw=path.read_bytes()
        matches=list(re.finditer(br'(?m)^/[^\r\n]+',raw))
        index=next(i for i,m in enumerate(matches) if m.group().startswith(('/MAT/PLAS_TAB/' if target=='MAT' else '/BRICK/').encode('ascii')))
        start=matches[index].start();end=matches[index+1].start()
        (root/'material-or-mesh.inc').write_bytes(raw[start:end])
        path.write_bytes(raw[:start]+b'#include material-or-mesh.inc\r\n'+raw[end:])
        source=capture(path,root,engine=root/'impact_0001.rad',units='Mg/mm/s')
        parsed=parse_source(source)
        assert any(card['origin']['file']=='material-or-mesh.inc' for card in parsed['cards'])
        assert parsed['b_definition']['bulk']['elements']
        result[target]=source
    return result


def retained_case(root,source):
    settings=select_material_response(settings_from_source(source),scope='bulk',native_element_id=1,
        quantity='active',component='scalar',name='BULK_ACTIVE')
    parsed=parse_source(source);definition=parsed['b_definition']
    root.mkdir();export_direct(settings,root/'native')
    save_json(root/'input.json',settings);save_json(root/'b_definition.json',definition)
    save_json(root/'initial_conditions.json',parsed['initial']);save_json(root/'physical_admission.json',{'physics':parsed['physics']})
    from caelab.impact_source import retain
    retain(source,root/'source_bundle')
    raw,titles,_=history_bytes(definition['outputs']['groups'])
    (root/'native/impactT01').write_bytes(raw);(root/'native/impactT01_TITLES').write_bytes(titles)
    original={'execution_status':'FAILED','diagnostics':{'native_execution_status':'SYNTHETIC_NOT_NATIVE'},
        'retained_native':artifact_receipt(root)}
    save_json(root/'original_execution.json',original)
    return settings,parsed,original


@pytest.mark.parametrize('target',['MAT','BRICK'])
@pytest.mark.parametrize('partial',[False,True])
def test_native_include_b_definition_original_and_partial_reader(tmp_path,with_card_include,target,partial):
    root=tmp_path/'attempt';settings,parsed,original=retained_case(root,with_card_include[target])
    record={'execution_status':'FAILED' if partial else 'SUCCEEDED','responses':{},'diagnostics':{}}
    if partial:
        record['source_execution_status']='FAILED'
        record['diagnostics']['original_execution_record']=file_pin(root,root/'original_execution.json')
    before={name:pin['sha256'] for name,pin in original['retained_native']['native_artifacts'].items()}
    append_readback(root,parsed['model'],settings,record,[],partial=partial)
    assert record['responses']['BULK_ACTIVE']['value']==[1.,1.,0.]
    assert record['diagnostics']['b_observations']['scopes']['bulk']['status']=='COMPLETE'
    assert record['responses']['BULK_ACTIVE']['metadata']['reader_operation']==('READBACK_ONLY' if partial else 'ORIGINAL_OUTPUT_READ')
    assert record['execution_status']==('FAILED' if partial else 'SUCCEEDED')
    from caelab.evaluation import file_hash
    assert {name:file_hash(root/name) for name in before}==before


@pytest.mark.parametrize('change',['tampered','missing','unpinned'])
def test_partial_native_include_not_admitted_without_original_pin(tmp_path,with_card_include,change):
    root=tmp_path/'attempt';settings,parsed,original=retained_case(root,with_card_include['MAT'])
    # A newly injected/changed include cannot become evidence for the old attempt.
    include=root/'native/material-or-mesh.inc'
    if change=='tampered':include.write_bytes(include.read_bytes()+b'# changed\n')
    elif change=='missing':include.unlink()
    else:
        del original['retained_native']['native_artifacts']['native/material-or-mesh.inc']
        save_json(root/'original_execution.json',original)
    record={'execution_status':'FAILED','responses':{},'diagnostics':{
        'original_execution_record':file_pin(root,root/'original_execution.json')}}
    append_readback(root,parsed['model'],settings,record,[],partial=True)
    assert record['diagnostics']['b_observations']['scopes']['definition']['status']=='UNKNOWN'
    assert 'BULK_ACTIVE' not in record['responses']


@pytest.fixture
def with_empty_include(tmp_path,with_card_include):
    from caelab.impact_rad_source import export_tree
    folder=tmp_path/'input-with-empty';export_tree(with_card_include['MAT'],folder)
    starter=folder/'impact_0000.rad';raw=starter.read_bytes()
    starter.write_bytes(raw.replace(b'/END',b'#include empty.inc\r\n/END',1))
    (folder/'empty.inc').write_bytes(b'')
    source=capture(starter,folder,engine=folder/'impact_0001.rad',units='Mg/mm/s')
    assert next(row for row in source['bundle']['files'] if row['path']=='empty.inc')['text']==''
    return source


@pytest.mark.parametrize('partial',[False,True])
def test_native_empty_source_include_preserved_original_and_partial_readback(tmp_path,with_empty_include,partial):
    root=tmp_path/'attempt';settings,parsed,original=retained_case(root,with_empty_include)
    pin=original['retained_native']['native_artifacts']['native/empty.inc']
    assert pin['bytes']==0 and (root/'native/empty.inc').read_bytes()==b''
    record={'execution_status':'FAILED' if partial else 'SUCCEEDED','responses':{},'diagnostics':{}}
    if partial:record['diagnostics']['original_execution_record']=file_pin(root,root/'original_execution.json')
    append_readback(root,parsed['model'],settings,record,[],partial=partial)
    assert record['responses']['BULK_ACTIVE']['value']==[1.,1.,0.]
    assert record['diagnostics']['b_observations']['definition_source_files']['native/empty.inc']==pin
    assert (root/'native/empty.inc').read_bytes()==b''


@pytest.mark.parametrize('change',['empty_missing','same_size_tamper'])
def test_partial_empty_source_does_not_weaken_missing_or_same_size_hash_guards(tmp_path,with_empty_include,change):
    root=tmp_path/'attempt';settings,parsed,original=retained_case(root,with_empty_include)
    if change=='empty_missing':(root/'native/empty.inc').unlink()
    else:
        # Change only a comment byte: unchanged length and identical card meaning.
        path=root/'native/material-or-mesh.inc';raw=path.read_bytes();index=raw.index(b'#')+1
        changed=raw[:index]+b'!'+raw[index+1:]
        assert len(changed)==len(raw) and changed!=raw
        path.write_bytes(changed)
    record={'execution_status':'FAILED','responses':{},'diagnostics':{
        'original_execution_record':file_pin(root,root/'original_execution.json')}}
    append_readback(root,parsed['model'],settings,record,[],partial=True)
    assert record['diagnostics']['b_observations']['scopes']['definition']['status']=='UNKNOWN'
    assert 'BULK_ACTIVE' not in record['responses']


def test_empty_source_exception_does_not_admit_empty_native_output(tmp_path):
    from caelab.impact_native_io import read_bytes
    output=tmp_path/'impactT01';output.write_bytes(b'')
    with pytest.raises(ValueError,match='bound'):read_bytes(output)
