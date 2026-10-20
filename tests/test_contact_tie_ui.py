"""Real Qt TIE editing/entry checks; native document and command receipts are doubles."""
from copy import deepcopy
from types import SimpleNamespace as NS
from test_pre_fem_edit import app, native
from test_pre_fem_edit import Object




def test_native_connection_routes_native_tie_to_official_writer(native,monkeypatch,app):
    import sys
    from apps.desktop_pre.connection import Connection
    from PySide6.QtWidgets import QLabel
    tie=Object(native.doc,'Tie','Fem::ConstraintPython',Proxy=NS(Type='Fem::ConstraintTie'))
    native.analysis.Group.append(tie)
    kind=lambda o:getattr(getattr(o,'Proxy',None),'Type',o.TypeId)
    monkeypatch.setitem(sys.modules,'FemGui',NS(getActiveAnalysis=lambda:native.analysis))
    monkeypatch.setitem(sys.modules,'femtools',NS(femutils=NS(type_of_obj=kind)))
    owner=NS(doc=native.doc,document_id='Pfixture',session_id='Sfixture',generation=7,refresh=lambda:None,
             read_metadata=lambda:deepcopy(native.metadata))
    calls=[]
    connection=NS(pending=None,App=native.App,owners={native.doc.Name:(owner,None,None)},panels={},
                  message=QLabel(),send_command=lambda:calls.append(deepcopy(connection.pending)))
    Connection.run(connection,export_only=True)
    assert calls[-1]['operation']=='pre.freeze' and calls[-1]['export_only']
    assert calls[-1]['arguments']=={'analysis_id':native.analysis.Name,'solver_id':native.solver.Name}
    connection.pending=None
    Connection.run(connection)
    assert calls[-1]['operation']=='pre.freeze' and not calls[-1]['export_only']
