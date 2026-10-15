"""Raw identity, masks and retained Data reads; actual existing comparison/math.

No ParaView, provider, fit or solver is launched. Workbench import is a small
file-table task and its owned executor is always closed in finally.
"""
from copy import deepcopy
import json
from pathlib import Path
import pytest

from caelab.post_curve_origin import targets, verify_curve, raw_record, read_data, read_lineage
from caelab.post_curves import compare, from_response, plain
from caelab.storage import canonical_hash
from test_post_curves import curve, recipe
from test_post_curve_snapshot import imported
from test_post_numerical import fixture_snapshot, selection


def payload(a, b, r):
    out = compare(a, b, r)  # Existing math only; no new alignment in the adapter.
    original = {tag: [{'row_index': i, **row, 'common_x': row['x'], 'common_y': row['y']}
        for i, row in enumerate(out[tag]['rows'])] for tag in ('a','b')}
    return {'semantics':'retained_curve_comparison', 'rows':out['rows'], 'originals':original,
        'summary': {'recipe':r, 'blocked':out['blocked'], 'sources':{tag:{key:out[tag][key]
            for key in ('title','origin','declaration','axis','selected_rows')} for tag in ('a','b')}}}


def test_both_original_brackets_never_midpoint_or_display_index():
    a, b, r = curve([0.,.5,1.],[0.,2.,4.]), curve([100.,1100.],[0.,.004],unit='kN',axis_unit='ms'), recipe()
    r.update(alignment='bracket', b_axis_offset=-.1)
    data = payload(a,b,r); before = deepcopy(data)
    found = targets(data,'aligned',1)
    assert [t['side'] for t in found] == ['a','b','b']
    assert [t['raw']['raw_x'] for t in found] == [.5,100.,1100.]
    assert [t['raw']['raw_y'] for t in found] == [2.,0.,.004]
    assert [t['raw']['identity']['row'] for t in found] == [11,10,11]
    assert found[1]['correspondence']['b'] == pytest.approx(2.)
    assert found[1]['correspondence']['weight'] == .5
    assert verify_curve(b,found[1]) == b['rows'][0]
    assert verify_curve(b,found[2]) == b['rows'][1]
    assert data == before
    assert len(targets(data,'aligned',0)) == 2  # exact endpoint B once


def test_selected_interval_uses_source_position_not_compare_index():
    a, b, r = curve([0.,1.],[1.,3.]), curve([-1.,0.,1.],[9.,2.,4.]), recipe()
    r['b']['rows']=[1,3]
    data=payload(a,b,r); target=targets(data,'b',0)[0]
    assert target['source_index']==1 and target['raw']['identity']['row']==11
    assert verify_curve(b,target)==b['rows'][1]
    target['source_index']=0
    with pytest.raises(ValueError):verify_curve(b,target)


@pytest.mark.parametrize('mode',['excluded','hidden','quality','raw_string','gap','duplicate_axis','load_parameter','unknown_unit'])
def test_originals_survive_invalid_alignment_without_reinterpretation(mode):
    a,b,r=curve([0.,.5,1.],[1.,2.,3.]),curve([0.,1.],[1.,3.]),recipe()
    r.update(alignment='bracket')
    if mode=='excluded':b['rows'][0].update(calculation=False,exclusion_reason='센서 포화')
    elif mode=='hidden':b['rows'][0]['visible']=False
    elif mode=='quality':b['rows'][0].update(quality=False,quality_reason='native_mask')
    elif mode=='raw_string':b['rows'][0]['raw_y']='1.000'
    elif mode=='gap':r['max_gap']=.01
    elif mode=='duplicate_axis':b['rows'][1]['x']=0.
    elif mode=='load_parameter':b['axis'].update(semantics='STATIC_LOAD_PARAMETER',unit='1')
    elif mode=='unknown_unit':b['axis']['unit']=None
    data=payload(a,b,r); t=targets(data,'b',0)[0]
    assert raw_record(verify_curve(b,t))==raw_record(b['rows'][0])
    assert t['axis']==b['axis']
    if mode=='hidden':assert t['raw']['calculation'] and not t['raw']['visible']
    if mode=='gap':assert len(targets(data,'aligned',1))==1  # no invented endpoints


@pytest.mark.parametrize('fault',['identity','raw_x','raw_y','quality','calculation','visible','segment','origin','axis','index'])
def test_changed_row_or_declaration_cannot_be_opened(fault):
    c=curve([0.,1.],[1.,2.]);t=targets(payload(c,c,recipe()),'b',0)[0]; before=deepcopy(t)
    changed=deepcopy(c)
    if fault=='origin':changed['origin']={'test':'different'}
    elif fault=='axis':changed['axis']['unit']='ms'
    elif fault=='index':t['source_index']=1
    elif fault=='identity':changed['rows'][0]['identity']['row']=99
    elif fault in ('quality','calculation','visible'):changed['rows'][0][fault]=False
    else:changed['rows'][0][fault]=7
    with pytest.raises(ValueError):verify_curve(changed,t)
    assert c['rows'][0]['identity']['row']==10


def test_duplicate_identity_missing_bracket_and_bool_index_rejected():
    c=curve([0.,1.],[1.,2.]);p=payload(c,c,recipe())
    p['originals']['b'][1]['identity']=p['originals']['b'][0]['identity']
    with pytest.raises(ValueError):targets(p,'aligned',0)
    p=payload(c,c,recipe());p['originals']['b']=[]
    with pytest.raises(ValueError):targets(p,'aligned',0)
    with pytest.raises(ValueError):targets(payload(c,c,recipe()),'a',True)


def retained_target(wb,ref):
    result=wb.document_result(ref['document_id'],ref['job_id']); response=result['responses']['response']
    origin={'reference':ref,'response':'response','response_sha256':canonical_hash(response)}
    c=from_response(response,origin=origin,title='보존 시험')
    return targets(payload(c,c,recipe()),'a',1)[0]


def test_real_retained_data_read_and_cold_reopen_no_import_no_draft_replacement(tmp_path):
    from caelab.workbench import Workbench
    root=tmp_path/'store';wb=Workbench(root)
    try:
        ref,draft=imported(wb);target=retained_target(wb,ref)
        before=len(wb.manager.list());document=deepcopy(wb.document_read(ref['document_id']))
        result=read_data(wb,target)
        assert result['status']=='DATA_VERIFIED' and result['source_index']==1
        assert result['row']['identity']=={'kind':'physical_line','row':2}
        assert result['row']['y'] is None and not result['row']['calculation']
        assert result['lineage_status']=='NOT_PRESENT'
        assert result['acquisition_rows'][1]=={'source_row':2,'axis':1000.,'value':'nan'}  # keep the retained raw spelling
        assert len(wb.manager.list())==before
        assert wb.document_read(ref['document_id'])['draft']==document['draft']
    finally:wb.shutdown()
    fresh=Workbench(root)
    try:
        assert read_data(fresh,target)==result
        assert len(fresh.manager.list())==before
        for key in ('input_sha256','result_sha256'):
            bad=deepcopy(target);bad['origin']['reference'][key]='0'*64
            with pytest.raises(ValueError):read_data(fresh,bad)
        bad=deepcopy(target);bad['origin']['response_sha256']='0'*64
        with pytest.raises(ValueError):read_data(fresh,bad)
    finally:fresh.shutdown()


def test_optional_lineage_maps_real_csv_physical_row_not_compare_row(tmp_path):
    from caelab.post_observation import project_samples
    from caelab.adapters.file_table import read_table
    snapshot,_=fixture_snapshot(tmp_path)
    projected=project_samples(snapshot,selection())
    file=tmp_path/'measurement.csv';file.write_bytes(projected['csv'])
    response=plain(read_table(file,projected['mapping'])['responses']['measured'])
    c=from_response(response,origin={'reference':{'retained':'fixture'},'response':'measured',
        'response_sha256':canonical_hash(response)},title='원측정 계보')
    t=targets(payload(c,c,recipe()),'a',1)[0]
    class Client:
        def post_observation(self,ref):
            return {'origin':projected['origin'],'response':response,'source_available':True}
    result=read_lineage(Client(),t)
    assert result['lineage_status']=='AVAILABLE'
    assert result['native_target']['mapping']['native']=={'block':[0],'row':1}
    assert result['native_target']['mapping']['source_row']==2
    t['raw']['identity']['kind']='derived_index'
    assert read_lineage(Client(),t)['lineage_status']=='UNAVAILABLE'


def test_explicit_existing_fixture_brackets_read_again_after_service_close(tmp_path):
    from examples.post_origin_return import run
    result=run(tmp_path/'new-fixture')
    assert result['cold_rows_equal'] and result['navigation_jobs_added']==0
    assert [r['identity']['row'] for r in result['original_b_rows']]==[1,2]
    assert result['aligned']['b']==2. and result['aligned']['weight']==.5
    assert result['native_gui']=='NOT_RUN'
