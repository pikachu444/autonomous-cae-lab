"""Common entrypoint checks after applying integration.patch; no GUI/solver claims."""
from types import SimpleNamespace as NS
import xml.etree.ElementTree as ET
import pytest
from caelab.beam_model import OPERATIONS


def integrated():
    from apps.desktop_pre import bridge
    if not set(OPERATIONS)<=set(bridge.OPERATIONS):pytest.skip('Apply integration.patch to exercise common entrypoints')


def test_owner_broker_backend_share_beam_operations():
    integrated()
    from caelab.native_commands import CAPABILITIES
    from caelab.backends import get_backend
    from caelab.adapters.beam_fem import BeamFemCalculixAdapter
    assert set(OPERATIONS)<=CAPABILITIES['pre']
    backend=get_backend('structure.calculix.beam')
    assert isinstance(backend,BeamFemCalculixAdapter)


def test_offline_beam_save_uses_same_owner_and_no_new_controller():
    integrated()
    from apps.desktop_pre.connection import Connection
    sent=[];owner=NS(doc=NS(Name='Beam'),document_id='Pbeam',session_id='Sbeam',generation=2,refresh=lambda:None)
    def dispatch(request):sent.append(request);return {'status':'COMPLETED','result':{'record':{'draft':{'section':{'width_mm':'1e'}}}}}
    owner.dispatch=dispatch
    connection=NS(owners={'Beam':(owner,None,NS(stop=NS(is_set=lambda:True),registered=NS(is_set=lambda:False)))},
        panels={},native_requests={})
    values=[]
    result=Connection.submit_native(connection,'pre.beam.draft',{'analysis_id':'A','draft':{'section':{'width_mm':'1e'}}},
        owner=owner,on_done=values.append)
    assert result['completed'] and len(sent)==1 and sent[0]['document_id']=='Pbeam'
    assert values[0]['record']['draft']['section']['width_mm']=='1e'


def test_freeze_to_existing_submission_retains_exact_identity():
    integrated()
    from apps.desktop_pre.beam_menu import start_run
    owner=NS(doc=NS(Name='Beam'),document_id='Pbeam',session_id='Sbeam',generation=7,refresh=lambda:None,
        beam=NS(inspect=lambda key:{'can_freeze':True}))
    sent=[];connection=NS(pending=None,native_requests={},panels={})
    connection.send_command=lambda:sent.append(connection.pending.copy())
    start_run(connection,owner,'Analysis')
    assert sent[0]['operation']=='pre.beam.freeze' and sent[0]['arguments']=={'analysis_id':'Analysis'}
    assert sent[0]['generation']==7 and sent[0]['session_id']=='Sbeam'
    with pytest.raises(ValueError):start_run(connection,owner,'Analysis')


def test_registrar_reuses_four_file_contract(tmp_path):
    integrated()
    from test_beam_support import snapshot
    from caelab.native_inputs import register_frozen_input
    source=snapshot(tmp_path/'exchange'/'Pbeam'/'Fbeam')
    receipt=register_frozen_input(tmp_path/'workspace',tmp_path/'exchange',source,'Dbeam',
        root_id='native-owner:Pbeam',relative='Pbeam/Fbeam/snapshot.json',limit=8*1024**2)
    assert receipt['kind']=='frozen_beam' and receipt['format']=='freecad-beam' and len(receipt['files'])==5


def test_beam_post_exports_section_forces_and_moments_without_stress_aliases(tmp_path):
    integrated()
    from test_beam_support import model, frd
    from caelab.beam_results import read_frd, write_post
    beam=model();raw=frd(beam,times=(.5,1.))
    source=tmp_path/'beam.frd';source.write_text(raw,encoding='ascii')
    observed=read_frd(source,beam)
    artifact=write_post(tmp_path/'post',observed,beam,source_status='SUCCEEDED')
    metadata={row['name']:row for row in artifact['native_metadata']['arrays']}
    datasets=ET.parse(tmp_path/'post'/'beam.pvd').findall('./Collection/DataSet')
    assert [float(row.get('timestep')) for row in datasets]==[.5,1.]
    # This is synthetic FRD-to-Post integration, not a native solver result.
    expected={'V1':(11.,'N'),'V2':(22.,'N'),'N':(33.,'N'),
              'Mt':(44.,'Nmm'),'M1':(55.,'Nmm'),'M2':(66.,'Nmm')}
    for dataset in datasets:
        point=ET.parse(tmp_path/'post'/dataset.get('file')).find('./UnstructuredGrid/Piece/PointData')
        arrays={row.get('Name'):row for row in point.findall('DataArray')}
        assert set(arrays)==set(metadata)-{'NativeElementId'}
        assert not any('stress' in name.lower() or 'mises' in name.lower() for name in arrays)
        for name,(value,unit) in expected.items():
            assert metadata[name]['units']==unit and arrays[name].get('NumberOfComponents')=='1'
            assert [float(x) for x in arrays[name].text.split()]==[value*float(dataset.get('timestep'))]*5
    assert source.read_text(encoding='ascii')==raw
