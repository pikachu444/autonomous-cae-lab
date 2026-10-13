"""Save a public synthetic LAW117 coupon; --run alone requests actual execution."""
import argparse
from pathlib import Path
from caelab.impact_model import default_settings,BACKEND
from caelab.workbench_client import Client


def settings():
    value=default_settings()
    path=Path(__file__).with_name('cohesive-coupon.inp')
    value['source'].update(title='공개 응집 시편',text=path.read_text(encoding='ascii'),
        provenance={'purpose':'synthetic workflow fixture, not a calibrated law'})
    value['cohesive']=[{'material':'BOND','law':'LAW117','normal_strength_mpa':2.,
        'shear_strength_mpa':2.,'mode_I_n_mm':.02,'mode_II_n_mm':.02,
        'criterion':'POWER','power_exponent':1.,'bk_exponent':1.,'gamma':1.,'deletion_points':1}]
    value['motions']=[{'node_set':'MOVING','mode':'velocity','height_mm':None,
        'velocity_mm_s':[0.,0.,20.],'omega_rad_s':[0.,0.,0.],'center_mm':[0.,0.,0.],'translation_mm':[0.,0.,0.]}]
    value['time'].update(end_s=.001,field_interval_s=.00005,history_interval_s=.00001)
    value['responses']=[
        {'name':'damage','quantity':'cohesive_damage','identity':2,'component':'scalar'},
        {'name':'opening','quantity':'cohesive_opening','identity':2,'component':'normal'},
        {'name':'top_stress','quantity':'stress','identity':3,'component':'zz'},
        {'name':'top_acceleration','quantity':'acceleration','identity':13,'component':'Z'}]
    return value


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--service',required=True);parser.add_argument('--run',action='store_true')
    args=parser.parse_args();client=Client(args.service)
    doc=client.document_open(kind='simulation',title='응집 시편',draft={'backend':BACKEND,'settings':settings()})
    def command(op):
        nonlocal doc
        receipt=client.document_command(doc['id'],op,{},session_id=doc['session_id'],expected_generation=doc['generation'])
        doc=receipt.get('document',doc);return receipt
    command('document.save')
    print(doc['id'])
    if args.run:print(command('simulation.evaluate')['job']['id'])


if __name__=='__main__':main()
