# C3A Windows 통합 확인

확인일: 2026-10-15. 기준은 main `4e2cf2c`에 실제 Pro C3A 전용20개와 root 공통7개 hunk를 이식한 작업 소스다. 동시 Post/재료 법칙 WIP는 보존했고 이 검사의 지원 조합으로 확대하지 않았다. 전용 기존3개는 전달 manifest의 before SHA와, 전달20개는 after SHA와 일치한 뒤 이식했다. Pro의 핵심 구현과 Sol의 GUI/CLI 국소 교정을 구별한다.

기존 Windows runtime Python3.12/PySide6.9.1과 Qt `windows` 플랫폼을 사용했다. 새 설치·solver·provider 호출은 없다. 각 확인은 `scripts/native_check.py`의 새 Windows Job에서 실행했고 종료 영수증의 `cleanup=job_empty`를 확인했다. FreeCAD/ParaView는 실행하지 않았다.

## 실제 Qt 동작

기존 Data/Material 파일 메뉴의 「이동 사본의 원 편집 자료…」에서 공개 사본의 원문을 읽고 「현재 편집기로 이어가기…」를 명시 선택했다. 실제 loopback Client/현재 owner UPDATE를 사용했으며 승인 질문은 검사 코드가 Yes를 선택했다. `1e`는 숫자로 적용되지 않은 delegate로 복원되고 cursor=2와 실제 편집 포커스가 돌아왔다. owner draft는 원래 acknowledged 값 그대로이고 새 계산/자동 저장은 없었다.

Material에 이미 미완성 `1e`가 있을 때도 원문은 읽을 수 있다. 이어가기는 현재 원문 보관 안내와 함께 거절하며 원문·역방향 선택(cursor=1, 선택 `e`)·전체 owner 문서가 유지됐다. 서로 다른 두 Plan 위젯에는 빈칸과 `invalid`가 각각 복원됐다. Plan 위젯 검사는 기존 restore API 소비이며 두 Plan의 메뉴 선택 흐름 전체를 검사한 것은 아니다.

QScreen의 실제 창 pixels를 보통 크기(960×680)와 좁은 크기(740×540)에서 읽어 한글·focus/selection·부분 저장 결과를 검토했다. 초기 선택창의 시각/상태 잘림은 내용 너비를 확보하여 교정했다. 원문 위치는 `mapping` 행/열 대신 응력/배율 등 실제 항목으로 표시하고, primary 이어가기/복사 검토를 기존 appearance로 강조했다. 복사 보관본은 기본 해제이고 Space 키로 명시 선택된다.

원 Q의 declared asset 검증이 실패한 catalog 행에는 `source`가 없을 수 있었다. 이 행의 선택창 KeyError를 없애고 비선택 상태와 구체 원인을 표시했다. 정상 행의 선택은 유지한다. 원문 reader의 거절 원인도 tooltip에만 두지 않고 본문에 표시한다.

## 실행 근거와 한계

실행 로그·영수증·창 캡처는 `runs/product-development/20261015/portable-c3a-windows/`에 있다.

| 범위 | 결과와 원 기록 |
|---|---|
| 실제 Data/Material 메뉴·읽기·이어가기·focus·Space 선택 | `actual-qt-after-process`: PASS. 같은 자료의 before는 `actual-qt`, after 캡처는 `actual-qt-after` |
| 실제 dirty target 메뉴·역방향 선택 보존 | `qt-dirty-process`: 1 PASS |
| 서로 다른 두 Plan의 빈칸/invalid와 broken catalog 선택창 | `qt-plans-process`: 2 PASS |
| 원문/closure/권한/CAS/변조/실패 전용 core26개 | `core-process`에21개, `core-tail-process`에나머지5개 완료 출력. 두 묶음은 각각180/150초 제한에 도달했으므로 명령 전체 PASS로 표시하지 않음 |
| 원 store 없는 공개4owner 읽기→현재 acknowledged 저장/새 Keep→8archive 재복사 | `cold-recopy-process`: PASS. `1e`/빈칸/invalid와 부분 저장 receipt 유지, 새 Job/provider0 |
| 첫 사본의 새 current Keep를 다른 process에서 명시 session-change 복구 | `current-keep-cold-process`: 4owner PASS |
| 재복사8archive의 원문 읽기·현재 저장/새 Keep | `recopy-cold-process`: PASS. 첫 사본의 원경로는 test-owned sibling으로 이동하여 보존 |
| 첫 사본 원경로가 없는 상태에서 재복사의 current Keep 새 process 복구 | `recopy-current-keep-cold-process`: 4owner PASS |
| 실제 HTTP/Client strict fields·동일 command 재시도·본문 한도·CLI 한글 JSON | `http-utf8-process`: 1 PASS |

CLI는 Windows CP949 stdout 때문에 UTF-8 호출자가 한글 JSON을 읽지 못하는 실제 실패가 있었다(`http-process`). 명시 UTF-8 출력으로 국소 교정한 뒤 같은 검사가 PASS했다(`http-utf8-process`). 파일 출력은 기존 UTF-8·배타 생성 그대로다.

이 첫 확인 때 Astra가 지적한 Q에만 남은 acknowledged 참조의 closure 누락과 응답 유실 뒤 별도 run이 추가된 경우의 오래된 전체문서 응답은 실제 Pro 핵심 교정 대상으로 남겼다. 이후 C1 교정과 해당 Windows 확인은 아래에 구별한다. C3B의 다른 owner/native 이동 요구는 그대로 남는다.

## C1 두 경계의 Windows 후속 확인

실제 Pro C1 전용10개 delta를 기존 C3A 통합 위에 적용했다. 기존4개의 raw SHA는 C1 before와 일치했고 새6개는 없었다. hunk 적용 후 Git의 CRLF 변환만 원문 LF로 되돌려 전용10개 전체 raw SHA가 C1 after와 일치함을 확인했다. 공통 `MaterialDocuments`/`related_save_edits` 두 hunk는 root가 통합했다. Sol의 손상 보관본·원문 위치·포커스 GUI와 UTF-8 CLI, UI 회귀 다섯 파일은 이전 확인 때의 SHA와 정확히 같다. C1의 핵심 코드·테스트·계약은 실제 Pro 원문이며 별도 대체 구현은 없다.

기존 Windows Python3.12 runtime에서 새 `tests/test_portable_recovery_c3a_c1.py`만 한 번 실행해 **25 passed in 89.75s**를 확인했다. `scripts/native_check.py --timeout 150`의 영수증은 timeout=false, exit_code=0, cleanup=job_empty다. 원26개 검사와 큰 cold/GUI/native 시나리오는 반복하지 않았다.

이 새 검사는 다음 경계에 한정된다.

- 원 store를 제거한 saved_only/acknowledged 사본에서, 실제 Material R2가 live 또는 Q.assets에만 남아도 두 Plan의 정확한 과거 참조를 읽고 이어간다. 같은 입력의 다른 saved revision으로 대신하지 않는다.
- 미선택 peer·중복 Q·누락/변조 자료를 거절하고, raw의 임의 ID/path를 의존이나 새 권한으로 수집하지 않는다. 구 사본의 불완전 map은 READY/BUFFER_READY로 승인하지 않으며 정상 원 Q 읽기는 남긴다.
- 진짜 같은 요청의 응답 유실과 durable write 이후 메모리/receipt 유실은 기존 owner의 정확한 증명으로 재시도한다. 그 뒤 run·비교·제목·숨은 이력·알 수 없는 필드·다른 mutation이 생기면 오래된 전체문서를 반환하지 않는다. evaluate 반례는 실제 owner의 run 추가와 bounded failed submission 대역이며 solver/evaluator 실행이 아니다.

로그와 정확한 소스 SHA·보존된 Sol 파일 SHA는 `runs/product-development/20261015/portable-c3a-c1-windows/`의 `new25-process/`와 `integration-receipt.json`에 있다. 새 solver/provider 호출은0이다. 이전 두 timeout과 CLI CP949 실패는 원 기록 그대로 남는다.

Astra는 별도로 Data Q에만 남은 calibration 입력이 saved_only 사본의 현재 retained_inputs에 합류하는지 추가 소스 검토 항목을 제기했다. 이25개를 그 Data 경계의 실행 증명으로 확대하지 않는다. 해당 핵심 후속과 C3B가 남아 있으므로 전체 C3A/C3 완료를 주장하지 않는다.

## Data C2의 Windows 후속 확인

이후 실제 Pro Data C2 전용7개 증분과 root의 공통2개 hunk를 통합했다. 핵심 코드·예제·계약6개는 Pro after raw SHA와 일치한다. Sol은 기존 왕복 테스트에 재개 전 source-preview 확인5줄만 보강했다. GUI·UTF-8 CLI·C1 전체 문서 재시도 보호와 Data 단일 닫기 동작은 유지했다.

기존 Windows runtime에서 새 C2 국소15개가 **109.51초에 PASS**했고, 미등록 invalid Data 초안 저장과 C1 동일 요청의 전체 문서 재시도 경계 두 case가 **4.17초에 PASS**했다. 보강한 왕복1개만 **34.26초에 다시 PASS**했으며 별도 새 case로 합산하지 않는다. 원25/26/59개 전체는 반복하지 않았다.

같은 공개 사본에서 원 보정 CSV source-preview→현재 owner의 명시 재개→현재 CSV·보정 자료 읽기→명시 편집·저장→새 current Keep/close gate→별도 프로세스의 새 Keep 복구·재복사→첫 사본 경로를 끊은 다른 cold 읽기를 확인했다. 원 Q·raw·receipt·input.json/CSV와 원 성공/FAILED 실행은 보존했고, 원 Q 권한은 NOT_GRANTED다. 공개 출발 사본60파일도 byte-identical이다. 출발 자료를 재사용하여 새 CSV import는0이며, metadata case의 새 CSV upload는 자료 등록 검사다.

로그·정확한 source SHA·세 cold process 결과와 정리 영수증은 `runs/product-development/20261015/portable-data-c2-windows/integration-receipt.json` 및 같은 폴더의 실행 기록에 있다. 세 Windows Job 모두 timeout 없이 exit0·job_empty로 끝났다. 새 solver/provider 호출은0이고 이번에는 Qt/native 창을 다시 실행하지 않았다. 앞선 실패·두 timeout은 원 기록 그대로 남으며, 다른 owner/managed native 이동의 C3B와 전체 C3 완료를 뜻하지 않는다.
