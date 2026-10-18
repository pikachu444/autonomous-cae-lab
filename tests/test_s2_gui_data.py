"""View-data logic is separate from real Qt rendering/Windows acceptance."""
from pathlib import Path
import ast
from copy import deepcopy
from types import SimpleNamespace
import pytest


ROOT=Path(__file__).resolve().parents[1]


def method(relative,cls,name,namespace):
    tree=ast.parse((ROOT/relative).read_text(encoding='utf-8'))
    body=next(node for node in tree.body if isinstance(node,ast.ClassDef) and node.name==cls)
    node=deepcopy(next(n for n in body.body if isinstance(n,ast.FunctionDef) and n.name==name))
    node.decorator_list=[]
    exec(compile(ast.fix_missing_locations(ast.Module(body=[node],type_ignores=[])),relative,'exec'),namespace)
    return namespace[name]


def test_gradient_data_logic_preserves_chain_units_and_inputs():
    # This exercises the actual method body with a drawing sink, NOT a Qt test.
    tables={};axes=SimpleNamespace(clear=lambda:None,get_xscale=lambda:'linear',set_xlabel=lambda *a:None,set_ylabel=lambda *a:None,
        legend=lambda:None,loglog=lambda *a,**k:None)
    view=SimpleNamespace(gradients='g',inputs='i',residuals='r',chains='c',checks='t',
        axes=axes,canvas=SimpleNamespace(draw_idle=lambda:None),summary=SimpleNamespace(setText=lambda t:tables.update(summary=t)),
        rows=lambda t,r:tables.__setitem__(t,r))
    fn=method('apps/research/s2_gradient_widgets.py','GradientEvidence','set_result',{'LABELS':{'heat_source':'체적 열원'}})
    data={'execution_status':'SUCCEEDED','gradients':{'mean_temperature':{'q':{'value':.25,'unit':'K/(W/m^3)'}}},
        'input_bindings':[{'id':'q','label':'공유 열원','unit':'W/m^3','value':4.,
            'targets':[{'stage':'Heat','input_id':'heat_source','applied_value':4.}]}],
        'objective_gradient':{'unit':'scaled_objective/normalized_coordinate','components':[
            {'id':'q','physical':.25,'dx_dz':8.,'value':.2}]},
        'stage_names':{'Heat':'열전도'}}
    before=deepcopy(data);fn(view,data)
    assert data==before and tables['g'][0][3:5]==(.25,'K/(W/m^3)')
    assert tables['c'][0][2:]==(.25,8.,.2,'scaled_objective/normalized_coordinate')
    assert tables['i'][0]==('공유 열원',4.,'W/m^3','열전도 / 체적 열원',4.)


def test_shared_dialog_value_keeps_stable_identity_and_invalid_draft_text():
    text=lambda value:SimpleNamespace(text=lambda:value)
    view=SimpleNamespace(identifier='SharedStable',name=text('한글 공유 입력'),unit=SimpleNamespace(currentText=lambda:'K'),
        value=text('계속 편집 중'),lower=text('285'),upper=text('305'),_target_items=[])
    fn=method('apps/research/shared_binding_dialog.py','SharedBindingDialog','value_draft',
        {'number_or_draft':lambda t:float(t) if t.isdecimal() else t,'deepcopy':deepcopy})
    value=fn(view)
    assert value=={'id':'SharedStable','label':'한글 공유 입력','unit':'K','value':'계속 편집 중','bounds':[285.,305.],'targets':[]}


def test_shared_dialog_actual_qt_draft_and_cancel():
    pytest.importorskip('PySide6',reason='Qt runtime NOT_RUN; not a rendered-window acceptance')
    from PySide6.QtWidgets import QApplication
    from apps.research.shared_binding_dialog import SharedBindingDialog
    app=QApplication.instance() or QApplication([])
    source={'stages':[{'id':'Heat','name':'열전도'}],'bindings':[]};before=deepcopy(source)
    dialog=SharedBindingDialog(None,source,{'Heat':{'inputs':[{'id':'heat_source','label':'체적 열원','unit':'W/m^3','value':1.}]}})
    try:
        dialog.name.setText('공유 열원');dialog.value.setText('수정 중')
        assert dialog.value_draft()['label']=='공유 열원'
        assert dialog.value_draft()['value']=='수정 중'
        assert not dialog.check()
        dialog.reject();assert source==before
    finally:
        dialog.close();dialog.deleteLater();app.processEvents()


def test_gradient_widget_actual_qt_normal_and_narrow():
    pytest.importorskip('PySide6',reason='Qt runtime NOT_RUN; Windows focus/selection still separately required')
    from PySide6.QtWidgets import QApplication
    from apps.research.s2_gradient_widgets import GradientEvidence
    app=QApplication.instance() or QApplication([]);widget=GradientEvidence()
    try:
        for width in (1100,720):
            widget.resize(width,700);widget.set_result({'execution_status':'FAILED','candidates':[]});widget.show();app.processEvents()
            assert widget.tabs.count()==5 and widget.summary.text()
    finally:
        widget.close();widget.deleteLater();app.processEvents()


def test_taylor_log_ticks_are_plain_ascii_and_preserve_values():
    pytest.importorskip('PySide6')
    from PySide6.QtWidgets import QApplication
    from matplotlib.ticker import LogLocator,LogFormatterSciNotation
    from apps.research.s2_gradient_widgets import GradientEvidence
    app=QApplication.instance() or QApplication([]);widget=GradientEvidence()
    result={'execution_status':'SUCCEEDED','gradient_verification':{'status':'PASS','directions':[
        {'taylor':[{'h':h,'R0':h*.1,'R1':h*h*.1} for h in (.04,.02,.01,.005)]}]}}
    original=deepcopy(result)
    try:
        widget.resize(1100,700);widget.show();widget.set_result(result);widget.canvas.draw()
        for axis in (widget.axes.xaxis,widget.axes.yaxis):
            assert isinstance(axis.get_major_locator(),LogLocator)
            assert isinstance(axis.get_minor_locator(),LogLocator)
            positions=(list(axis.get_majorticklocs()),list(axis.get_minorticklocs()))
            major,minor=axis.get_major_formatter(),axis.get_minor_formatter()
            axis.set_major_formatter(LogFormatterSciNotation());axis.set_minor_formatter(LogFormatterSciNotation())
            assert positions==(list(axis.get_majorticklocs()),list(axis.get_minorticklocs()))
            axis.set_major_formatter(major);axis.set_minor_formatter(minor)
            assert axis.get_major_formatter()(1e-2)=='1e-02'
            assert axis.get_major_formatter()(1e-6)=='1e-06'
            for label in axis.get_majorticklabels()+axis.get_minorticklabels():
                assert label.get_text().isascii() and '$' not in label.get_text()
        assert list(widget.axes.lines[0].get_xdata())==[.04,.02,.01,.005]
        assert list(widget.axes.lines[1].get_ydata())==[h*h*.1 for h in (.04,.02,.01,.005)]
        assert result==original
    finally:widget.close();widget.deleteLater();app.processEvents()
