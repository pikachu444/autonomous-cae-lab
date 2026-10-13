"""Read retained Engine/history evidence only; no solver, converter or file writes."""
import argparse
import json
from pathlib import Path
from caelab.impact_model import validate_settings,engine_deck
from caelab.adapters.impact_results import history
from caelab.adapters.impact_timing import engine_termination,history_inventory,sample_coverage,energy_observations


def inspect(calculation,history_csv=None):
    root=Path(calculation).resolve(strict=True);native=root/'native'
    settings=validate_settings(json.loads((root/'input.json').read_text(encoding='utf-8')))
    if (native/'impact_0001.rad').read_text(encoding='ascii')!=engine_deck(settings):
        raise ValueError('Retained engine controls differ from their saved settings')
    termination=engine_termination(native/'impact_0001.out','',settings['time']['end_s'])
    if termination['status']!='NORMAL':raise ValueError('Native termination: '+termination['status'])
    csvpath=Path(history_csv).resolve(strict=True) if history_csv else native/'history.csv'
    responses,table=history(csvpath)
    inventory=history_inventory(native/'impactT01',table)
    coverage=sample_coverage([row['values'][0] for row in table['rows']],
                            settings['time']['end_s'],settings['time']['history_interval_s'])
    return {'native_termination':termination,'native_records':inventory,'history_coverage':coverage,
        'response_count':len(responses),'energy_observations':energy_observations(table,csvpath),
        'qualification':'UNKNOWN','decision':'NOT_RELEASED','solver_execution':'NOT_PERFORMED',
        'source_files_modified':False}


def main():
    parser=argparse.ArgumentParser(description='보존된 충격 계산의 종료 기록과 표본 범위를 읽습니다')
    parser.add_argument('--calculation',required=True)
    parser.add_argument('--history-csv',help='이미 변환한 CSV 사본 (생략하면 native/history.csv)')
    args=parser.parse_args()
    print(json.dumps(inspect(args.calculation,args.history_csv),ensure_ascii=False,indent=2))


if __name__=='__main__':main()
