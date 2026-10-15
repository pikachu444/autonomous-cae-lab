"""New B1.3 contract regressions. All generated source values are synthetic."""
from copy import deepcopy
import hashlib
from io import BytesIO
from pathlib import Path
import xml.etree.ElementTree as ET
import pytest
from b13_raw_fixture import raw_model, write_sources
from caelab.beam_output import DEFAULT, mechanical_identity, compare_runs, element_axes
from caelab.beam_model import validate_model, validate_draft, check_draft_shape, BeamInputError
from caelab.beam_deck import render
from caelab.beam_results import read_frd, channels, post_metadata, post_files, final_responses


@pytest.mark.parametrize('angle',['0','90','180','270'])
def test_raw_roundtrip_axes_sparse_expansion_ids_and_actual_ip(tmp_path,angle):
    m=raw_model(angle);xyz,exp=write_sources(tmp_path,m)
    observed=read_frd(tmp_path/'beam.frd',m)
    assert observed['complete_file'] and len(observed['internal']['rows'])==100
    assert set(observed['coordinates_mm'])==set(xyz)
    assert observed['expansion'][88]['expanded']==tuple(exp[88])
    assert observed['internal']['rows'][0]['S']['values']==[2.,3.,4.,.5,.6,.7]
    assert observed['internal']['rows'][0]['S']['source_line']>1
    assert all(r['native_generalized_rotation'] is False for r in observed['frames'][0]['derived_rotations'])
    assert observed['frames'][0]['derived_rotations'][0]['value_rad']==pytest.approx([.001,.002,.003],abs=3e-7)
    metadata=post_metadata(observed,m,source_status='SUCCEEDED')
    internal=[r for r in metadata['arrays'] if r['name']=='S_internal']
    assert internal and internal[0]['association']=='CELLS'
    files=dict(post_files(observed,m,source_status='SUCCEEDED'))
    assert 'beam_raw_0000.vtu' in files and 'beam_ip_0000.vtu' in files
    ip=ET.fromstring(files['beam_ip_0000.vtu'])
    assert ip.find('.//PointData/DataArray') is None
    assert ip.find('.//CellData/DataArray[@Name="S_internal"]') is not None
    assert final_responses(observed,m)['beam_internal_S']['metadata']['association']=='CELLS'
    with pytest.raises(ValueError,match='SECTION FORCES'):
        channels(observed['frames'][0])


def test_piecewise_quarter_turns_actual_axes_and_distinct_source(tmp_path):
    m=raw_model(regional=True);write_sources(tmp_path,m)
    obs=read_frd(tmp_path/'beam.frd',m)
    assert render(m).count('*BEAM SECTION')==2
    assert obs['sections'][0]['declared_axes']!=obs['sections'][3]['declared_axes']
    wrong=deepcopy(m);wrong['element_axes']['88']['local1']=[1.,0.,0.]
    with pytest.raises(BeamInputError):validate_model(wrong)


def test_output_choice_is_explicit_and_mechanical_pair_is_not_a_single_run():
    left=raw_model();right=deepcopy(left);right['draft']['output']=deepcopy(DEFAULT)
    a,b=render(left),render(right)
    assert 'SECTION FORCES' not in a and 'OUTPUT=3D' in a
    assert 'SECTION FORCES' in b and 'OUTPUT=3D' not in b
    assert mechanical_identity(left)==mechanical_identity(right)
    pair=compare_runs(left,'RUN_A',right,'RUN_B')
    assert pair['same_run'] is False and pair['observations_merged'] is False
    with pytest.raises(ValueError):compare_runs(left,'RUN_A',right,'RUN_A')
    right['draft']['section']['width_mm']='11'
    with pytest.raises(ValueError,match='기계 입력'):compare_runs(left,'RUN_A',right,'RUN_B')


def test_invalid_output_reference_raw_can_save_but_not_apply():
    m=raw_model();m['draft']['output']['reference_mm'][0]='1e'
    check_draft_shape(m['draft'])
    assert any(r['path']=='output.reference_mm.0' for r in validate_draft(m['draft']))
    with pytest.raises(BeamInputError):validate_model(m)


@pytest.mark.parametrize('damage',['wrong_shape','wrong_element','swapped_nodes','wrong_axis','wrong_IP','middle_corruption','wrong_set'])
def test_raw_malformed_sources_are_not_promoted_to_partial(tmp_path,damage):
    m=raw_model();write_sources(tmp_path,m)
    path=tmp_path/'beam.12d'
    if damage=='wrong_shape':path.write_text(path.read_text().replace('C3D20RBR','C3D20RB',1))
    elif damage=='wrong_element':path.write_text(path.read_text().replace('ELEMENT 88','ELEMENT 87',1))
    elif damage=='swapped_nodes':path.write_text(path.read_text().replace('101 408 207','101 207 408',1))
    elif damage=='wrong_axis':
        other=raw_model('90');write_sources(tmp_path,other)
    elif damage=='wrong_IP':
        path=tmp_path/'beam.dat';path.write_text(path.read_text().replace('88 1 ','88 9 ',1))
    elif damage=='wrong_set':
        path=tmp_path/'beam.dat';path.write_text(path.read_text().replace('for set BEAM','for set FOREIGN',1))
    else:
        path=tmp_path/'beam.frd';path.write_text(path.read_text().replace(' -4  STRESS','GARBAGE\n -4  STRESS',1))
    with pytest.raises(ValueError):read_frd(tmp_path/'beam.frd',m,allow_partial=True)


def test_missing_DAT_and_EOF_remain_partial_without_filled_IP(tmp_path):
    m=raw_model();write_sources(tmp_path,m,end=False,dat=False)
    with pytest.raises(ValueError,match='Incomplete'):read_frd(tmp_path/'beam.frd',m)
    value=read_frd(tmp_path/'beam.frd',m,allow_partial=True)
    assert not value['complete_file'] and value['internal']['rows']==[]
    metadata=post_metadata(value,m,source_status='FAILED')
    assert metadata['beam']['observation_status']=='PARTIAL'
    assert not any(d['name']=='S_internal' for d in metadata['arrays'])


def test_section_force_reader_remains_disjoint(tmp_path):
    from test_beam_support import frd
    m=raw_model();write_sources(tmp_path,m)
    (tmp_path/'beam.frd').write_text(frd(m),encoding='ascii')
    with pytest.raises(ValueError):read_frd(tmp_path/'beam.frd',m)


def test_axis_region_gaps_overlap_and_local_end_ambiguity_rejected():
    m=raw_model(regional=True)
    m['draft']['axis_regions'][1]['elements']=[88]
    with pytest.raises(BeamInputError):validate_model(m)
    m=raw_model(regional=True);m['draft']['axis_regions'].pop()
    with pytest.raises(BeamInputError):validate_model(m)
    m=raw_model(regional=True);m['draft']['ends'][0]['system']='local'
    with pytest.raises(BeamInputError):validate_model(m)


def test_exact_native_fifty_point_rule_is_not_hex8_or_generic_gauss5(tmp_path):
    from caelab.beam_gauss import B32R_RECT_GAUSS50 as g
    assert len(g)==50
    assert g[8]==(-.577350269189626,-.9258200998,-.9258200998)
    assert g[18]==(-.577350269189626,0.,0.)
    assert g[29]==(.577350269189626,-.9258200998,-.9258200998)
    assert g[-1]==(.577350269189626,.9258200998,.9258200998)
    m=raw_model();write_sources(tmp_path,m)
    result=read_frd(tmp_path/'beam.frd',m)
    assert {r['integration_point'] for r in result['internal']['rows']}==set(range(1,51))


def test_reported_ip_coordinates_must_match_actual_expansion_not_reference_line(tmp_path):
    m=raw_model();write_sources(tmp_path,m)
    path=tmp_path/'beam.dat';text=path.read_text();a,b=text.split('global coordinates',1)
    lines=b.splitlines()
    for i,line in enumerate(lines):
        p=line.split()
        if len(p)==5 and p[0].isdigit():
            p[2]=str(float(p[2])+1.);lines[i]=' '.join(p);break
    path.write_text(a+'global coordinates'+'\n'.join(lines)+'\n')
    with pytest.raises(ValueError,match='COORD does not match'):
        read_frd(tmp_path/'beam.frd',m,allow_partial=True)
