"""Verified schedule, untimed design pose, legacy clocks and retained Data."""
from copy import deepcopy
import json
import time
from urllib.parse import unquote
import pytest
from test_pre_motion import setup,qt_panel,calculate,Placement,Vector
from apps.desktop_pre.motion import Motion,NATIVE_CLOCK,native_frame_times
from apps.desktop_pre.motion_path import merge_path,csv_payload,data_draft,save_data_document


@pytest.mark.parametrize('start,end,step,expected',[
    (0.,1.,.25,[None,0.,.25,.5,.75,1.]),
    (.5,1.5,.4,[None,.5,.9,1.3]),
    (0.,1.49,.5,[None,0.,.5,1.,1.5]),
    (0.,.45,.5,[None,0.]),  # native first-output comparison is strict
    (0.,.3,.1,[None,0.,.1,.2,.1+.1+.1]),
])
def test_native_schedule_preserves_initial_kind_repeated_addition_and_end_boundary(start,end,step,expected):
    assert native_frame_times({'start':start,'end':end,'step':step},len(expected))==expected
    with pytest.raises(ValueError,match='시각'):native_frame_times({'start':start,'end':end,'step':step},len(expected)+1)


def test_unverified_count_keeps_native_coordinates_and_previous_rows_without_inventing_time(setup):
    owner,motion,target,result=calculate(setup)
    original=motion.dispatch('pre.motion.path',{'calculation_id':result['id'],'trace_id':'Tip','start':0,'count':4},target)
    generate=owner._object(target['assembly_id']).generateSimulation
    def partial(simulation):
        status=generate(simulation)
        owner.doc.frames=[Placement(Vector(i)) for i in range(5)]
        return status
    owner._object(target['assembly_id']).generateSimulation=partial
    new=motion.dispatch('pre.motion.calculate',{},target)
    assert new['id']!=result['id'] and new['frame_times']==[None]*5
    assert not new['clock_source']['complete'] and '예상 4 / 계산 5' in new['clock_source']['reason']
    unknown=motion.dispatch('pre.motion.path',{'calculation_id':new['id'],'trace_id':'Tip','start':0,'count':5},target)
    assert [r['point'][0] for r in unknown['rows']]==[1.,2.,3.,4.,5.]
    assert all(r['time'] is None for r in unknown['rows']) and unknown['rows'][1]['frame_kind']=='unknown'
    assert next(s for s in motion.descriptor()['path_results'] if s['id']==result['id'])['paths']['Tip']==original
    assert b'world_x_mm' in csv_payload(unknown) and owner.doc.moving.Placement.Base.x==0


def test_noninteger_end_admission_and_native_end_output_limit_are_consistent(setup):
    owner,motion,target,definition=setup;definition=deepcopy(definition)
    definition['time'].update(start=2.,end=2.49,step=.5)
    motion.dispatch('pre.motion.configure',{'definition':definition},target)
    assert owner.metadata['motion']['definition']['time']['end']==2.49
    definition['drives'][0]['limits']={'min':0.,'max':1.245,'unit':'rad'}
    with pytest.raises(ValueError,match='전구간'):
        motion.dispatch('pre.motion.configure',{'definition':definition},target)


def test_unverified_native_version_preserves_coordinates_without_schedule_inference(setup):
    owner,motion,target,definition=setup;owner.App.Version=lambda:('1','2','0')
    _,_,_,calculation=calculate(setup)
    assert calculation['frame_times']==[None]*4 and not calculation['clock_source']['complete']
    assert calculation['clock_source']['native_version']=='FreeCAD 1.2.0'
    path=motion.dispatch('pre.motion.path',{'calculation_id':calculation['id'],'trace_id':'Tip','start':0,'count':4},target)
    assert path['rows'][2]['point']==[10.,2.,0.] and path['rows'][2]['time'] is None


def test_same_count_shifted_native_time_rejects_before_generation_and_marks_retained_path_past(setup):
    owner,motion,target,definition=setup;definition=deepcopy(definition);frames=deepcopy(owner.doc.frames)
    definition['time'].update(start=0.,end=1.,step=.5)
    motion.dispatch('pre.motion.configure',{'definition':definition},target);owner.doc.frames=frames
    _,_,_,calculation=calculate(setup)
    path=motion.dispatch('pre.motion.path',{'calculation_id':calculation['id'],'trace_id':'Tip','start':0,'count':4},target)
    assert motion.descriptor()['path_results'][-1]['source_status']=='CURRENT'
    simulation=owner._object(owner.metadata['motion']['simulation_id'])
    simulation.aTimeStart,simulation.bTimeEnd=.5,1.5;owner.generation+=1
    assert len(owner.doc.frames)==4 and native_frame_times({'start':.5,'end':1.5,'step':.5},4)==[None,.5,1.,1.5]
    before=len([c for c in owner.doc.calls if c[0]=='generateSimulation'])
    with pytest.raises(ValueError,match='다시 적용'):
        motion.dispatch('pre.motion.calculate',{},target)
    assert len([c for c in owner.doc.calls if c[0]=='generateSimulation'])==before
    retained=next(s for s in motion.descriptor()['path_results'] if s['id']==calculation['id'])
    assert retained['source_status']=='STALE' and retained['paths']['Tip']==path
    assert owner.metadata['motion']['definition']==definition and simulation.aTimeStart==.5 and simulation.bTimeEnd==1.5
    assert owner.doc.moving.Placement.Base.x==0


def test_qt_restored_design_does_not_display_previous_preview_time(qt_panel):
    app,widget,panel,queued,descriptor,setup=qt_panel
    calculate(setup);widget.refresh(descriptor())
    panel._motion.update(frame=2,preview=True);panel._show_runtime()
    assert '계산 시각 2.5 s' in panel.status.text()
    panel._motion.update(preview=False,state='CANCELLED');panel._show_runtime()
    assert '설계 자세' in panel.status.text() and '계산 시각' not in panel.status.text()


def timed_samples():
    return {'calculation_id':'Ktime','trace_id':'Tip','total_frames':4,'clock':NATIVE_CLOCK,
        'clock_source':{'complete':True,'native_version':'FreeCAD 1.1.4'},'coordinate_unit':'mm','frame':'document_global',
        'rows':[{'frame':i,'time':t,'frame_kind':'design' if i==0 else 'simulation','point':[float(i),0.,0.]}
            for i,t in enumerate([None,0.,.5,1.])]}


def test_time_csv_data_masks_design_only_keeps_raw_coordinates_and_reopens_without_native(tmp_path):
    from caelab.workbench import Workbench
    from caelab.adapters.file_table import read_table
    from caelab.data_document import DataDocuments
    path=merge_path(None,timed_samples());wb=Workbench(tmp_path/'service')
    try:
        saved=save_data_document(wb,path);source=wb.input_path(saved['draft']['data_id'])
        raw_csv=source.read_bytes();lines=raw_csv.decode().splitlines()
        assert lines[1].split(',')[1]=='time_s' and lines[2].startswith('0,nan,0.0,')
        metadata=json.loads(unquote(lines[0].split('=',1)[1]))
        assert metadata['sampled_frames']==[0,1,2,3] and metadata['non_time_frames'][0]['frame']==0
        values=read_table(source,saved['draft']['mapping'])['responses'];x=values['X']
        assert x['axes'][0]['name']=='time' and list(x['axes'][0]['values'])==[0.,.5,1.]
        assert list(x['value'])==[1.,2.,3.] and x['raw_samples']['value']==[0.,1.,2.,3.]
        assert x['raw_samples']['calculation_valid']==[False,True,True,True]
        assert '설계 자세' in x['raw_samples']['exclusion_reasons'][0]
        imported=wb.document_command(saved['id'],'data.import',{},session_id=saved['session_id'],expected_generation=saved['generation'])
        deadline=time.monotonic()+10
        while wb.manager.status(imported['job']['id'])['state'] not in ('SUCCEEDED','FAILED') and time.monotonic()<deadline:time.sleep(.01)
        assert wb.manager.status(imported['job']['id'])['state']=='SUCCEEDED'
        saved=save_data_document(wb,path,document=saved)
        fresh=DataDocuments(wb.root,'cold',None,None,resolve_input=lambda _:None)
        assert fresh.read(saved['id'])['draft']==saved['draft']
        retained=fresh.result(saved['id'],imported['job']['id'])['responses']['X']
        assert retained['axes'][0]['values']==list(x['axes'][0]['values']) and retained['raw_samples']==x['raw_samples']
        assert source.read_bytes()==raw_csv
    finally:wb.manager.shutdown()


def test_qt_design_row_time_curve_and_legacy_clock_are_distinct(qt_panel):
    app,widget,panel,queued,descriptor,setup=qt_panel
    path=timed_samples();browser=panel.path_browser
    browser.refresh([{'id':path['calculation_id'],'paths':{'Tip':path},'source_status':'CURRENT'}],path['calculation_id'])
    assert browser.table.item(0,1).text()=='설계 자세' and browser.table.item(3,1).text()=='1.0'
    assert browser.table.horizontalHeaderItem(1).text()=='계산 시각 [s]'
    browser.plot.grab();assert {i for i,p in browser.plot.points}=={1,2,3}
    browser.table.selectRow(3);assert browser.current_view()['frame']==3
    legacy=deepcopy(path);legacy.update(calculation_id='Kold',clock='nominal output grid')
    legacy['rows']=[{'frame':i,'nominal_time':i*.5,'point':r['point']} for i,r in enumerate(path['rows'])]
    unchanged=deepcopy(legacy)
    browser.refresh([{'id':'Kold','paths':{'Tip':legacy},'source_status':'CURRENT'}],'Kold')
    assert browser.table.item(3,1).text()=='1.5' and '출력격자' in browser.table.horizontalHeaderItem(1).text()
    assert browser.path_value['rows']==unchanged['rows'] and b'nominal_time_s' in csv_payload(legacy)
