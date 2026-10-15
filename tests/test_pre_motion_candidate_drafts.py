"""M1 draft admission into M4; native-shaped doubles, no native execution."""
from copy import deepcopy

import pytest

from assembly_pose_doubles import source_fixture
from apps.desktop_pre.assembly_pose_candidate import PoseCandidates
from apps.desktop_pre.assembly_pose_geometry import select_frame


def test_saved_relation_draft_blocks_candidate_but_keeps_results_readable_and_repairable(tmp_path, monkeypatch):
    owner, assembly, _ = source_fixture(tmp_path, monkeypatch)
    before = deepcopy(owner.read_metadata()['motion_paths'])
    assert select_frame(owner, assembly.Name, 'Kfixture', 2)
    data = owner.read_metadata()
    draft = {'view': {'joint_id': None, 'drive_row': 0, 'trace_row': -1}, 'joint_draft': None,
             'definition_draft': {'drives': [{'relation': {'expression': 'amplitude*sin(A)',
                 'constants': [{'name': 'amplitude', 'value': '1e', 'unit': 'deg'}]}}]}}
    data['motion_editors'] = {assembly.Name: draft}
    owner.write_metadata(data)  # Already saved raw snapshot; actual save validation is tested separately.
    with pytest.raises(ValueError, match='편집을 적용하거나 취소'):
        select_frame(owner, assembly.Name, 'Kfixture', 2)
    job = PoseCandidates(owner)
    failed = job.start({'calculation_id': 'Kfixture', 'frame': 2}, {'assembly_id': assembly.Name}, automatic=False)
    assert failed['state'] == 'FAILED' and '편집을 적용하거나 취소' in failed['message']
    assert not job.busy and job._document is None
    assert owner.motion._saved_result(assembly, 'Kfixture') == before['Kfixture']
    data = owner.read_metadata()
    data['motion_editors'][assembly.Name]['definition_draft'] = None
    owner.write_metadata(data)
    repaired = job.start({'calculation_id': 'Kfixture', 'frame': 2}, {'assembly_id': assembly.Name}, automatic=False)
    try:
        assert repaired['state'] == 'PREPARING' and job.busy
        assert owner.read_metadata()['motion_paths'] == before
    finally:
        job.cancel()
        job.advance()
