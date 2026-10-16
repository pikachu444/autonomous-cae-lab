"""Native property wiring only; controlled proxies, no ParaView execution."""
from copy import deepcopy
from pathlib import Path
import importlib.util
import sys
import pytest

ROOT=next(p for p in Path(__file__).resolve().parents if (p/'tests/test_post_workspace_ownership.py').is_file())
sys.path.insert(0,str(ROOT/'tests'))
from test_post_workspace_ownership import owner_workspace
from test_post_native_view_layout import layout_env


@pytest.fixture
def charts(layout_env):
    s=layout_env
    candidate_path=Path(__file__).resolve().parents[1]/'apps/desktop_post/workspace.py'
    spec=importlib.util.spec_from_file_location('apps.desktop_post.chart_label_candidate',candidate_path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    s.env.work.show=module.Workspace.show.__get__(s.env.work)
    create=s.native.CreateView
    def view(kind):
        result=create(kind)
        if kind=='XYChartView':result.LeftAxisTitle='';result.BottomAxisTitle=''
        return result
    s.native.CreateView=view
    s.chart_view=view
    return s


@pytest.mark.parametrize('kind,array,title,unit',[
    ('surface_time','SurfaceAreaAverage','Surface average','MPa'),
    ('gauge_time','GaugeRelativeDisplacement','Projected relative displacement','mm')])
def test_new_history_chart_receives_labels_from_saved_units_without_data_edits(charts,kind,array,title,unit):
    s=charts;obj,record,bundle=s.result(kind)
    record['summary'].update(array=array,units=unit,time_units='s')
    record['recipe'].update(units=unit,time_units='s',time_range=[0,.2],reference_time=.07)
    before=deepcopy((record['recipe'],record['summary'],bundle['source'].graph,s.render.CameraPosition,
                     s.render.ViewTime,s.raw_display.ColorArrayName,s.render.selected_points))
    s.env.work.show(obj,record,bundle)
    view=s.active[1];display=view.Representations[0]
    assert display.SeriesLabel==[array,title+' ['+unit+']']
    assert view.LeftAxisTitle=='['+unit+']' and view.BottomAxisTitle=='Time [s]'
    assert display.XArrayName=='Time' and display.SeriesVisibility==[array]
    assert display.SeriesLineStyle==[array,'0'] and display.SeriesMarkerStyle==[array,'4']
    assert before==(record['recipe'],record['summary'],bundle['source'].graph,s.render.CameraPosition,
                     s.render.ViewTime,s.raw_display.ColorArrayName,s.render.selected_points)


@pytest.mark.parametrize('missing',[None,'UNKNOWN'])
def test_unknown_units_are_explicit_and_never_guessed_from_array_name(charts,missing):
    s=charts;obj,record,bundle=s.result('gauge_time')
    record['summary'].update(array='GaugeRelativeDisplacement',units=missing,time_units=missing)
    record['recipe'].update(units='mm',time_units='s')
    s.env.work.show(obj,record,bundle)
    view=s.active[1]
    assert view.LeftAxisTitle=='[?]'
    assert view.Representations[0].SeriesLabel==['GaugeRelativeDisplacement','Projected relative displacement [unit unknown]']
    assert view.BottomAxisTitle=='Time [unit unknown]'
    assert record['summary']['units'] is missing


@pytest.mark.parametrize('custom',[False,True])
def test_existing_chart_keeps_explicit_axis_titles_and_fills_only_empty_titles(charts,custom):
    s=charts;obj,record,bundle=s.result('surface_time')
    record['summary'].update(array='SurfaceAreaAverage',units='MPa',time_units='ms')
    existing=s.chart_view('XYChartView');record['view_name']=s.views[-1][0]
    if custom:existing.LeftAxisTitle='User response';existing.BottomAxisTitle='User clock'
    s.env.work.show(obj,record,bundle)
    assert s.active[1] is existing
    assert existing.LeftAxisTitle==('User response' if custom else '[MPa]')
    assert existing.BottomAxisTitle==('User clock' if custom else 'Time [ms]')
    assert existing.Representations[0].SeriesLabel==['SurfaceAreaAverage','Surface average [MPa]']


def test_recipe_units_remain_available_when_older_summary_has_no_unit_keys(charts):
    s=charts;obj,record,bundle=s.result('gauge_time')
    record['summary'].update(array='GaugeRelativeDisplacement')
    record['recipe'].update(units='m',time_units='ms')
    s.env.work.show(obj,record,bundle)
    assert s.active[1].LeftAxisTitle=='[m]'
    assert s.active[1].BottomAxisTitle=='Time [ms]'


def test_explicit_shared_chart_keeps_axes_without_guessing_other_series_units(charts):
    from types import SimpleNamespace
    s=charts;obj,record,bundle=s.result('surface_time')
    record['summary'].update(array='SurfaceAreaAverage',units='MPa',time_units='s')
    existing=s.chart_view('XYChartView');record['view_name']=s.views[-1][0]
    other=SimpleNamespace(Input=object(),Visibility=1,SeriesLabel=['other','User curve'])
    existing.Representations.append(other)
    s.env.work.show(obj,record,bundle)
    assert existing.LeftAxisTitle=='' and existing.BottomAxisTitle==''
    assert other.SeriesLabel==['other','User curve']
    assert existing.Representations[-1].SeriesLabel==['SurfaceAreaAverage','Surface average [MPa]']


@pytest.mark.parametrize('mode',['time','path','contact_force','filter'])
def test_existing_chart_modes_keep_their_original_label_behavior(charts,mode):
    s=charts;obj,record,bundle=s.result(mode)
    if mode=='filter':
        obj['kind']='filter';record['recipe']={'source_ref':'Sraw','filter':'PlotOverLine','settings':{'array':'q'}}
    s.env.work.show(obj,record,bundle)
    view=s.active[1];display=view.Representations[0]
    assert view.LeftAxisTitle=='' and view.BottomAxisTitle==''
    assert not hasattr(display,'SeriesLabel')
