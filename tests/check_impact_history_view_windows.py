"""Three retained-history views at the pinned helper boundary; no native run."""
import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--snapshot',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--domain-sha',required=True)
    args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=False)
    digest=lambda path:hashlib.sha256(path.read_bytes()).hexdigest()
    domain=ROOT/'caelab/impact_responses.py';assert digest(domain)==args.domain_sha.lower()
    from PySide6.QtWidgets import QApplication
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    from apps.research.appearance import apply_appearance
    from apps.research.impact_history_view import ImpactHistoryView
    from caelab.impact_responses import select_history
    snapshot=json.loads(args.snapshot.read_text(encoding='utf-8'));before=deepcopy(snapshot)
    original_sha=digest(args.snapshot)
    app=QApplication([]);apply_appearance(app);view=ImpactHistoryView(snapshot)
    records=[];signals=[]
    try:
        view.study_requested.connect(lambda value:signals.append(value))
        view.plan_requested.connect(lambda value:signals.append(value))
        view.show();view.resize(800,715)
        for name,channel,transform in [('mean-force','PAIR_force_FNZ','identity'),
                ('native-impulse','PAIR_native_impulse_FNZ','identity'),
                ('sample-integral','PAIR_force_FNZ','sample_trapezoid')]:
            view.channel.setCurrentIndex(view.channel.findData(channel))
            view.start.setCurrentIndex(1)
            view.transform.setCurrentIndex(view.transform.findData(transform));app.processEvents()
            view.table.setFocus();view.table.selectRow(13);app.processEvents()
            packet=view.selected;assert packet==select_history(snapshot,packet['selection']['request'])
            semantics=packet['selection']['semantics']
            if name=='mean-force':
                assert semantics['conversion_kind']=='DERIVED_SECANT'
                assert semantics['display_scale_from_native'] is None
                assert '실제 원 구간 시간 [s]' in view.meaning.text()
                assert '→ 표시 N (배율' not in view.meaning.text()
            elif name=='sample-integral':
                assert semantics['conversion_kind']=='DERIVED_SAMPLE_TRAPEZOID'
                assert semantics['display_scale_from_native'] is None
                assert packet['response']['raw_samples']['transformed_values'][0]==0.
                assert '원 누적 충격량 관측이 아닙니다' in view.meaning.text()
            else:assert '원 접촉쌍 누적 충격량' in view.meaning.text()
            QTest.mouseClick(view.study_button,Qt.MouseButton.LeftButton)
            QTest.mouseClick(view.plan_button,Qt.MouseButton.LeftButton)
            assert signals[-2:]==[packet,packet]
            assert view.grab().save(str(args.output/(name+'-narrow.png')))
            records.append({'view':name,'selection_sha256':packet['selection_sha256'],
                'request':packet['selection']['request'],'semantics':semantics,
                'selected_source_row':packet['rows'][view.table.currentRow()]['source_row'],
                'caption':view.meaning.text()})
        assert snapshot==before and digest(args.snapshot)==original_sha
        assert digest(domain)==args.domain_sha.lower()
        sources={str(p.relative_to(ROOT)):digest(p) for p in [domain,
            ROOT/'apps/research/impact_history_view.py',Path(__file__).resolve()]}
        (args.output/'manifest.json').write_text(json.dumps({'status':'PASS_SCOPED_FINAL_DELTA',
            'source_sha256':sources,'snapshot_sha256':original_sha,'source':snapshot['source'],
            'views':records,'same_packet_both_signals':True,'snapshot_unchanged':True,
            'qt_platform':app.platformName(),'new_core_native_provider_jobs':0,
            'physical_OS_input':False},ensure_ascii=False,indent=2),encoding='utf-8')
    finally:
        view.close();view.deleteLater();app.processEvents()


if __name__=='__main__':main()
