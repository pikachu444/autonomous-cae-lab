# 실제 확인과 남은 범위

기준 de7de4e, 2026-10-16 Windows Python3.12.14/PySide6 6.9.1. 기존 전용 runtime과 scikit-fem12.0.2·SciPy1.17.0 평가기를 사용했다. source/pin·각 실행 명령·현재 파일 SHA와 receipt는 로컬 `_workspace/delivery-portable-physics/FINAL_MANIFEST.json`에 기록한다. 제품의 공학적 판정은 NOT_RELEASED/UNKNOWN 그대로다.

## 실제 작은 물리 평가와 독립 재개

`actual-01/native-check.json`: exit0, 51.9초, Job `job_empty`. parent8168, cold1 3160, cold2 45108은 서로 다른 프로세스다.

- 원 PDE: `pde.scikit_fem.dimensioned`, 현재 선언의 정상 선형 약형식, 온도 [K]·좌표 [m], 원 기준 오차·residual 관문 유지. 원 결과 디렉터리16파일을 해시로 보존했다.
- 원 Simulation: `thermal.scikit_fem.rectangle`, 정상 열전도·기존 Picard/온도/잔차 관문. 실제 온도장 [K]와 원 결과52파일을 보존했다.
- 원 두 평가 후 사본 생성, 원 store를 shutdown하고 `.preserved`로 이동. cold1에서 원 결과·모든 파일 SHA·원 제출 입력을 비교하고 현지 편집/Undo/Redo/저장했다. **명시 새 실행만** 각 평가기1회, 새 job2개로 계산했다. 원 결과는 이전 입력에 남았다.
- 새 결과까지 저장/재복사하고 첫 사본을 `.preserved`로 옮긴 뒤 cold2에서 두 세대 결과·원 파일·현재 편집을 확인했다. 추가 평가 없이 다시 편집/Undo/Redo/저장했다.

총 네 번의 작은 실제 평가(원2+현지2)이며 native 솔버 benchmark/캠페인이 아니다. provider/Expert/FreeCAD/ParaView/WSL/설치/유료 호출0. 읽기·편집·저장·재복사 동안 `evaluation.run`/submit/live status·result를 거부하도록 확인했다. 원/첫 사본과 원 실패 기록은 삭제하지 않았다. `actual-01/observations.json`은 원 result reader에서 읽은 물리량/단위/파일 수이며 새 결과를 만들지 않는다.

## 영향 계약과 실패 반례

중복 없는 전용 pytest **21개**를 확인했다.

| 실행 | 개수 | 범위 |
|---|---:|---|
| contracts-02 |14| 실제 owner·JobManager 위의 labelled 실행 대역. 성공, 오류/결과 없는 원 실패, 부분 실패, exact bytes, 편집/Undo/저장/재복사, field/proof/input/alias 변조, legacy proof 거절, 미구현 입력 읽기·평가 차단 |
| qt-01 |3| 현지 native runtime 부재의 새 실패2(실행 경계 대역), 실제 Windows Qt/HTTP와 기존 실제 온도장 읽기1 |
| save-failure-01 |2| saved pointer 발행 실패 시 이전 저장본·현재 미완성 입력·원 결과 불변 |
| retained-ui-03 |2| 보존 결과 없는 실패·취소 원 오류 표시와 live 원 job 조회0, 성공 후 읽기 오류의 이전 그래프·선택 초기화, 새 현지 pending의 status 조회 유지 |

`missing-proof-01`은 위 legacy2개에 cold boot 거절 assertion을 보강한 재확인으로 중복 합산하지 않는다. 결과 파일만 고친 뒤 새 hash로 몰래 재바인딩하지 않는다. 결과 없는 실패의 원 오류를 새 성공 응답으로 만들지 않는다. native runtime 부재2개는 기존 owner·명령·JobManager의 실제 실패 저장을 확인하되 실행 경계의 명시 대역이다. FEniCSx/Code_Aster/CalculiX/OpenCourant/MFront의 새 실제 계산 수용이 아니다.

초기 `contracts-01` 실패는 대역 fixture의 상위 results 폴더 생성 누락이었다. 이를 고쳤고 원 실패 로그도 보존했다. `retained-ui-01`은 현지 pending의 원 caption 동작을 RUNNING이라고 가정한 test assertion 실패다. 기존 상태 조회 유지만 검사하도록 바로잡았고 `retained-ui-02`는2pass였다. 마지막 clear 경로 보강 뒤 동일2개를 `retained-ui-03`에서 확인했으며 중복 합산하지 않는다. 이 두 Qt 반례의 실행/실패/취소와 손상은 명시 대역이다. 원 저장 실패 기록을 바꾼 검사가 아니다. 물리 허용치/결과/status를 고치지 않았다. source AST 검사는 기존 MoAI/ast-grep의 eval/exec/shell=True 두 규칙으로 시행했으며 동작/독립 검토를 대신하지 않는다.

## 실제 창과 소유 정리

Qt/HTTP 검사는 실제 계산한 사본의 별도 검사용 사본을 만들고 PDE/Simulation 창에서 원 온도장을 선택했다. 정상1280×850/좁은1020×720, 한글, field/node·K/m·이전 입력 표시, File copy의 취소/저장본 선택 때 미적용 `1e` 유지, 명시 저장 후 Undo/Redo/save와 helper 자식 창 정리를 확인했다. 새 계산0이다.

WIN-COMMAND에 따라 기존 File 메뉴의 동일 copy helper를 재사용하고 모델/결과 창을 중심에 유지했다. Qt01의 모델영역 제목에서 기존 matplotlib 한글 glyph 경고를 발견해 기존 configure_plot_fonts를 생성 전에 재사용했다. `render-02`는 같은 결과/시간/값을 다시 계산하지 않고 모델/결과 탭을 표시만 재저장했다. 정상/좁은 PNG를 직접 읽어 한글과 장·축·선택을 확인했고 glyph 경고가 없어졌다.

독립 검토에서 결과 없는 보존 실행이 live 원 job 조회로 떨어지는 경계를 발견했다. 보존 실패/취소 원 상태·오류를 표시하고, 보존 결과 손상은 reader 오류 그대로 보이며 기존 성공 그래프/선택을 지우도록 공통 최소 patch를 반영했다. 공통 copy 안내도 모델 입력에 맞게 ‘편집한 내용’으로 바꿨다. 해당2반례와 선택창 최종 표시는 추가 물리 계산 없이 확인했다.

root가 마지막 그래프의 내부 영어 설명을 ‘절점 값/요소 평균값’, 선택 절점의 좌표·값, ‘정상 상태 결과’로 정리했다. 원 time_origin은 tooltip에 보존하며 값·단위·표본/보간 동작은 바꾸지 않았다. 기존 `test_research_pde_ui.py::test_exact_field_components_nodes_time_and_post_study` 한 개를 `field-labels-01`에서 추가 확인했다(전용21개와 별도인 기존 UI 대역 검사1개). `render-03`의 PDE1280×850/Simulation1020×720 두 PNG가 최종 결과 화면이며 두 장을 직접 읽었다. 원 결과만 다시 읽었고 추가 계산0, glyph 경고0, 두 실행 모두 exit0/`job_empty`다. `render-02`의 모델영역/기타 크기 이미지는 같은 원 결과의 이전 표시 근거로 보존한다.

모든 확인은 절대 Python과 `scripts/native_check.py`의 private Windows Job으로 실행했다. 완료·실패 모두 자기 server/window/worker를 finally 정리하고 `job_empty`를 확인했다. 사용자 기존 창·프로세스를 종료하지 않았다. OS 마우스/포커스, 별도 GUI launcher의 두 프로세스 왕복, 실제 Post/PVSM/프린터 및 공학 승인은 미확인이다.

## 남은 범위

CB04/05 이동 owner/입력/보존 결과/명시 새 평가 경로를 구현하고 위 두 Windows 평가기로 실제 확인했다. 다른 adapter의 기존 native 설치·권한·입력 지원 관문은 유지되며 본 확인으로 승격하지 않는다. `.caepre` native Analysis와 live registrar가 필요한 경로는 CB07의 정확한 원 dependency 이동이 선행된다. 기존 inline deck/mesh/source/field 원문 보존과 원 결과 읽기는 그 이유로 막지 않는다. CB06 단계/transfer/reuse, CB07 native host, CB08 Post project/reader 이동은 다음 별도 인도다.
