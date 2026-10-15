"""Public SYNTHETIC verification fixture, never product material defaults.

Mg/mm/s. The material, initiation table and Gf are invented comparison inputs,
not identification of a real engineering material or an accepted native model.
"""
from pathlib import Path
from caelab import impact_model
from caelab.impact_bulk import default_law
from caelab.impact_damage import default_law as cohesive_law


def settings():
    root=Path(__file__).resolve().parents[1]
    text=(root/'cohesive-coupon.inp').read_text(encoding='ascii')
    text=text.replace('*MATERIAL,NAME=BOND','*PLASTIC\n100,0\n110,0.1\n150,1\n*MATERIAL,NAME=BOND')
    text+='*SURFACE,TYPE=ELEMENT,NAME=LOWERFACE\nLOWER,S2\n*SURFACE,TYPE=ELEMENT,NAME=UPPERFACE\nUPPER,S1\n'
    value=impact_model.default_settings();value['source'].update(title='SYNTHETIC bulk / finite-thickness interface',text=text)
    value['time'].update(end_s=.004,field_interval_s=.0001,history_interval_s=.00002)
    value['motions']=[{'node_set':'MOVING','mode':'velocity','height_mm':None,
        'velocity_mm_s':[0.,0.,25.],'omega_rad_s':[0.,0.,0.],
        'center_mm':[0.,0.,0.],'translation_mm':[0.,0.,0.]}]
    law=default_law('BULK')
    law['initiation'].update(eta=[-1.,0.,1.],rates_s_inv=[0.,100.],
        plastic_strain=[[.2,.1,.05],[.24,.12,.06]],sr_ref_s_inv=100.)
    law['evolution']['gf_n_mm']=.5
    law['calibration'].update(source='SYNTHETIC public regression inputs; NOT a material calibration',
                             temperature_range_K=[290.,300.],observed_temperature_K=293.15)
    value['bulk_damage']=[law]
    law=cohesive_law('BOND');law.update(normal_strength_mpa=2.,shear_strength_mpa=2.,mode_I_n_mm=.02,mode_II_n_mm=.02)
    value['cohesive']=[law]
    value['interface_controls']=[{'material':'BOND','compression':'INTACT_COMPRESSION_ISYM0',
        'reclosure':'COHESIVE_ONLY','contact_index':None,'contact_start_s':None}]
    value['b_responses']=[
        {'name':'BULK_DAMAGE','scope':'bulk','identity':1,'quantity':'damage_sum','component':'scalar'},
        {'name':'BULK_ACTIVE','scope':'bulk','identity':1,'quantity':'active','component':'scalar'},
        {'name':'BULK_IE_DENSITY','scope':'bulk','identity':1,'quantity':'internal_energy_density','component':'scalar'},
        {'name':'BOND_FACE','scope':'interface','identity':2,'quantity':'face_separation','component':'normal'},
        {'name':'BOND_ACTIVE','scope':'interface','identity':2,'quantity':'cohesive_active','component':'scalar'}]
    return value


if __name__=='__main__':
    import argparse,json
    parser=argparse.ArgumentParser(description='합성 B 정의 출력. native 실행/설치 없음')
    parser.add_argument('output',type=Path)
    args=parser.parse_args()
    if args.output.exists():raise SystemExit('기존 입력을 덮지 않습니다')
    value=settings();impact_model.validate_settings(value)
    args.output.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
