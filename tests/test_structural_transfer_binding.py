"""TR-U condition binding against the existing compiler; no native execution."""
from copy import deepcopy
import json
import pytest
from caelab.contact import separate_meshes
from caelab.contact_deck import UNITS,render
from caelab.contact_steps import default_program,compile_program
from caelab.storage import canonical_hash
from caelab.structural_field_transfer import prepare_transfer
from caelab.structural_field_ports import bind_transfer_model
from examples.structural_u_transfer import subdivided_receiver,transfer_definition
from test_structural_field_transfer import source


def captured_case():
    field=source();receiver=subdivided_receiver(field)
    m=separate_meshes([{'body_id':'Solid',
        'nodes':[{'node_id':n,'position_mm':p} for n,p in zip(receiver['node_ids'],receiver['coordinates'])],
        'elements':deepcopy(receiver['elements'])}],minimum_bodies=1)
    for row in m['nodes']:row['native_position_mm']=list(row['position_mm'])
    for row in m['elements']:row['type']='C3D10'
    dofs=[{'node_id':n,'component':d,'value_mm':0.} for n in receiver['boundary_node_ids'] for d in (1,2,3)]
    m.update(kind='freecad-contact-mesh',schema_version='1',units=dict(UNITS),analysis_scope='single_solid_static',
        materials=[{'body_id':'Solid','object_id':'Steel','law':'isotropic_linear_elastic',
                    'young_modulus_MPa':210000.,'poisson_ratio':.3}],contacts=[],loads=[],boundary_dofs=dofs,
        conditions=[{'object_id':'TransferBoundary','type':'Fem::ConstraintFixed','body_id':'Solid',
                     'components_mm':{1:0.,2:0.,3:0.},'boundary_dofs':deepcopy(dofs)}],
        step={'initial':1.,'period':1.,'minimum':1e-5,'maximum':1.,'increments':2000,
              'geometry':'linear','automatic':True,'matrix_solver':'default','controls':None},
        output={'frequency':1,'nodal':['U','RF','S','E'],'pair':[]})
    m['analysis_steps']=default_program(m['step'],m['conditions'])
    m=json.loads(json.dumps(m))
    receipt=prepare_transfer(field,receiver,transfer_definition(field))
    return m,receipt


def test_exact_zero_boundary_is_explicitly_replaced_and_existing_writer_owns_all_cards():
    captured,receipt=captured_case();before=deepcopy((captured,receipt))
    bound=bind_transfer_model(captured,receipt)
    assert (captured,receipt)==before
    assert len(bound['conditions'])==34 and len(bound['boundary_dofs'])==102
    assert 35 not in {r['node_id'] for r in bound['boundary_dofs']}
    lineage=bound['displacement_transfer']
    assert lineage['captured_model_sha256']==canonical_hash(captured)
    assert lineage['original_boundary_dofs']==captured['boundary_dofs']
    assert lineage['source']==receipt['source'] and lineage['rows']==receipt['rows']
    steps=compile_program(bound['analysis_steps'],bound['conditions'])
    assert len(steps)==1 and len(steps[0]['boundary'])==102
    deck=render(bound)
    assert steps[0]['loads']=={} and '*INITIAL CONDITIONS' not in deck
    assert '*AMPLITUDE' in deck and '*BOUNDARY' in deck and '*STATIC' in deck
    assert bind_transfer_model(captured,json.loads(json.dumps(receipt)))==bound


@pytest.mark.parametrize('mutation',['hash','missing_dof','changed_value','mask','integer_mask','wrong_boundary','edited_step','extra_support'])
def test_invalid_or_changed_binding_never_changes_original_capture(mutation):
    captured,receipt=captured_case()
    if mutation=='hash':receipt['receiver_sha256']='0'*64
    elif mutation=='missing_dof':receipt['boundary_dofs'].pop()
    elif mutation=='changed_value':receipt['boundary_dofs'][0]['value_mm']=1.
    elif mutation=='mask':receipt['mask'][0]=False
    elif mutation=='integer_mask':receipt['mask'][0]=1
    elif mutation=='wrong_boundary':captured['conditions'][0]['object_id']='OtherSupport'
    elif mutation=='edited_step':captured['analysis_steps']['steps'][0]['label']='explicitly edited'
    elif mutation=='extra_support':captured['conditions'].append(deepcopy(captured['conditions'][0]))
    before=deepcopy((captured,receipt))
    with pytest.raises(ValueError):bind_transfer_model(captured,receipt)
    assert (captured,receipt)==before
