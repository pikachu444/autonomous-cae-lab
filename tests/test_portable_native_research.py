"""One mixed real-owner workflow; supplied saved native file, no native launch."""
import importlib.util
import os
from pathlib import Path


def test_mixed_copy_cold_edit_save_recopy_preserves_native_and_failed_research(tmp_path):
    root = Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location('public_mixed_native_research',
        root / 'examples/native-project-research/public_mixed.py')
    example = importlib.util.module_from_spec(spec); spec.loader.exec_module(example)
    # Public committed native bytes keep this runnable in ordinary CI. The
    # bounded Windows acceptance uses N1's already-saved public XLink archive.
    native = Path(os.environ.get('CAE_PUBLIC_NATIVE_PROJECT',
        str(root / 'tests/fixtures/native_single_solid/public_box.FCStd')))
    result = example.run(tmp_path / '함께 옮기는 연구', native,
        post_project=os.environ.get('CAE_PUBLIC_POST_PROJECT'), post_root=os.environ.get('CAE_PUBLIC_POST_ROOT'))
    assert result['status'] == 'PASSED' and result['read_edit_save']
    assert result['study_report_sources_available']
    assert result['frozen_assets_unchanged']
    assert result['different_snapshot_rejected']
    expected_kinds = ['native_post', 'native_pre'] if os.environ.get('CAE_PUBLIC_POST_PROJECT') else ['native_pre']
    assert result['native_kinds'] == expected_kinds
    assert result['original_sources_blocked'] and result['native_snapshot_unchanged']
    assert result['new_jobs'] == 0 and result['verification'] == 'READY'
    assert set(result['states']) == {'SUCCEEDED', 'FAILED'}
    assert result['solver_provider_native_launch'] == 'NOT_RUN'
