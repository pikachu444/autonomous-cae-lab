"""Candidate show/layout only: controlled native API, no new calculation."""
from copy import deepcopy
import importlib.util
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tests'))
from test_post_workspace_ownership import owner_workspace


class Layout:
    def __init__(self,view=None):
        self.cells={} if view is None else {0:view}
        self.splits=[];self.collapses=[];self.SMProxy=self;self.maximized=-1
    def GetMaximizedCell(self):return self.maximized
    def GetViewLocation(self,view):return next((i for i,v in self.cells.items() if v is view),-1)
    def SplitViewVertical(self,view,fraction):
        old=self.GetViewLocation(view);top=2*old+1
        self.cells.pop(old);self.cells[top]=view
        self.splits.append((old,fraction));return top
    def AssignView(self,slot,view):
        assert slot not in self.cells
        self.cells[slot]=view;return True
    def RemoveView(self,view):
        slot=self.GetViewLocation(view)
        if slot>=0:self.cells.pop(slot)
        return slot
    def Collapse(self,slot):
        assert slot not in self.cells
        parent=(slot-1)//2;sibling=2*parent+1
        self.cells[parent]=self.cells.pop(sibling);self.collapses.append(slot);return True


@pytest.fixture
def layout_env(owner_workspace):
    env=owner_workspace
    path=Path(__file__).resolve().parents[1]/'apps/desktop_post/workspace.py'
    spec=importlib.util.spec_from_file_location('apps.desktop_post.workspace_layout_candidate',path)
    candidate=importlib.util.module_from_spec(spec);spec.loader.exec_module(candidate)
    env.work.show=candidate.Workspace.show.__get__(env.work)
    env.work._result_render_view=candidate.Workspace._result_render_view.__get__(env.work)
    views=[];active=[env.work.resolve('Sraw'),None];layouts=[];resets=[]
    def view(kind):
        item=SimpleNamespace(GetXMLName=lambda:kind,Representations=[],CameraPosition=[9,8,7],
            ViewTime=.7,selected_points=[2,4],LeftAxisTitle='',BottomAxisTitle='');item.SMProxy=item
        views.append(('view'+str(len(views)),item));return item
    render=view('RenderView');raw_display=SimpleNamespace(Input=active[0],Visibility=1,ColorArrayName=['POINTS','stress'])
    render.Representations.append(raw_display);layout=Layout(render);layouts.append(layout);active[1]=render
    def create_layout(**kwargs):
        item=Layout();layouts.append(item);return item
    def show(source,target,*args):
        display=next((d for d in target.Representations if d.Input is source),None)
        if display is None:display=SimpleNamespace(Input=source,Visibility=1);target.Representations.append(display)
        display.Visibility=1;return display
    native=candidate.p
    native.GetActiveSource=lambda:active[0];native.GetActiveView=lambda:active[1]
    native.SetActiveSource=lambda value:active.__setitem__(0,value);native.SetActiveView=lambda value:active.__setitem__(1,value)
    native.GetLayout=lambda value:next((l for l in layouts if l.GetViewLocation(value)>=0),None)
    native.CreateLayout=create_layout;native.CreateView=view
    native.AssignViewToLayout=lambda view,layout,hint:layout.AssignView(hint,view)
    native.Show=show;native.Render=lambda target:None;native.ResetCamera=lambda target:resets.append(target)
    native.Delete=lambda target:views.remove(next(row for row in views if row[1] is target))
    native.RemoveLayout=lambda target:layouts.remove(target)
    native.Hide=lambda source,target:setattr(next(d for d in target.Representations if d.Input is source),'Visibility',0)
    env.work._views=lambda:list(views)
    def result(kind='surface_average',ref='Ameasure'):
        obj=env.add_object(ref);obj['kind']='measurement'
        record=obj['history'][0];record['recipe']={'source_ref':'Sraw','measurement':kind,'array':'q'}
        record['summary']={'array':'SurfaceAreaAverage'}
        return obj,record,env.work.bundles[record['id']]
    return SimpleNamespace(env=env,native=native,views=views,layouts=layouts,layout=layout,render=render,
        raw_display=raw_display,active=active,resets=resets,result=result,create_view=view)


@pytest.mark.parametrize('kind,type_name',[('surface_average','SpreadSheetView'),('surface_time','XYChartView')])
def test_first_result_splits_model_above_own_result_and_redisplay_reuses_it(layout_env,kind,type_name):
    s=layout_env;obj,record,bundle=s.result(kind)
    model=(deepcopy(s.render.CameraPosition),s.render.ViewTime,deepcopy(s.raw_display.ColorArrayName),deepcopy(s.render.selected_points))
    s.env.work.show(obj,record,bundle)
    result=s.active[1]
    assert result.GetXMLName()==type_name
    assert s.layout.cells=={1:s.render,2:result} and s.layout.splits==[(0,.68)]
    assert len(s.layouts)==1 and len(s.views)==2 and s.resets==[]
    s.env.work.show(obj,record,bundle)
    assert len(s.views)==2 and s.layout.splits==[(0,.68)] and s.active[1] is result
    assert model==(s.render.CameraPosition,s.render.ViewTime,s.raw_display.ColorArrayName,s.render.selected_points)
    other,other_record,other_bundle=s.result(kind,'Aother')
    s.env.work.show(other,other_record,other_bundle)
    assert s.active[1] is not result and len(result.Representations)==1
    assert s.layout.cells[2] is result and len(s.views)==3 # Existing chart is never implicitly overlaid.
    assert s.layout.cells=={1:s.render,2:result} and s.layout.splits==[(0,.68)]
    assert len(s.layouts)==2


def test_user_split_model_is_not_automatically_split_again(layout_env):
    s=layout_env;obj,record,bundle=s.result()
    existing=s.create_view('XYChartView')
    s.layout.cells={1:s.render,2:existing}
    s.env.work.show(obj,record,bundle)
    assert s.layout.cells=={1:s.render,2:existing} and s.layout.splits==[]
    assert len(s.layouts)==2 and s.active[1] is not existing


def test_saved_or_explicit_compatible_view_is_reused_without_layout_changes(layout_env):
    s=layout_env;obj,record,bundle=s.result('surface_time')
    saved=s.create_view('XYChartView');saved_layout=Layout(saved);s.layouts.append(saved_layout)
    record['view_name']=s.views[-1][0]
    s.env.work.show(obj,record,bundle)
    assert s.active[1] is saved and s.layout.splits==[] and saved_layout.splits==[]
    explicit=s.create_view('XYChartView');explicit_layout=Layout(explicit);s.layouts.append(explicit_layout)
    s.env.owner.proxy_id=lambda view:str(id(view))
    s.env.work.show(obj,record,bundle,view_id=str(id(explicit)))
    assert s.active[1] is explicit and all(not l.splits for l in s.layouts)
    before=(len(s.views),deepcopy(record),list(s.layout.splits))
    with pytest.raises(ValueError,match='XYChartView'):
        s.env.work.show(obj,record,bundle,view_id=str(id(s.render)))
    assert before==(len(s.views),record,s.layout.splits)


@pytest.mark.parametrize('unrelated,maximized',[(True,False),(False,True)])
def test_unrelated_or_maximized_native_layout_is_untouched(layout_env,unrelated,maximized):
    s=layout_env;obj,record,bundle=s.result()
    if unrelated:s.raw_display.Input=object()
    if maximized:s.layout.maximized=0
    s.env.work.show(obj,record,bundle)
    assert s.layout.cells=={0:s.render} and s.layout.splits==[]
    assert len(s.layouts)==2 and s.layouts[-1].cells[0] is s.active[1]


def test_failed_new_result_rolls_back_only_its_split_and_view(layout_env):
    s=layout_env;obj,record,bundle=s.result();before=list(s.active)
    s.native.Render=lambda target:(_ for _ in ()).throw(RuntimeError('controlled render failure'))
    with pytest.raises(RuntimeError,match='controlled render failure'):s.env.work.show(obj,record,bundle)
    assert s.layout.cells=={0:s.render} and s.layout.collapses==[2]
    assert s.active==before and len(s.views)==1 and len(s.layouts)==1 and 'view_name' not in record
