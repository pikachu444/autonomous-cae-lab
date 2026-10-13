"""Public synthetic FE input for the product adapter, not a replacement evaluator."""
from pathlib import Path
from caelab.impact_model import default_settings,BACKEND


def settings():
    result=default_settings()
    path=Path(__file__).with_name('user-solid.inp')
    result['source'].update(title='공개 변형체 예제',text=path.read_text(encoding='ascii'),
                            provenance={'example':'synthetic / no engineering qualification'})
    result['motions']=[{'node_set':'BODY','mode':'velocity','height_mm':None,
        'velocity_mm_s':[0.,0.,-100.],'omega_rad_s':[0.,0.,0.],
        'center_mm':[0.,0.,0.],'translation_mm':[0.,0.,0.]}]
    return result


def main():
    import argparse
    from caelab.workbench_client import Client
    parser=argparse.ArgumentParser(allow_abbrev=False)
    parser.add_argument('--service',required=True)
    parser.add_argument('--run',action='store_true')
    args=parser.parse_args()
    client=Client(args.service)
    doc=client.document_open(kind='simulation',title='공개 FE 운동',draft={'backend':BACKEND,'settings':settings()})
    import uuid
    def command(operation):
        nonlocal doc
        reply=client.document_command(doc['id'],operation,{},session_id=doc['session_id'],
            expected_generation=doc['generation'],command_id='C'+uuid.uuid4().hex)
        doc=reply.get('document',doc);return reply
    command('document.save')
    print('Saved Simulation:',doc['id'])
    if args.run:
        reply=command('simulation.evaluate')
        print('Explicit submitted job:',reply['job']['id'])


if __name__=='__main__':main()
