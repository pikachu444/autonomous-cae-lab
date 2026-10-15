"""Source-level analytic counterexample; not executed on Windows at preparation."""
import pytest
from caelab.experiment_uncertainty import propagate_linear


def test_partial_input_cannot_publish_non_psd_computed_output_block():
    variables=[{'id':f'x{i}','unit':'1','value':float(i)} for i in range(4)]
    supplied={f'x{i}':{'kind':'standard','value':1.,'unit':'1'} for i in range(3)}
    supplied['x3']={'kind':'UNKNOWN','value':None,'unit':'1'}
    matrix=[[1.,-.9,-.9,None],[-.9,1.,-.9,None],[-.9,-.9,1.,None],[None]*4]
    dependence={'kind':'covariance','order':[v['id'] for v in variables],
        'units':['1']*4,'matrix':matrix,'note':'Explicit public analytic invalid block'}
    G=[[float(i==j) for j in range(4)] for i in range(4)]
    # For the first three output directions: eigenvalues=(-.8,1.9,1.9),
    # v=(1,1,1) gives v^T C v=3+6*(-.9)=-2.4.
    with pytest.raises(ValueError):
        propagate_linear(variables,G,supplied,dependence,included=[True,True,True,False])
