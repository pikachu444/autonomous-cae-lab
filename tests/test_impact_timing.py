"""Explicit native record doubles; no Engine process and no altered native values."""
import csv
from copy import deepcopy
from pathlib import Path
import struct
import pytest
from caelab.adapters.impact_timing import engine_termination,sample_coverage,history_inventory,energy_observations
from caelab.adapters.impact_results import history,GLOBAL_NAMES


def write_native_history(tmp_path,times,rich=False):
    def record(payload):return struct.pack('>I',len(payload))+payload+struct.pack('>I',len(payload))
    def ints(*values):return struct.pack('>'+str(len(values))+'i',*values)
    def floats(values):return struct.pack('>'+str(len(values))+'f',*values)
    title=b'explicit synthetic record double'.ljust(100,b' ')
    data=record(ints(4021)+b'contract test'.ljust(80,b' '))+record(b'date'.ljust(80,b' '))
    data+=record(ints(2))+record(ints(100))+record(floats([1000.,.001,1.]))
    data+=record(ints(*([1,1,1,1,1,23] if rich else [0,0,0,0,0,23])))
    data+=record(ints(*range(1,24)))
    if rich:
        data+=record(ints(1)+title+ints(1,1,0,2))+record(ints(1,2))
        data+=record(ints(1)+title)+record(ints(1)+title)
        data+=record(ints(1,0,0,1,2)+title)+record(ints(1))+record(ints(1,2))
        data+=record(ints(1,1,0,1,3)+title)+record(ints(1)+title)+record(ints(1,2,3))
    columns=['time',*GLOBAL_NAMES]+([f'retained extra {i}' for i in range(7)] if rich else [])
    csvpath=tmp_path/'history.csv'
    with csvpath.open('w',encoding='ascii',newline='') as stream:
        writer=csv.writer(stream);writer.writerow(columns)
        for time in times:
            values=[1.]*23;extras=[2.,3.,4.,5.,6.,7.,8.] if rich else []
            data+=record(floats([time]))+record(floats(values))
            if rich:
                data+=record(floats(extras[:2]))+record(floats(extras[2:4]))+record(floats(extras[4:]))
            all_values=[time,*values,*extras]
            binary=struct.unpack('>'+str(len(all_values))+'f',floats(all_values))
            writer.writerow([format(v,'.6e') for v in binary])
    native=tmp_path/'impactT01';native.write_bytes(data)
    return native,csvpath


@pytest.mark.parametrize('last',[.0009486788,.0009902273])
@pytest.mark.parametrize('rich',[False,True])
def test_normal_end_and_native_samples_are_separate_without_interpolation(tmp_path,last,rich):
    engine=tmp_path/'impact_0001.out'
    engine.write_text('FINAL TIME . . . 1.0000E-03\nNORMAL TERMINATION\nTOTAL NUMBER OF CYCLES : 10\n',encoding='ascii')
    completion=engine_termination(engine,'',.001)
    assert completion['status']=='NORMAL' and completion['achieved_end_s'] is None
    assert completion['declared_end_reached']=='UNKNOWN'
    native,csvpath=write_native_history(tmp_path,[0.,last/2,last],rich)
    responses,table=history(csvpath);before=deepcopy((responses,table))
    inventory=history_inventory(native,table)
    times=[r['values'][0] for r in table['rows']]
    coverage=sample_coverage(times,.001,1e-5)
    assert inventory['record_count']==3
    assert coverage['last_sample_s']==times[-1] and coverage['tail_before_requested_end_s']>0
    assert coverage['requested_end_value']=='NOT_INFERRED'
    assert (responses,table)==before
    assert len(responses['global_1']['value'])==3
    assert responses['global_1']['axes'][0]['values'][-1]<.001
    # ANIM's independent terminal cycle is not an extra TH point.
    anim=sample_coverage([0.,.0005,.00100019],.001,.00005)
    assert anim['samples_after_requested_end']==1 and anim['last_sample_s']==.00100019


def test_user_break_or_missing_completion_never_uses_history_as_end_evidence(tmp_path):
    log=tmp_path/'impact_0001.out'
    for text,status in (
        ('NORMAL TERMINATION\nUSER BREAK\nTOTAL NUMBER OF CYCLES : 2','STOPPED'),
        ('FINAL TIME 1.0000E-03\nTOTAL NUMBER OF CYCLES : 2','INCOMPLETE'),
        ('ABNORMAL TERMINATION\nTOTAL NUMBER OF CYCLES : 2','FAILED'),
        ('NORMAL TERMINATION','INCOMPLETE')):
        log.write_text(text,encoding='ascii')
        assert engine_termination(log,'',.001)['status']==status
    log.write_text('NORMAL TERMINATION\nTOTAL NUMBER OF CYCLES : 2',encoding='ascii')
    assert engine_termination(log,'TOTAL NUMBER OF CYCLES : 3',.001)['status']=='INCOMPLETE'


def test_record_truncation_and_converter_row_loss_are_not_scheduled_tail(tmp_path):
    native,csvpath=write_native_history(tmp_path,[0.,.0005,.0009],True)
    _,table=history(csvpath);original=native.read_bytes()
    for end in (len(original)-1,len(original)-8):
        native.write_bytes(original[:end])
        with pytest.raises(ValueError,match='Truncated|width'):history_inventory(native,table)
    native.write_bytes(original)
    for changed in (table['rows'][:-1],table['rows'][1:],table['rows']+[table['rows'][-1]]):
        with pytest.raises(ValueError,match='row|coverage'):
            history_inventory(native,{**table,'rows':changed})
    with pytest.raises(ValueError,match='column'):
        history_inventory(native,{**table,'header':table['header'][:-1]})


def test_signed_energy_remains_readable_without_physical_approval(tmp_path):
    csvpath=tmp_path/'history.csv'
    with csvpath.open('w',encoding='ascii',newline='') as stream:
        writer=csv.writer(stream);writer.writerow(['time',*GLOBAL_NAMES])
        writer.writerow([0.,'.0065','0',*([0.]*21)])
        writer.writerow([.0009486788,'-7.283110e9','3.425786e9',*([0.]*21)])
    responses,table=history(csvpath)
    assert table['rows'][-1]['tokens'][1]=='-7.283110e9'
    assert responses['global_1']['value'][-1]==pytest.approx(-7.283110e6)
    assert responses['global_2']['value'][-1]==pytest.approx(3.425786e6)
    review=energy_observations(table,csvpath)
    assert review['assessment']=='UNKNOWN' and review['decision']=='NOT_RELEASED'
    assert review['channels'][0]['negative_source_rows']==[3]


def test_adapter_normal_termination_allows_earlier_history_and_post(tmp_path,monkeypatch):
    """Real pinned INP conversion; explicit doubles for native solver/converters."""
    import subprocess
    from types import SimpleNamespace
    from examples.impact.user_model import settings
    import caelab.adapters.impact as module
    s=settings();sample=.0009486788
    samples=tmp_path/'samples';samples.mkdir()
    th,csvpath=write_native_history(samples,[0.,sample],False)
    names={name:name for name in ('starter','engine','th_to_csv','anim_to_vtk')}
    monkeypatch.setattr(module,'selected_runtime',lambda:(names,{}, {'explicit_test_double':True}))
    calls=[]
    def command(argv,cwd,label,**kwargs):
        cwd=Path(cwd);calls.append(label)
        if label=='convert':
            return subprocess.run(argv,cwd=cwd,capture_output=True,timeout=30)
        if label=='starter':
            (cwd/'impact_0000.out').write_text(
                'NORMAL TERMINATION\nNO SYNTAX ERROR DETECTED\n0 ERROR(S)\n0 WARNING(S)\nNUMNOD: 4\n'
                'WORK UNIT SYSTEM ( Mg , mm , s ) 1E3 1E-3 1E0\nINPUT UNIT SYSTEM ( Mg , mm , s ) 1E3 1E-3 1E0\n',encoding='ascii')
        elif label=='engine':
            (cwd/'impact_0001.out').write_text('FINAL TIME 1E-3\nNORMAL TERMINATION\nTOTAL NUMBER OF CYCLES : 10\n',encoding='ascii')
            (cwd/'impactT01').write_bytes(th.read_bytes())
            (cwd/'impactT01_TITLES').write_text('explicit converter double',encoding='ascii')
            (cwd/'impactA001').write_bytes(b'explicit ANIM double')
        elif label=='history_convert':
            (cwd/'history.csv').write_bytes(csvpath.read_bytes())
        elif label.startswith('animation_'):
            vtk=('# vtk DataFile Version 3.0\nexplicit converter double\nASCII\nDATASET UNSTRUCTURED_GRID\n'
                 'FIELD FieldData 1\nTIME 1 1 double\n0.000948679\n'
                 'POINTS 4 float\n0 0 0 10 0 0 0 10 0 0 0 10\n'
                 'CELLS 1 5\n4 0 1 2 3\nCELL_TYPES 1\n10\n'
                 'POINT_DATA 4\nSCALARS NODE_ID int 1\nLOOKUP_TABLE default\n1 2 3 4\n'
                 'VECTORS Displacement float\n0 0 0 0 0 0 0 0 0 0 0 0\n'
                 'CELL_DATA 1\nSCALARS ELEMENT_ID int 1\nLOOKUP_TABLE default\n1\n'
                 'SCALARS PART_ID int 1\nLOOKUP_TABLE default\n1\n'
                 'SCALARS EROSION_STATUS int 1\nLOOKUP_TABLE default\n1\n')
            return SimpleNamespace(returncode=0,stdout=vtk.encode('ascii'),stderr=b'')
        return SimpleNamespace(returncode=0,stdout=b'',stderr=b'')
    monkeypatch.setattr(module,'run_owned_command',command)
    out=tmp_path/'calculation';out.mkdir()
    result=module.ImpactAdapter().run(s,output=out)
    assert result['execution_status']=='SUCCEEDED',result
    assert result['post_artifacts'] and (out/'post/impact.pvd').is_file()
    detail=result['diagnostics']
    assert detail['qualification']==detail['physical_failure']=='UNKNOWN'
    assert detail['decision']=='NOT_RELEASED'
    assert detail['history_coverage']['last_sample_s']<s['time']['end_s']
    assert detail['animation_coverage']['last_sample_s']==.000948679
    assert result['responses']['global_1']['axes'][0]['values'][-1]<s['time']['end_s']
    assert calls.count('engine')==1


def test_pinned_converter_time_underflow_is_not_reinterpreted(tmp_path):
    native,csvpath=write_native_history(tmp_path,[0.,2.**-140,1e-5],False)
    _,table=history(csvpath)
    with pytest.raises(ValueError,match='Subnormal'):
        history_inventory(native,table)
