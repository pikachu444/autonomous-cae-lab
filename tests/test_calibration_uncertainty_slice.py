"""Independent metrology oracle for the existing affine first-order slice."""
from copy import deepcopy
import math
import numpy as np
import pytest

from caelab.experiment_calibration import default_calibration
from caelab.experiment_uncertainty import calibration_problem,propagate,plain


def test_shared_coefficient_covariance_and_joint_nonlinear_first_order_oracle():
    recipe={**default_calibration('N'),'input_unit':'V','coefficient_input_unit':'V','x0_unit':'V',
            'a':2.,'x0':1.,'b':5.,'source':{'data_id':'Dpublic','sha256':'a'*64,'name':'Public synthetic certificate'},
            'uncertainty':{'value':.7,'unit':'N','kind':'expanded','k':2.,'correlation':'UNKNOWN','note':'Output only; do not sum'}}
    original={'kind':'series','unit':'N','component':'z','location':'gauge','measure':'force','frame':'lab',
              'calibration':recipe,'source_rows':[10,12],'value':[9.,11.],
              'raw_samples':{'source_rows':[10,12],'value':[3.,4.],'transformed_value':[9.,11.],
                             'calculation_valid':[True,True],'quality_valid':[True,True]}}
    before=deepcopy(original);problem=calibration_problem(original)
    u=[.1,.1,.2,.05,.3]
    specification={'uncertainties':{v['id']:{'kind':'standard','value':value,'unit':v['unit']}
                                   for v,value in zip(problem['variables'],u)},
                   'dependence':{'kind':'independent_declared','note':'Explicit independent oracle inputs'},
                   'axis_uncertainty':'UNKNOWN'}
    a=propagate(problem,specification)['experiment_analysis']
    assert np.asarray(a['output_covariance'])==pytest.approx(np.array([[.30,.34],[.34,.50]]),abs=1e-12)
    assert a['rows'][0]['standard_uncertainty']==pytest.approx(math.sqrt(.30),abs=1e-12)
    # This scalar affine sensor law is jointly nonlinear in a and x/x0.
    # Central differences independently check the declared analytic first derivatives.
    nominal=np.array([3.,4.,2.,1.,5.])
    def measured(v):return v[2]*(v[:2]-v[3])+v[4]
    jacobian=np.empty((2,5));step=1e-5
    for j in range(5):
        delta=np.zeros(5);delta[j]=step
        jacobian[:,j]=(measured(nominal+delta)-measured(nominal-delta))/(2*step)
    assert np.asarray(problem['sensitivities'])==pytest.approx(jacobian,abs=1e-8)
    C=np.diag(np.array(u)**2);C[2,4]=C[4,2]=.03
    specification['dependence']={'kind':'covariance','order':[v['id'] for v in problem['variables']],
        'units':[v['unit'] for v in problem['variables']],'matrix':C.tolist(),'note':'Supplied Cov(a,b)=.03 N^2/V'}
    a=propagate(problem,specification)['experiment_analysis']
    assert a['rows'][0]['standard_uncertainty']==pytest.approx(math.sqrt(.42),abs=1e-12)
    assert a['input_covariance'][2][4]==.03
    assert a['source_problem']['supplied_output_uncertainty']==recipe['uncertainty']
    assert a['calibration_reapplied'] is False and original==before
    specification['dependence']={'kind':'UNKNOWN'}
    unknown=propagate(problem,specification)
    assert unknown['execution_status']=='REJECTED'
    assert all(r['standard_uncertainty'] is None for r in unknown['experiment_analysis']['rows'])
    assert original==before
