"""User-model path example; only --run explicitly submits an existing backend."""
from pathlib import Path
from caelab.impact_model import default_settings,model_from_settings,BACKEND
from caelab.impact_source import capture
from caelab.impact_sets import create_node_set,create_surface


def settings(root=None):
    root=Path(root) if root else Path(__file__).with_name('include-project')
    result=default_settings();result['source']=capture(root/'model.inp',root)
    model=model_from_settings(result)
    result['generated_sets']=[create_node_set(result['source'],model,'MOVEMENT','MOVING'),
        create_surface(result['source'],model,'LOWER_CONTACT','BASE','exterior',[(1,'S2')]),
        create_surface(result['source'],model,'UPPER_CONTACT','MOVING','exterior',[(2,'S1')])]
    result['motions']=[{'node_set':'MOVEMENT','mode':'velocity','height_mm':None,
        'velocity_mm_s':[0.,0.,-10.],'omega_rad_s':[0.,0.,0.],
        'center_mm':[5.,5.,1.52],'translation_mm':[0.,0.,0.]}]
    result['contacts']=[{'a':'UPPER_CONTACT','b':'LOWER_CONTACT','law':'TYPE24','friction':0.}]
    result['time'].update(end_s=.004,field_interval_s=.0002,history_interval_s=.0001)
    result['responses']=[{'name':'top_z','quantity':'displacement','identity':15,'component':'Z'},
        {'name':'contact_z','quantity':'contact_force','identity':11,'component':'Z'}]
    return result


def main():
    import argparse,uuid,json
    from caelab.workbench_client import Client
    from caelab.impact_source import export_effective
    p=argparse.ArgumentParser(allow_abbrev=False)
    p.add_argument('--service');p.add_argument('--export',type=Path);p.add_argument('--run',action='store_true')
    a=p.parse_args();s=settings()
    if a.export:export_effective(s,a.export);print('INP:',a.export)
    if a.run and not a.service:p.error('--run requires --service')
    if not a.service:
        if not a.export:p.error('Choose --service or --export')
        return
    client=Client(a.service)
    doc=client.document_open(kind='simulation',title='두 물체 충격',draft={'backend':BACKEND,'settings':s})
    def command(operation):
        nonlocal doc
        reply=client.document_command(doc['id'],operation,{},session_id=doc['session_id'],expected_generation=doc['generation'],command_id='C'+uuid.uuid4().hex)
        doc=reply.get('document',doc);return reply
    command('document.save');print('Saved Simulation:',doc['id'])
    if a.run:print('Submitted job:',command('simulation.evaluate')['job']['id'])


if __name__=='__main__':main()
