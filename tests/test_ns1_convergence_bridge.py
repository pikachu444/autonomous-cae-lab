"""Common integration patch operations through the actual typed bridge, with a native double."""
from test_pre_bridge import native, request
from test_ns1_convergence_controls import draft
from caelab.native_commands import CAPABILITIES


def test_bridge_routes_convergence_commands_without_solving(native):
    n=native;n.analysis.Group=[n.solver]
    # Routing check: metadata persistence is a JSON-backed native-document double.
    import json
    data={}
    n.owner.read_metadata=lambda:json.loads(json.dumps(data))
    def store(value):
        data.clear();data.update(json.loads(json.dumps(value)))
    n.owner.write_metadata=store
    for suffix in ('read','save','apply'):
        operation='pre.fem.convergence_'+suffix
        assert operation in CAPABILITIES['pre']
        args={'analysis_id':n.analysis.Name}
        if suffix!='read':args['draft']=draft()
        q=request(n,operation,args,{'object_id':n.solver.Name},command_id='C'+suffix)
        result=n.owner.dispatch(q)
        assert result['status']=='COMPLETED',result
        assert result['result']['executed'] is False
    assert n.solver.IterationsControlParameterIter==draft()['iterations']
