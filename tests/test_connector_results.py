"""Controlled byte fixtures; never reported as native execution evidence."""
import json
from copy import deepcopy
from pathlib import Path
import pytest
from test_connector_model import draft
from impact_b_fixtures import history_bytes
from caelab.connector_results import parse,catalog,read
from caelab.connector_model import BACKEND,model
from caelab.connector_deck import TOKENS,layout,starter,engine
from caelab.storage import save_json,canonical_hash
from caelab.dynamic_result_store import file_pin
from caelab.adapters.opencourant_runtime import WINDOWS_SOURCE,WINDOWS_FILES


def fixture(root):
    settings={'connector':draft()};native=root/'native';native.mkdir()
    data,titles,_=history_bytes([{'id':1,'type':3,'title':'CONTROLLED_TYPE13','members':[1],'tokens':list(TOKENS)}])
    (native/'connectorT01').write_bytes(data);(native/'connectorT01_TITLES').write_bytes(titles)
    save_json(root/'input.json',settings)
    m=model(settings['connector'])
    mapping={'native_run_name':'connector','th_group':1,'spring_element':1,
             'nodes':layout(m)[0],'attachments':layout(m)[1]}
    from caelab.connector_admission import expected_bodies
    mapping['expected_native_bodies']=expected_bodies(m,mapping)
    save_json(root/'connector_mapping.json',mapping)
    (native/'connector_0000.rad').write_text(starter(m),encoding='ascii')
    (native/'connector_0001.rad').write_text(engine(m),encoding='ascii')
    text='''SYNTHETIC CONTROLLED LOG NOT A NATIVE RUN
NORMAL TERMINATION
NO SYNTAX ERROR DETECTED
0 ERROR(S)
0 WARNING(S)
NUMNOD: 2
WORK UNIT SYSTEM ( Mg , mm , s ) 1000 .001 1
INPUT UNIT SYSTEM ( Mg , mm , s ) 1000 .001 1
'''
    for row in mapping['expected_native_bodies']:
        def vals(values):return ' '.join(format(v,'.7g') for v in values)
        text+=f"""RIGID BODY INITIALIZATION
RIGID BODY ID {row['body']}
PRIMARY NODE {row['main_node']}
NEW X,Y,Z {vals(row['position_mm'])}
NEW MASS {row['mass_Mg']:.7g}
NEW INERTIA xx yy zz {vals(row['inertia_Mg_mm2'][:3])}
NEW INERTIA xy yz zx {vals(row['inertia_Mg_mm2'][3:])}
PRINCIPAL INERTIA {vals(row['inertia_Mg_mm2'][:3])}
SECONDARY NODES
{vals(row['secondary_nodes'])}

"""
    (native/'connector_0000.out').write_text(text,encoding='ascii')
    h=parse(root,settings);save_json(root/'connector_history.json',h)
    from caelab.adapters.impact import starter_admission
    from caelab.connector_admission import read_bodies
    outcome={'backend':BACKEND,'execution_status':'SUCCEEDED',
        'runtime':{'platform':'win64','source_tag':WINDOWS_SOURCE,'files':WINDOWS_FILES},
        'starter_admission':starter_admission(native/'connector_0000.out',{'nodes':dict(mapping['nodes']),'elements':{}}),
        'native_attachments':read_bodies(native/'connector_0000.out',mapping,fe=False),
        'model_sha256':canonical_hash(model(settings['connector'])),
        'effective_deck_pins':[file_pin(root,native/('connector_'+tail+'.rad')) for tail in ('0000','0001')],
        'artifacts':[file_pin(root,p) for p in sorted(root.rglob('*')) if p.is_file()]}
    save_json(root/'connector_execution.json',outcome)
    return settings,outcome


def test_raw_actual_clock_and_retained_selected_slice(tmp_path):
    settings,outcome=fixture(tmp_path)
    selected=read(outcome,tmp_path,'connector.MX',start=1,stop=3)
    assert selected['value']==[4.,5.]
    assert selected['unit']=='N*mm' and selected['axes'][0]['values'][1]!=.0003
    assert selected['source_rows']==[1,2] and selected['valid_mask']==[True,True]
    assert catalog(outcome,tmp_path)['connector.IE']['quantity'].startswith('native generalized internal work')
    assert 'reaction' in catalog(outcome,tmp_path)['connector.MY']['semantics']
    for change in (-1,True,.1):
        with pytest.raises(ValueError):read(outcome,tmp_path,'connector.MX',start=change)


def test_unit_proof_and_raw_bytes_cannot_be_replaced(tmp_path):
    settings,outcome=fixture(tmp_path)
    forged=deepcopy(outcome);forged['starter_admission']['units']='kg/m/s'
    save_json(tmp_path/'connector_execution.json',forged)
    with pytest.raises(ValueError,match='단위'):catalog(forged,tmp_path)
    save_json(tmp_path/'connector_execution.json',outcome)
    with (tmp_path/'native/connectorT01').open('ab') as stream:stream.write(b'changed')
    with pytest.raises(ValueError):catalog(outcome,tmp_path)


def test_nonfinite_values_and_failed_tail_keep_masks(tmp_path):
    settings,outcome=fixture(tmp_path)
    data,titles,_=history_bytes([{'id':1,'type':3,'title':'CONTROLLED_TYPE13','members':[1],'tokens':list(TOKENS)}],nan=True)
    path=tmp_path/'native/connectorT01';path.write_bytes(data)
    h=parse(tmp_path,settings);assert h['values']['IE'][1] is None and h['mask']['IE'][1] is False
    path.write_bytes(data[:-8]);partial=parse(tmp_path,settings,failed=True)
    assert len(partial['time_s'])==2 and partial['excluded']


def test_mismatched_actual_member_is_not_retitled(tmp_path):
    settings,_=fixture(tmp_path)
    mapping=json.loads((tmp_path/'connector_mapping.json').read_text(encoding='utf-8'))
    mapping['spring_element']=2;save_json(tmp_path/'connector_mapping.json',mapping)
    with pytest.raises(ValueError,match='실제 요소'):parse(tmp_path,settings)
