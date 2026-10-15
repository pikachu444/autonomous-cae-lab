"""Opaque converter titles and exact retained 3040 unit proof; no solver calls."""
from copy import deepcopy
import csv,io,json,struct
from pathlib import Path
import pytest
from caelab.adapters.impact_results import GLOBAL_NAMES,history,history_prefix
from caelab.adapters.impact import starter_admission
from caelab.adapters.opencourant_runtime import WINDOWS_SOURCE,WINDOWS_FILES
from caelab.impact_bulk_history import retained_pair_units,pair_provenance,PAIR_CHANNELS
from caelab.dynamic_result_store import file_pin
from caelab.storage import save_json


def identity():return {'platform':'win64','source_tag':WINDOWS_SOURCE,'files':deepcopy(WINDOWS_FILES)}


def csv_bytes():
    s=io.StringIO(newline='');w=csv.writer(s)
    w.writerow(['time',*GLOBAL_NAMES,'PAIR_FNX_OPAQUE']);w.writerow([0.,*range(23),2.]);w.writerow([.1,*range(23),3.])
    return s.getvalue().encode('ascii').replace(b'PAIR_FNX_OPAQUE',b'PAIR_FNX_\xbc\xef\xc5')


def test_opaque_additional_header_preserves_raw_bytes_and_requires_exact_converter(tmp_path):
    p=tmp_path/'history.csv';raw=csv_bytes();p.write_bytes(raw)
    for runtime in (None,{**identity(),'files':{}},{**identity(),'source_tag':'other'}):
        with pytest.raises(ValueError,match='exact retained converter'):history(p,converter_identity=runtime)
    responses,table=history(p,converter_identity=identity())
    assert bytes.fromhex(table['header_byte_evidence']['raw_header_hex'])==raw.splitlines(keepends=True)[0]
    assert table['rows'][0]['values'][-1]==2. and table['header'][:24]==['time',*GLOBAL_NAMES]
    assert table['unmapped_columns']==['PAIR_FNX_\\xbc\\xef\\xc5']
    _,prefix=history_prefix(p,converter_identity=identity())
    assert prefix['recovery']['verified_source_rows']==[2,3] and prefix['recovery']['status']=='COMPLETE'
    assert p.read_bytes()==raw


def test_opaque_global_header_and_nonascii_body_never_pass(tmp_path):
    p=tmp_path/'history.csv';raw=csv_bytes()
    p.write_bytes(raw.replace(b'INTERNAL ENERGY',b'INTERNAL\xbc ENERGY'))
    with pytest.raises(ValueError,match='global layout'):history(p,converter_identity=identity())
    p.write_bytes(raw+b'\xbc,1,2\n')
    with pytest.raises(UnicodeError):history(p,converter_identity=identity())


def test_normal_utf8_header_is_preserved_without_runtime(tmp_path):
    raw=csv_bytes().replace(b'PAIR_FNX_\xbc\xef\xc5','원 제목'.encode('utf8'))
    p=tmp_path/'utf8.csv';p.write_bytes(raw)
    _,table=history(p)
    assert table['unmapped_columns']==['원 제목'] and 'header_byte_evidence' not in table


def unit_attempt(tmp_path):
    settings={'source':{'units':'Mg/mm/s'},'public_synthetic_test':True}
    model={'nodes':{1:[0,0,0]},'elements':{1:{'type':'C3D4'}}}
    native=tmp_path/'native';native.mkdir()
    (native/'impact_0000.out').write_text('NORMAL TERMINATION\nNO SYNTAX ERROR DETECTED\n0 ERROR(S)\n0 WARNING(S)\nNUMNOD: 1\nWORK UNIT SYSTEM ( Mg , mm , s ) 1E3 1E-3 1E0\nINPUT UNIT SYSTEM ( Mg , mm , s ) 1E3 1E-3 1E0\n',encoding='ascii')
    (native/'impactT01').write_bytes(b'SYNTHETIC_HISTORY_PIN_ONLY')
    (native/'impactT01_TITLES').write_bytes(b'SYNTHETIC_TITLES_PIN_ONLY')
    save_json(tmp_path/'input.json',settings)
    pins={n:file_pin(tmp_path,native/n.split('/')[-1]) for n in ('native/impact_0000.out','native/impactT01','native/impactT01_TITLES')}
    original={'diagnostics':{'runtime':identity()},'checks':[starter_admission(native/'impact_0000.out',model)],
        'retained_native':{'input_artifacts':{'input.json':file_pin(tmp_path,tmp_path/'input.json')},'native_artifacts':pins}}
    save_json(tmp_path/'original_execution.json',original)
    return settings,model,original,file_pin(tmp_path,tmp_path/'original_execution.json')


def test_legacy_proof_binds_exact_execution_input_runtime_starter_and_history_pins(tmp_path):
    s,m,original,execution=unit_attempt(tmp_path)
    proof=retained_pair_units(tmp_path,execution,m,s,identity())
    group={'type':101,'members':[1],'tokens':list(PAIR_CHANNELS),'native_variable_ids':list(range(1,7))}
    h={'layout':{'format_code':3040,'unit_factors':None},'source_pin':file_pin(tmp_path/'native',tmp_path/'native/impactT01'),
        'titles_pin':file_pin(tmp_path/'native',tmp_path/'native/impactT01_TITLES')}
    assert pair_provenance(h,group,identity(),proof)['legacy_unit_evidence']['execution_pin']==execution
    assert pair_provenance(h,group,identity(),{'units':'Mg/mm/s'}) is None
    assert pair_provenance(h,group,identity()) is None
    altered=deepcopy(h);altered['source_pin']['sha256']='0'*64
    assert pair_provenance(altered,group,identity(),proof) is None
    with pytest.raises(ValueError):retained_pair_units(tmp_path,execution,m,{**s,'other':True},identity())
    with pytest.raises(ValueError):retained_pair_units(tmp_path,execution,m,s,{**identity(),'files':{}})
    (tmp_path/'native/impact_0000.out').write_text('PASS units Mg/mm/s',encoding='ascii')
    with pytest.raises(ValueError):retained_pair_units(tmp_path,execution,m,s,identity())


def test_missing_or_changed_original_check_is_not_reconstructed_as_authority(tmp_path):
    s,m,original,_=unit_attempt(tmp_path)
    for change in ('missing','units'):
        altered=deepcopy(original)
        if change=='missing':altered['checks']=[]
        else:altered['checks'][0]['units']='kg/m/s'
        save_json(tmp_path/'original_execution.json',altered)
        pin=file_pin(tmp_path,tmp_path/'original_execution.json')
        with pytest.raises(ValueError):retained_pair_units(tmp_path,pin,m,s,identity())


def test_corrupt_csv_header_remains_a_recoverable_value_error(tmp_path):
    p=tmp_path/'history.csv';p.write_bytes(b'"unterminated header\n0,1,2\n')
    for parser in (history,history_prefix):
        with pytest.raises(ValueError,match='header is unreadable'):parser(p,converter_identity=identity())
