# 실제 검증과 미실행 구분

Linux 수치는 회수한 Pro 원기록이다. 현재 Windows 통합·수정·실행은 아래 별도 절에 기록한다. 서로 합산하지 않는다.

## Pro 인도 원기록 (Linux)

Linux Python 3.13.5, pytest 9.0.2. 기존 설치만 사용했다. 최종 전용 suite는 `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1`, `PYTHONPATH=.:tests`로 **66 passed / exit 0 / 33.16 s**였다. `final-all-new-isolated.log/xml`이 원기록이다. 전용 45개 owner/권한·11개 headless GUI contract·2개 실제 vendored Co-STORM runner 경계·8개 Report 읽기/출력 권한 게이트를 합한 수다. headless 계약 검사는 실제 Qt 렌더링이 아니다.

변경 접점의 기존 좁은 회귀는 **24 passed, 3 skipped / exit 0 / 4.32 s**였다. Study/Discussion 13개, 기존 Co-STORM 읽기 4개, R1 Report 선택 7개다. 기존 Qt 3개 모듈은 PySide6 부재로 skip이며 실제 Windows 통과가 아니다. `final-existing-isolated.log/xml`을 참조한다. 따라서 중복 없는 확인 사례는 전용 66 + 기존 24 = **90개**다. 개발 중 같은 사례를 반복 실행한 수를 더하지 않는다.

최종 공개 runnable은 parent PID 3788, cold1 PID 3799, cold2 PID 3810으로 각각 분리되어 exit 0이었다. 원 store를 삭제한 뒤 첫 cold를 열고, 첫 사본을 삭제한 뒤 두 번째 cold를 열었다. 결과는 `public-proof/result.json`, 두 process log·cold JSON·원문 evidence와 controlled-current 기록에 있다. paid_provider_calls=0, actual_ai_answer=false, windows_qt=NOT_RUN이다. process는 runnable이 만든 범위에서만 소유하며 삭제 전 controller shutdown/join을 검사했다.

## 실제 수용 사례

SE01: 같은 제목의 Markdown 1/2개정에서 원 1개정·정확한 구간·raw/source SHA/selected content SHA·metadata를 보존한다. raw/segments/descriptor/locator/hash 누락·변조와 모호한 revision/latest를 거부한다. 원 turn/실행/Undo 및 현재 본문에서 제거되어 원 Report archive에만 남은 pin도 재복사한다.

SE02: 공개 및 원 local 허용 경로의 source-free 읽기가 실제 성공했다. 원/현지 local 문자열 일치, 타 workspace/private·role collection, revoke, review 이후 및 stage 작성 중 revoke, ID 충돌을 검사했다. frozen/원문/Expert 결과·영수증/새 context 및 Report 캐시·출력 거부를 구분한다. native 파일시스템 관리자에 대한 새 암호화/ACL 검사는 아니다.

SE03/04: 실제 S/B owner의 질문·판단·UNKNOWN·현재 본문 편집/Undo/Redo/save/cold/recopy와 원 A raw/참조/선택 text를 비교한다. 허용된 frozen 원문과 현재 탐색 실패를 분리한다. Report current resolver 실패 시 SOURCE_UNAVAILABLE/navigation_reference=None을 유지한다. 권한 거부 후 기존 preview/출력 재사용을 막고 기존 이미지 손상 preview 정책은 보존한다.

SE05/06: 원 성공/실패/READY/RUNNING/dispatch_pending/부분 기록은 immutable provenance로 보존하며 cold/read/Undo/save에서 원 job/status/receipt 조회·harvest/retry/dispatch를 금지한다. 새 현지 명시 Ask는 기존 owner/JobManager/Runtime source·role·transmission·session·budget 검사를 통과하여 controlled 응답을 수집·저장한다. 현지 유실응답·같은 command, 미설정/전송불허/철회/취소·늦은 질문 변경을 검사한다. 원 private history/세션은 새 context에 섞이지 않는다.

Co-STORM은 기존 vendored runner의 지도/보고서/중단 journal을 실제 생성 경계 double로 만들고 보존/원 retry 차단/새 local 실패 시 이전 report 보존/새 protocol index와 원 turn의 분리를 검사했다. LM 출력·검색은 scripted boundary이며 실제 AI 답변·실제 Haystack ranking 통과로 해석하면 안 된다.

SE07/08: stale generation, 저장 pointer 실패, 기존 destination, 발행 실패, 같은 command 응답유실, 늦은 reply/내보내기 중 편집 및 권한 변경을 검사한다. 원 자료·현재 buffer·기존 출력은 보존한다. 실제 두 별도 process chain은 공개 runnable 원기록으로 별도 증명한다.

## 실패·시간초과 기록

개발 단계의 실패 로그는 삭제하지 않았다. 초기 기존 baseline은 Study/Expert OWNER_NOT_SUPPORTED, 문헌 Report REPORT_KNOWLEDGE_SCOPE_REQUIRED였다. 초기 새 tests의 잘못된 호출/상태 필드/cleanup/참조 조립을 교정한 기록도 그대로 보존한다.

외부 pytest plugin 자동 로딩이 켜진 묶음 실행에는 실행 도구 timeout이 있었다. `final-focused.log`(120초), `final-all-new.log`(75초), `diagnostic-no-capture.log`(90초)의 실행은 정상 종료를 확인하지 못했으므로 PASS run으로 계산하지 않는다. 마지막 진단 로그는 개별 66 사례의 PASSED까지 보이지만 pytest session 종료 코드는 없다. 정확한 지연 원인은 확정하지 않았다. 외부 plugin 자동 로딩을 끈 최종 원 suite 66개와 기존 회귀 24개는 각각 종료 코드 0을 확인했다. assertion, source/permission gate, owner/dispatcher/runner를 생략하는 옵션은 사용하지 않았다.

## Pro 원기록의 미실행 경계

실제 Windows, PySide6/Qt 화면·focus/selection/Cancel/좁은 창·native 창 lifecycle·PDF/print rendering은 NOT_RUN이다. Codex/Sol의 기존 절대 Python·native_check output/Job·150초 이하 timeout·자기 process/window finally cleanup 절차로 후속 확인한다. 실제 provider/inference/search index/Haystack ranking, 기존 실제 provider가 설정된 Windows 새 Ask는 NOT_RUN이며 유료 호출/설치 0이다. 모든 숫자/답변은 공개 합성 자료 또는 명시 controlled script다.

Astra 독립 검토·원격 main 게시·사용자 PC 통합은 수행하지 않았다. 이 패치는 이번 CB02/CB03/문헌 Report의 적용 가능한 source와 연결이며 전체 C3B 또는 제품 전체 수용을 선언하지 않는다. CB04–08, Report candidate/current 비교 탐색·부분 opener·managed native와 다른 팀의 잔여는 그대로다.


## Windows 현재 통합 확인 — 2026-10-16

Pro 기준 eaa33cf 작성물의 신규12파일/기존19hunk를 root와 나누어 현재 main에 통합했다. Sol은 전용24경로, root는 공통7경로와 기존 Literature.read callback 연결을 담당했다. 이후 D 공개 문헌 검색/권한/중단 재사용 구현은 유지했다. source와 실제 실행 경로/hash는 로컬 `_workspace/delivery-portable-study-expert/FINAL_MANIFEST.json`에 고정한다. 새 모델 설계나 독립 전문 팀을 구현한 것으로 해석하지 않는다.

Windows Python3.12.14/PySide6 6.9.1, 기존 전용 runtime을 사용했다. 모든 묶음은 scripts/native_check.py, 절대 Python, 개별 제한시간과 private Windows Job finally 정리를 사용했으며 아래 완결 실행은 exit0/job_empty다. 검사수는 서로 겹치지 않는 **75개**다.

| 확인 | 원기록 폴더 | 사례수 | 의미 |
|---|---|---:|---|
| 원문 개정/범위·변조·현지 권한 | core-first-01 |16| 원문/선택/권한 불일치 차단 |
| 원 이력 무실행·새 Ask/허용 경계 | core-middle-01 |13| copied READY/RUNNING/dispatch_pending 무실행, 현지 질문·권한·늦은 편집 유지 |
| 현재 영수증/원·현지 참조/재복사 | core-tail-01 |16| stale/save 실패, revoke, raw archive closure와 현지 command 재읽기 |
| 실제 작은 CSV 결과 S/X/B 복사 | selected-result-01 |1| CSV import만 실제 실행, stress 값/MPa/선택/frozen A bytes 및 두 번째 사본 일치. solver0 |
| 기존 실제 vendored Co-STORM 경계 | costorm-local-01 |2| LM/검색은 labelled double, 원 지도/보고서/중단 journal 보존 |
| 공개 문헌 완료/부분 operation closure | public-02 |3| 실제 runner, 모델·Crossref transport 대역. 정확 archive2개/DOI/읽은 범위/부분 성공 read/recopy/cold 및 변조 거절 |
| Report 출력·메뉴 headless 계약 | report-contract-01 |19| Report8+기존 helper11, 실제 PDF/프린터 검사는 아님 |
| Qt 복사 선택 | qt-choice-01 |3| QTest로 저장/저장본만/취소, 미적용 문자열·선택·독립창 유지 |
| Ask 전 공개 문헌 첨부 | public-composer-01 |1| composer/Undo/작성 발언의 exact 인용 복사·cold·recopy, 모델/dispatch0 |
| 실제 Qt/HTTP 앱 | qt-http-03 |1| shown Study/Expert/Report·연결창, 원 이력 무호출, 미적용 section 유지, recopy inspection READY |

독립 process 공개 runnable은 `public-process-01/flow/result.json`: parent51016 → cold1 32608 → cold2 6708, 52초/exit0/job_empty. 생성한 원 store와 첫 사본은 삭제하지 않고 `.preserved` 이름으로 옮겨 원 경로 없이 재개했다. 각 새 소유자는 편집/Undo/Redo/저장하고, cold1의 명시 새 Ask는 현재 역할·원문·전송 검사를 거쳐 **CONTROLLED RUNTIME TEST RECORD 1회**만 기록했다. copied grant로 거절된 시도와 NOT_CONFIGURED도 보존했다. actual_ai_answer=false, paid_provider_calls=0. 실제 OAuth 모델을 새로 호출하지 않았다.

실제 Windows Qt는 1200×800/900×700 창을 열어 QTest 입력과 QWidget.grab 이미지를 확인했다. `qt-http-03/images/`의 expert/study/report normal/narrow, `final-render-01/`의 local/public review normal880×600/narrow720×500가 최종 화면이다. 복사 목록은 선택 문헌을 위에 보이며 raw 파일명은 한국어 자료종류로 표시하고 원 경로는 tooltip에 보존한다. WIN-COMMAND에 따라 기존 파일 메뉴와 짧은 저장/취소 동선을 유지했다. OS 키보드/포커스, 별도 GUI process launcher 왕복, 실제 PDF/인쇄·FreeCAD/ParaView·공학 승인은 이 검사에 포함하지 않는다.

## Windows 교정과 보존한 실패

초기 core-01은29개 점 표시 뒤180초 timeout이며 완결 PASS가 아니다. 이를 16/13/16의 좁은 그룹으로 나누어 각각 종료를 확인했다. public-01은 같은 DOI의 서로 다른 보관 파일을1개로 가정한 검사 오류였으며 원 자료를 바꾸지 않고 다수 exact archive를 보존하도록 assertion을 교정했다. qt-http-01은 검사에서 소유자를 두 번 생성한 controller lock 오류이며 제품 오류로 분류하지 않는다.

qt-http-02의 창 검사는 통과했지만 이미지에서 recopy 포함 검토가 BLOCKED인 것을 확인했다. 과거 저장 Report가 현재 owner와 같은 A를 사용하면서 다른 navigation proof를 보유하는 경우, 문헌 closure 수집이 현 owner 파일을 읽던 결함이었다. 해당 snapshot의 정확 revision 폴더와 기존 verify를 사용하도록 고쳤다. 원 proof/hash/bytes를 재작성하거나 검증을 약화하지 않았다. qt-http-03에 READY assertion을 추가하여 교정을 확인했다. 이전 PNG/로그도 보존했다. final-render-01은 이 교정 뒤 목록 표시만 재확인했으며 추가 계산/모델/검색0이다. Matplotlib tight-layout 경고1건은 원 페이지 렌더 후 resize 때 남았고, 실제 페이지/한글/표를 직접 확인했다.

이 검사는 기존 로그인 경로가 설정되었을 때 새 Ask가 사용하는 계약을 controlled 경계로 확인한 것이다. 실제 로그인/응답 수용, 분야별 독립 state/model/전문코퍼스 구축과 원 CB04–08·타 팀 잔여를 완료로 주장하지 않는다.


독립 검토에서 Ask 전 `composer.evidence`와 작성 발언에 붙인 정확한 public paper 인용이 문서 owner 참조로 오인되던 누락을 교정했다. 선언된 draft/Undo/turn 경로에서만 exact archive를 수집하고 paper_id/locator는 문서 ID로 바꾸지 않는다. `_Fork` 및 기존 `TypedProjection`의 참조 투영이 원 인용을 보존하며 나머지 owner/result 관문은 그대로다. public-composer-01의1개 새 반례에서 실제 owner의 `expert.intervene`는 작성 발언만 남겼고 Ask/Job0인 채 원store 이동 후 Undo/Redo/save/recopy/cold가 통과했다(6.4초, exit0/job_empty).

public-cold-guard-01은 이미 포함한 public report 사례의 constructor guard만 실제 `literature.fetch_url`에 맞춰 재확인한 실행이다. 초기에 테스트가 없는 `_fetch` 속성을 patch했으나 기존 생성자는 local 파일 읽기만 했고 생성후 fetch/submit 거부는 유효했다. 새guard 실행은 exit0/job_empty이며 같은 사례를 검사수에 중복 합산하지 않는다. 제품 동작이나 외부 권한을 바꾼 교정이 아니다.
