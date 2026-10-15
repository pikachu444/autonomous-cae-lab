"""Real analytic VTK result/fingerprint, MOCK ParaView/owner/activation only."""
import os
from copy import deepcopy
import sys
from types import SimpleNamespace

import pytest
vtk = pytest.importorskip('vtk', reason='VTK native contract is NOT_RUN without VTK')
from caelab.report_image import make_origin
from caelab.post_observation import file_pin
from apps.desktop_post.report_image_origin_native import verify_live
from report_image_block_fixture import lookup
from test_report_image_native_contract import native


def origin(n):
    return make_origin(file_pin(n.f['manifest']), 'Dpost', 'Snative', os.getpid(), 'Fresult', 'Rresult')[0]


def active(n):
    p = sys.modules['paraview'].simple
    p.GetActiveSource = lambda: n.source
    p.GetActiveView = lambda: n.view
    return p


def test_native_verifier_reads_exact_saved_raw_values_without_scene_edit(native):
    n = native; active(n); expected = origin(n)
    before = deepcopy(n.view.props)
    result = verify_live(n.workspace, origin=expected, expected_view_generation=3)
    assert result['status'] == 'SOURCE_VERIFIED' and result['revision'] == 'Rresult'
    assert result['native_pid'] == os.getpid() and result['historical_view_restored'] is False
    assert n.view.props == before and n.calls == []  # no Render/SaveScreenshot for a live verification


@pytest.mark.parametrize('fault', ['time', 'values', 'active', 'pending', 'viewGeneration', 'project'])
def test_native_wrong_state_or_data_is_not_exact_origin(native, fault):
    n = native; p = active(n); expected = origin(n)
    if fault == 'time': n.data.GetInformation().Set(vtk.vtkDataObject.DATA_TIME_STEP(), .5)
    if fault == 'values': n.data.GetPointData().GetArray('stress').SetTuple1(0, 900)
    if fault == 'active': p.GetActiveSource = lambda: SimpleNamespace(identifier='other')
    if fault == 'pending': n.source.pending = ['Value']
    if fault == 'viewGeneration': n.workspace.owner.view_generation += 1
    if fault == 'project': n.workspace.owner.project_path = n.f['manifest'].parent/'other.json'
    with pytest.raises((ValueError, OSError)): verify_live(n.workspace, origin=expected, expected_view_generation=3)
    assert n.calls == []


@pytest.mark.parametrize('fault', ['generation', 'view', 'source'])
def test_change_during_fetch_rejects_confirmation(native, fault):
    n = native; active(n); expected = origin(n)
    def fetch(_):
        if fault == 'generation': n.workspace.owner.generation += 1
        elif fault == 'view': n.workspace.owner.view_generation += 1
        else: n.f['source'].unlink()
        return n.data
    sys.modules['paraview'].servermanager.Fetch = fetch
    with pytest.raises((ValueError, OSError)): verify_live(n.workspace, origin=expected, expected_view_generation=3)


@pytest.mark.parametrize('fault', ['temperature', 'component', 'solid', 'RGB'])
def test_global_stress_with_hidden_legend_and_block_override_rejected_before_screenshot(native, fault):
    n = native; raw = n.rep.SMProxy
    raw.properties['BlockColorArrayNames'].values = ['/Root/Other', '0', 'stress']
    raw.properties['BlockLookupTables'].values = [n.lut]
    if fault == 'temperature': raw.properties['BlockColorArrayNames'].values[2] = 'temperature'
    if fault == 'component': raw.properties['BlockLookupTables'].values = [lookup('otherLut', component=1)]
    if fault == 'solid': raw.properties['BlockColors'].values = ['/Root/Other', '1', '0', '0']
    if fault == 'RGB': raw.properties['BlockMapScalars'].values = ['/Root/Other', '0']
    with pytest.raises(ValueError): n.workspace.export(object_ref='Fresult', format='png', report_snapshot=True)
    assert not any(call[0] == 'SaveScreenshot' for call in n.calls)


def test_equal_block_assignment_changes_during_capture_still_rejects(native):
    n = native
    def change():
        n.rep.SMProxy.properties['BlockColorArrayNames'].values = ['/Root/Other', '0', 'stress']
        n.rep.SMProxy.properties['BlockLookupTables'].values = [n.lut]
    n.changes.append(change)
    with pytest.raises(ValueError, match='캡처 중'):
        n.workspace.export(object_ref='Fresult', format='png', report_snapshot=True)
    assert sum(call[0] == 'SaveScreenshot' for call in n.calls) == 1
