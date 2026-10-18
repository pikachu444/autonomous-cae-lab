"""The two predeclared public LAW117 input fixtures; no tuning/campaign generator."""
from examples.impact.cohesive_model import settings as coupon
from caelab.impact_interface import default_control


def declared_settings(kind):
    clock=[0,.0005,.00075,.00125,.00175,.002,.0025,.003,.00325,.0035,.00375,.004]
    if kind=='normal':components={'Z':[0,.008,.008,.002,-.002,-.002,.004,.008,.010,.010,0,0]}
    elif kind=='mixed':components={'Z':[0,.006,.006,.0015,-.001,-.001,.003,.006,.008,.008,0,0],
                                  'X':[0,.006,.006,.0015,0,0,.003,.006,.008,.008,0,0]}
    else:raise ValueError('Only the two predeclared input fixtures exist')
    value=coupon();value['motions']=[];value['contacts']=[]
    value['time'].update(end_s=.004,field_interval_s=2.5e-5,history_interval_s=1e-5)
    value['interface_controls']=[default_control('BOND')]
    value['interface_histories']=[{'name':kind+'_'+axis.lower(),'material':'BOND','node_set':'MOVING',
        'component':axis,'time_s':list(clock),'displacement_mm':data,'frame':'MODEL_GLOBAL'} for axis,data in components.items()]
    value['responses']=[{'name':'damage','quantity':'cohesive_damage','identity':2,'component':'scalar'},
        {'name':'opening','quantity':'cohesive_opening','identity':2,'component':'normal'},
        {'name':'slip','quantity':'cohesive_slip','identity':2,'component':'tangent1'},
        {'name':'interface_global_zz','quantity':'stress','identity':2,'component':'zz'},
        {'name':'interface_global_xz','quantity':'stress','identity':2,'component':'xz'}]
    return value
