"""Real Qt TIE editing/entry checks; native document and command receipts are doubles."""
from copy import deepcopy
from types import SimpleNamespace as NS
from test_pre_fem_panel_ui import app, panel, native
from test_pre_fem_edit import Object
from test_contact_tie import install_tie


def test_gui_tie_dependencies_partial_draft_and_late_edit(panel,native,monkeypatch,app):
    a,b = install_tie(native,monkeypatch)
    panel.refresh(load_forms=True)
    page = panel.contact_page
    page.fields['normal_law'].setCurrentIndex(page.fields['normal_law'].findData('tie'))
    page.fields['tie_tolerance_mm'].setText('1e')
    page.sides['a'].setCurrentIndex(page.sides['a'].findData(a['id']))
    page.sides['b'].setCurrentIndex(page.sides['b'].findData(b['id']))
    panel.tabs.setCurrentWidget(page); panel.resize(1100,780); panel.show(); app.processEvents()
    assert page.fields['tie_tolerance_mm'].isVisible()
    assert not page.fields['normal_stiffness_MPa_per_mm'].isVisible()
    assert not page.fields['tangential_law'].isEnabled()
    assert page.draft()['tangential_law'] == 'tied'
    page.apply()
    page.fields['tie_tolerance_mm'].setText('.02'); page.fields['tie_tolerance_mm'].textEdited.emit('.02')
    panel.test_complete()
    assert native.metadata['contacts'][0]['draft']['tie_tolerance_mm']=='1e'
    assert page.fields['tie_tolerance_mm'].text()=='.02'
    assert panel.width()==1100


def test_native_connection_routes_tie_input_and_run_to_existing_contact_owner(native,monkeypatch,app):
    import sys
    from apps.desktop_pre.connection import Connection
    from PySide6.QtWidgets import QLabel
    tie=Object(native.doc,'Tie','Fem::ConstraintPython',Proxy=NS(Type='Fem::ConstraintTie'))
    native.analysis.Group.append(tie)
    kind=lambda o:getattr(getattr(o,'Proxy',None),'Type',o.TypeId)
    monkeypatch.setitem(sys.modules,'FemGui',NS(getActiveAnalysis=lambda:native.analysis))
    monkeypatch.setitem(sys.modules,'femtools',NS(femutils=NS(type_of_obj=kind)))
    owner=NS(document_id='Pfixture',session_id='Sfixture',generation=7,refresh=lambda:None,
             read_metadata=lambda:deepcopy(native.metadata))
    calls=[]
    connection=NS(pending=None,App=native.App,owners={native.doc.Name:(owner,None,None)},panels={},
                  message=QLabel(),send_command=lambda:calls.append(deepcopy(connection.pending)))
    Connection.run(connection,export_only=True)
    assert calls[-1]['operation']=='pre.contact.freeze' and calls[-1]['export_only']
    assert calls[-1]['arguments']=={'analysis_id':native.analysis.Name,'solver_id':native.solver.Name}
    connection.pending=None
    Connection.run(connection)
    assert calls[-1]['operation']=='pre.contact.freeze' and not calls[-1]['export_only']
