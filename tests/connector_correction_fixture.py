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
