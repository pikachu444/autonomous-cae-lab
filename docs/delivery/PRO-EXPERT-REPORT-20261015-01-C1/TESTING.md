# C1 검사 기록과 증거 수준

기준: 첨부 4ac2e2a + 실제 첫 인도 additions.patch/integration.patch + C1 세 패치.
실제 명령/환경/clean apply 결과는 배포 validation/에 있다. 작성 도중 로그는 최종 수용 로그로
사용하지 않는다. clean replay 결과와 파일별 SHA/CRC 확인 후 배포한다.

## 이 작업에서 실행한 검사

```text
PYTHONPATH=.:tests python -m pytest -q tests/test_report_image*.py --disable-warnings
PYTHONPATH=.:tests python -m pytest -q tests/test_experiment_report.py -k "exact_absent_time or snapshot_numeric_scalars or exact_nested_candidate or saved_optimization_reduction" --disable-warnings
```

| 검사 모듈 | case 수 | 실행 성격 |
|---|---:|---|
| report_image_core (첫 인도, 갱신 포함) | 54 | 실제 Report owner/파일/pin/Undo/저장, 합성 PNG |
| report_image_connection | 10 | scripted transport/capture lifecycle |
| report_image_vtk | 25 | 실제 VTK analytic geometry/XML 저장·읽기 |
| report_image_native_contract (갱신 포함) | 18 | 실제 VTK + 모의 ParaView/SaveScreenshot |
| report_image_axis_c1 | 34 | 공개 analytic 축/정적/frozen/과거 개정/보존 자산 |
| report_image_blocks_c1 | 33 | 검토한 ParaView raw SM property 모의 API |
| report_image_origin_c1 | 54 | 실제 Report owner/pin + 모의 registry/transport/launcher |
| report_image_launch_c1 | 12 | 기존 desktop._post 실제 코드, Popen/실행파일 선택 모의 |
| report_image_origin_native_c1 | 15 | 실제 VTK exact data + 모의 ParaView owner |
| **전용 합계** | **255 passed** | **Qt 두 모듈은 별도 skipped** |
| 기존 Report 회귀 | **5 passed** | exact time/숫자·비유한 값/선택 후보/축약값 보존 |

실제 환경은 Linux Python 3.13.5, VTK 9.6.2이며 environment.json에 버전을 기록했다.
전용 실행의 경고 77건은 VTK 호출 API의 deprecation 계열이며 경고 상세를 별도 stdout에 남겼다.
오류/경고를 native Windows 통과로 해석하지 않는다.

PySide6 부재로 test_report_image_qt.py와 test_report_image_qt_c1.py 두 모듈을 collection에서
skip했다. 기존 5개 + C1 8개 = **Qt/PDF/widget case 13개는 미실행**이다. 2 skipped를 ‘검사 두 개만
남음’으로 해석하지 않는다. C1 PDF 생성/한글 렌더/native 인쇄가 통과했다고 주장하지 않는다.

C1 테스트에서 실제 subprocess/ParaView/provider/solver/실장비 호출은 하지 않았다.
필수 compiled/AST 검사는 변경/추가 Python 원문에 대해 실행했다. 현재 main 전체/전체 Workbench
bootstrap은 검사하지 않았다. 첨부 선별 ZIP에 apps.desktop_pre/apps.lab 등 전체 bootstrap 소스가
완비되어 있다고 가정하거나 가짜 모듈로 채우지 않았다.

## 사용자가 전달한 별도 Windows 첫 인도 기록

CORRECTION.md 15–25행의 보고이며 이 Linux 실행/독립 재검증 결과가 아니다.
main 5f6aede의 별도 사본에 첫 인도를 적용: 69 passed, 2 VTK/native-contract 모듈 skipped.
Qt 5개는 실제 실행했고 normal/narrow Report 창 및 QTest Tab/capture/poll/cancel도 확인했다고 했다.
사용한 PNG/transport는 공개 합성/모의였으며 실제 ParaView capture/provider/solver는 미실행이다.
native_check receipt exit0/job_empty와 기존 QPrinter 0x80040155 진단이 있었다. 실제 PDF 생성·검사
성공과 일반 native 인쇄 수용은 구분한다. 그 진단을 삭제하거나 C1 인쇄 수용으로 바꾸지 않았다.
Sol viewport-fit 보완은 별도 gui-fit.patch이며 C1의 show_origin hunk와 독립적으로 유지한다.

## 최종 판정

세 결함에 대한 실제 코드, analytic/모의 회귀, 패치 적용 가능성을 제출한다. source review로 확인한
ParaView API가 설치 binary에서 그대로 수용되는지와 실제 Windows capture/원자료 재열기/C1 Qt/PDF는
WINDOWS_ACCEPTANCE.md에 남긴다. 새로운 임의 API 호출이나 mock 실행으로 이를 완료하지 않는다.
