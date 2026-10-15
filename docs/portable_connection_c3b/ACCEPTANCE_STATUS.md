# C3B-R1 인도 상태와 실제 실행 근거

아래는 원 Pro 인도 시점의 기록이다. 이후 Windows의 실제 편집·저장·재복사·재열기와
Qt 메뉴·선택 확인 및 국소 탐색 교정은 [Windows 확인](WINDOWS_VERIFICATION_KO.md)에
연결한다. 다른 문서 종류·문헌 연결 등 미구현 잔여는 유지한다.

## 범위 판정

REQUEST/API_MAP/ACCEPTANCE/OWNERSHIP 전체와 실제 baseline 접점을 먼저 검토했다. 정상 C3A+C1+Data C2를 유지하면서 가장 앞의 독립된 실패는 Report A JSON의 frozen reference와 새 typed source reference가 같지 않아 발생했다. 단순 SUPPORTED/prefix/asset 허용 확장으로 content 읽기를 끝낼 수 없었다.

따라서 첫 인도는 **Report 자체 + 기존 지원 공학 source + frozen 이미지**의 읽기→현재 편집/Undo/Redo→저장→cold→재복사다. 이는 호출 이름/전송 영수증만 있는 결과가 아니라 실제 기존 owner와 파일을 사용한 구현이다. 전체 C3B 또는 범용 CB01 완료로 세지 않는다.

| 수용 항목 | 이번 상태 | 정확한 잔여 |
|---|---|---|
| CB01 Report | 공학 문서/결과 source, frozen PNG, saved/ack/history 및 빈 Report의 원 owner bytes 보존과 current edit/save/cold/recopy 구현·Linux 확인 | knowledge 현지 scope, 비교/candidate current navigation, 손상 portable-project의 부분 cold open, 실제 Windows Qt 수용 |
| CB02 Study | NOT_IMPLEMENTED | exact knowledge revision/locator/raw source, collection/access/revoked 원 기록과 현재 local scope의 분리, 실제 Study 편집 왕복 |
| CB03 Expert | NOT_IMPLEMENTED | 원 turns/rounds/실패/Co-STORM 보존과 현재 dispatch 분리, provider 없는 cold 및 새 Ask 권한/전송 확인. CB02 문헌 계약을 재사용해야 함 |
| CB04 PDE | NOT_IMPLEMENTED | 원 실행 read facet, 기존 pde.evaluate 현재 실행/저장 왕복 |
| CB05 Simulation | NOT_IMPLEMENTED | native input/field snapshot 원 bytes와 현재 실행 설정의 분리, 기존 simulation.evaluate 왕복 |
| CB06 Evaluation | NOT_IMPLEMENTED | stage_inputs/attempt/transfer/reuse prefix의 immutable 검증과 현재 evaluation.run 연결. CB04/05 source adapter 선행 |
| CB07 managed Pre | NOT_IMPLEMENTED | 실제 native_design selection, FCStd/caepre raw archive, XLink derived relocation 및 현재 opener |
| CB08 managed Post | NOT_IMPLEMENTED | project/PVSM/reader pins/history dependency와 verified repair/current opener. Report frozen 그림 복사는 이 항목의 대체가 아님 |
| CB09 실패/재확인 | Report 경로의 stale/원 참조 변조/history 누락/그림 손상/발행 실패/동일 command 재확인/용량 검사 확인 | 다른 미구현 owner/native의 수용, Windows 파일시스템 수용 |
| CB10 동등 사용 | 실제 Python/Client/CLI Report 선택·원값/current navigation 일치. Qt GUI 접점 코드+controlled Python 계약 검사 | 실제 Qt 목록/메뉴/키보드/초점/닫기 수용, optional MCP의 Report 경로 실제 호출 |

다음 의존 순서는 CB02 knowledge/Study → CB03 Expert, 그리고 기존 execution read 패턴의 CB04/05 → CB06, 마지막으로 등록된 native target 및 CB07/08 verified relocation이다. Report를 이들 owner와 함께 선택하는 일반 연결은 해당 group이 구현되기 전 허용 목록만 열어 통과시키지 않는다. FN05 exact historical owner/두 submitted hash/inputs hash/Data assessment 검증은 변경하지 않았다.

## 실제 검사

`logs/01_baseline_red.log`: 원본 실제 Report owner는 OWNER_NOT_SUPPORTED. 검사 전용으로 허용 관문만 연 반례는 READY copy 후 content가 SNAPSHOT_UNAVAILABLE, 원 A 참조 검증 오류. 실제 RED이며 문서 추측이 아니다.

`logs/04_report_tests_first.log`: 첫 신규 검사 2 FAILED, 21 PASSED. 하나는 acknowledged 원 saved-base Report 문서 bytes가 재복사 때 빠지는 실제 결함이었다. raw saved-base archive를 명시 보존하여 고쳤다. 다른 하나는 test fixture가 result reference에 필수 kind='result'를 넣지 않아 기존 validator에 거절된 오류였다. fixture를 수정했으며 validator를 완화하지 않았다. 이 실패 로그는 삭제하거나 성공으로 바꾸지 않았다.

`logs/05_report_targeted_correction.log`: 해당 실제 왕복/결과 3 PASS. `06`은 당시 새 검사+기존 영향 29 PASS. `08`은 실제 HTTP/Client/CLI 1 + controlled GUI Python 경계 10, 총 11 PASS. `09`는 빈 Report의 원 owner archive까지 보강한 35 PASS. 앞선 smoke/예제 기록도 원 로그 그대로 포함한다.

**최종 코드 국소 검사: `logs/10_final_focused_suite.log`, 44 PASS, 12.98초.**

- 신규 Report core 27: saved_only/ack, 원 A raw bytes/PNG/원 Report 문서, Data 실제 성공·실패 import와 행/성분/단위, standalone source 미선택, 현재 새 capture, 잘못된 binding/current buffer, history-only A, 원 archive 변조, response-loss 재확인/current edits, stale review, 발행 실패, invalid authored 문자열, 미저장 Report, knowledge 발행 차단, owner별 asset whitelist, 빈 Report, copied image 손상 및 전체 크기 관문.
- 신규 실제 HTTP/Client/CLI 1: exact selection/inspection equality, create/같은 command 재확인, 원 store 제거 뒤 Client/current navigation/content/verify.
- 신규 controlled GUI Python 경계 10: busy/pending, 미적용 설명/명시 Save/Cancel, 응답 전/실패 미리보기의 native origin 열기 방지, late save reply. 실제 Qt 수용 아님.
- 기존 영향 회귀 6: Report image retention/degraded publish 4, C1 Q-only saved source 1, Data C2 acknowledged calibration retention 1. 광역 legacy 또는 solver suite를 반복하지 않았다.

`logs/11_final_separate_process_example.log`: 최종 코드의 실제 공개 예제. parent PID 1772, cold PID 1787/1797은 서로 다르다. 원 store 및 외부 source를 삭제하고 첫 cold에서 current owner edit/Undo/Redo/save/recopy; 첫 사본을 삭제한 다음 두 번째 cold에서 재열기/저장. 원 saved Report document와 A/PNG raw bytes, 원 성공·실패 import 및 source/current navigation을 대조했다. cold에서 실행/원 native 접근 호출 0, 새 JobManager 작업 0. 최종 사본 verify READY. 공학적 자격 NOT_RELEASED.

로그 시간은 이 Linux 실행의 관측값일 뿐 Windows 소요시간이나 미래 예측이 아니다. 이 인도의 원본/최종 파일 SHA와 patch 적용 검증은 SOURCE_MANIFEST.json 및 PATCH_APPLICATION_CHECK.json으로 별도 기록한다.

## NOT_RUN / 미구현을 혼동하지 않음

실제 Windows·Qt, FreeCAD/ParaView native capture/open/edit/save, PDE/FE solver, AI provider, optional MCP는 NOT_RUN이다. PySide6/native runtime을 설치하지 않았고 추가 유료 호출/구독/크레딧도 0이다. 이미지 fixture는 SCRIPTED_NOT_NATIVE다. CB02–08 core를 작성하지 않은 것은 runtime NOT_RUN 때문이 아니라 **이 중간 인도의 남은 구현 범위**다.

공유 GUI 코드와 최소 root patch는 인도했다. root/Sol의 Windows 수용에서는 실제 메뉴/초점/미적용 내용/응답유실/다른 창 입력/종료를 확인해야 한다. 자신의 서버/창/child만 finally 정리하며 사용자의 기존 작업 창은 종료하지 않는다. 새 전체 solver 캠페인을 선행조건으로 추가하지 않는다.
