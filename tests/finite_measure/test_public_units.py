"""Same test in two unit conventions; never counted as independent holdout."""
from pathlib import Path
import json
import pytest
from caelab.adapters.file_table import read_table
from caelab.finite_measure_input import mapping,recipe,local_preview
from caelab.data_processing import preview_recipe
from caelab.data_processing_lineage import verify_response,trace_sample
from caelab.storage import canonical_hash

ROOT=Path(__file__).resolve().parents[2]/'examples/finite-measure'


def test_public_reordered_unit_twin_and_json_cold_replay(tmp_path):
    outputs=[]
    for tag in ('train','train-unit-twin'):
        c=json.loads((ROOT/(tag+'-config.json')).read_text(encoding='utf-8'));m=mapping(c)
        raw=read_table(ROOT/(tag+'.csv'),m)
        source=dict(document_id='T'+tag.replace('-',''),job_id='Jcase',input_revision='Icase',input_sha256=canonical_hash(m))
        out=preview_recipe(raw,source,recipe(c));assert out['execution_status']=='SUCCEEDED',out['stages']
        for r in out['responses'].values():verify_response(r,complete=True)
        cold=json.loads(json.dumps(out,sort_keys=True))
        for r in cold['responses'].values():verify_response(r,complete=True)
        outputs.append(out)
    for name in outputs[0]['responses']:
        assert outputs[0]['responses'][name]['value']==pytest.approx(outputs[1]['responses'][name]['value'],abs=1e-12)
        assert outputs[0]['responses'][name]['axes']==outputs[1]['responses'][name]['axes']
    assert outputs[0]['source']['source_sha256']!=outputs[1]['source']['source_sha256']
    # A0 remains geometry; response input values stay N or kN, not secretly MPa.
    assert outputs[1]['channels']['fm_load']['metadata']['unit']=='kN'


def test_local_preview_preserves_raw_and_explains_missing_unit():
    c=json.loads((ROOT/'train-unit-twin-config.json').read_text(encoding='utf-8'))
    rows=[[1.1,1000.,1250.,1.,17.6]]
    # Here J/A are deliberately inconsistent with 1.025; the raw row survives.
    r=local_preview(c,rows)[0]
    assert r['raw']==rows[0] and r['values']['engineering_strain']==pytest.approx(.025)
    assert r['values']['log_strain']==pytest.approx(__import__('math').log(1.025))
    assert r['values']['finite_Cauchy'] is None and '충돌' in r['errors']['finite_Cauchy']
    c['columns']['load']['unit']=''
    r=local_preview(c,rows)[0]
    assert r['values']['first_Piola'] is None and r['raw']==rows[0]


def test_current_geometry_or_units_cannot_silently_execute_old_recipe():
    from copy import deepcopy
    from caelab.finite_measure_input import verify_processing_specification
    c=json.loads((ROOT/'train-config.json').read_text());m=mapping(c);raw=read_table(ROOT/'train.csv',m)
    draft={'finite_measure':c,'processing':{'recipe':recipe(c)}}
    verify_processing_specification(draft,raw)
    changed=deepcopy(draft);changed['finite_measure']['geometry']['A0']['value']='1e'
    with pytest.raises(ValueError,match='현재 치수'):verify_processing_specification(changed,raw)
    changed['processing']['recipe']=recipe(changed['finite_measure'])
    # Consistent raw invalid definition can be previewed, but its value operation
    # fails domain checks; no old A0 is substituted.
    verify_processing_specification(changed,raw)
    bad=deepcopy(draft);bad['finite_measure']['columns']['load']['unit']='kN'
    bad['processing']['recipe']=recipe(bad['finite_measure'])
    with pytest.raises(ValueError,match='import'):verify_processing_specification(bad,raw)
    assert draft['finite_measure']['geometry']['A0']['value']==20.
