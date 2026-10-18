"""Public original LAW117 coupon with predeclared L03 loading only."""
from examples.impact.cohesive_model import settings as coupon
from caelab.impact_interface import default_control
from caelab.impact_reclosure_policy import POLICY


def settings(stage='P0'):
    value=coupon();value['motions']=[]
    value['contacts']=[{'a':'LOWER_TOP','b':'UPPER_BOTTOM','law':'TYPE24','friction':0.}]
    value['interface_controls']=[{**default_control('BOND'),'reclosure':POLICY,'contact_index':0}]
    value['b_responses']=[
        {'name':'PAIR_IMPULSE_Z','scope':'pair','identity':0,'quantity':'native_impulse','component':'FNZ'},
        {'name':'PAIR_AVERAGE_Z','scope':'pair','identity':0,'quantity':'force','component':'FNZ'},
        {'name':'PAIR_FACE','scope':'interface','identity':2,'quantity':'face_separation','component':'normal'},
        {'name':'COH_ACTIVE','scope':'interface','identity':2,'quantity':'cohesive_active','component':'scalar'}]
    if stage=='P0':value['time'].update(end_s=1e-5,field_interval_s=5e-6,history_interval_s=1e-6)
    elif stage=='P1':
        value['time'].update(end_s=.004,field_interval_s=2.5e-5,history_interval_s=1e-5)
        value['interface_histories']=[{'name':'reclosure_z','material':'BOND','node_set':'MOVING','component':'Z',
            'time_s':[0,.0005,.00075,.00175,.00225,.00325,.0035,.004],
            'displacement_mm':[0,.030,.030,-.025,-.025,.010,.010,.010],'frame':'MODEL_GLOBAL'}]
    else:raise ValueError('Only predeclared P0/P1; P2 requires explicit native restart lineage')
    return value
