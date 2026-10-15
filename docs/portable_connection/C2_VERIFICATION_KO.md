# C2 실제 검사 기록과 미실행

## 기준과 원 RED 보존

요청 ZIP 전체의 SOURCE_MANIFEST 2579개 항목을 SHA256으로 대조했다. 패킷 기준은 **86bc7db1cbe61060e7db98795a87c9f9aa37fc34 + C1 전용28**이며, 원 Windows 세 반례의 실행 기준은 **2fea93f838c4f0193e0101895077dd99f5cd9a8c**다. 원 C1·원 Windows 소스/데이터/결과/owned-job receipt를 수정하지 않는다.

원 Windows 기록은 Python3.13에서 세 예상 결함을 재현한 exit0이고 Qt/provider/물리 solver 호출0이다. `job_empty`는 그 원 검사의 cleanup 결과이며 제품 이동 수용 성공이 아니다. 신규 Linux 결과에 원 Windows PASS를 더하지 않는다.

Linux에서도 수정 전 exact C1을 사용해 missing pending evidence, frozen-arguments hash mismatch, completed-attempt source mismatch의 세 RED를 동일하게 재현했다. 수정 후에는 첨부된 실제 Windows 생성 원 store의 복사본에서 새 사본을 만들고, source 경로를 rename으로 없앤 별도 프로세스에서 세 경우를 검사했다. 원 packet 파일은 byte 불변이다. Windows가 만든 LF/CRLF 포함 pending evidence 파일은 현재 owner 명시 저장 뒤에도 raw SHA가 같다.

## 최종 범위

인도 `verification/`의 final log/XML/실제 process receipt가 수치의 근거다. 정확한 패킷 source에 product.patch와 combined integration.patch를 다시 적용한 별도 소스에서 실행한다. 아래 그룹은 서로 중복되지 않는다.

| 그룹 | 결과 | 검사 범위 |
|---|---:|---|
| portable-c2 | 37 passed | 새 file/proof/receipt/consumer/HTTP/CLI 검사34 + 정확 supplied Windows original3 |
| c1-regression | 95 passed, 2 skipped | C1 portable/typed relation/Esc-command/배치/초안·Undo·large local input/body caps; Qt 두 모듈 미설치 skip |
| numerical-regression | 81 passed | 실제 기존 Numerical detail/C1/C2/evidence 소비자 회귀 |
| common-regression | 25 passed, 1 skipped | 기존 native-command/input 경계, 선택 MCP 미설치 skip |
| 합계 | **238 passed / 3 skipped** | 제품 전체 또는 Windows 전체가 아닌 이 명시 범위 |

Qt skip은 실제 QWidget/QTest를 돌렸다는 뜻이 아니다. 중복 ZIP member 거절 fixture는 Python zipfile의 duplicate-name 경고를 발생시킬 수 있다. 경고 원문은 보존한다.

## 수용 검사

원 저장 snapshot / acknowledged draft / generation / Undo / MPa·s·UNKNOWN / raw Data와 성공·실패 결과가 유지된다. 원 pending evidence 파일·binding·완료/미완료 CAPTURE 이력·publication witness를 수집하고 원줄기와 모순이면 목적지 발행 전에 거절한다. pending 사본의 원 command는 실행 권한이 아니며, 새 current session/generation의 명시 저장/CAPTURE만 허용된다.

원 C2 `selection`, `failed_capture`, `complete`, 공개 `DetailHost`와 실제 Workbench/Data/Material/Report owner를 사용한다. 새 bound 예제에는 실제 서로 다른 Data 관측 두 개와 fit/holdout 역할을 명시한다. fixture 생성에만 대수 evaluator를 사용하고, cold에서는 owner/controller 생성 전부터 기존 Numerical tripwire로 Workbench dispatch·JobManager submit·Numerical evaluator·Evaluation DAG 경계를 차단한다.

cold 명시 save → 완료 attempt 상세 읽기 → 증거 resolve → 두 후보 비교 → 실제 Report capture/update/save → Material 명시 채택 → owner edit/Undo/save를 실행한다. 다른 프로세스에서 그 보고서/보존증거/채택 ref를 다시 읽고, 재복사에서도 원 snapshot identity와 current navigation ref, graph의 typed reference를 확인한다. 새로운 job 수와 evaluator/DAG/dispatch 호출은 0이다.

원 Data-bound successful candidate의 상세가 미보존인 경우는 **그대로 미보존**이다. success capture와 그것을 failure로 포장한 capture 모두 거절됨을 확인한다. 원 fit 메타데이터 보고는 가능하고, 실제 FAILED 후보의 실패 진단은 따로 보존·보고한다. 실패 증거의 adoption은 거절한다. 재계산하여 없던 상세를 만들어 통과시키지 않는다.

공개 ZIP은 검사용 사본과 분리해 생성하고, 그 ZIP을 다시 압축 해제한 폴더에서 별도 cold/second/recopy 프로세스를 수행한다. 공개 ZIP의 raw hash는 검사 후에도 같다. 사용자는 dirty acknowledged/pending 상태를 실제 owner에서 이어갈 수 있다. `public-archive-check.json`에 정확한 zip 크기/hash와 결과가 있다.

C2 HTTP 검사는 기존 loopback 서버, Client, 기존 CLI 요청 adapter를 사용한다. client 상세 읽기와 서버 owner 상세 읽기가 정확히 같으며 CAPTURE 재시도도 같은 응답이다. public 실행 읽기 정보는 저장 권한이 아니다. source/evidence/attempt를 조작하면 서버는 실제 retained 파일을 검증하여 거절한다.

## 거절 및 회귀

원 snapshot/receipt row 불일치·누락, completed reference/publication 모순, proof/map/input/job/result/evidence tamper, rehashed map의 semantic 모순, current informational origin marker 변경, 다른 source/candidate/attempt/evidence ref를 검사한다. 단순 digest 변경뿐 아니라 digest를 다시 계산한 변조 mapping의 typed replay도 검사한다.

중간 proof 보존 I/O 실패를 주입해 이전 saved manifest가 유지되는지 확인한다. 새 CAPTURE가 PRESERVING/REGISTERED에 남은 뒤 정확한 동일 scope 재시도와 중복 응답 복구가 동작한다. source 편집 이후 stale generation의 새 CAPTURE는 거절하고 저장된 원증거 읽기는 계속 가능하다. target stale CAS도 채택 전에 거절된다.

C1의 actual 18,000,012-byte local CSV/HTTP 경로, 일반128KiB/upload16MiB/create8MiB 거절, archive raw-name 사전검사, 기존 목적지 보호, atomic manifest-last/중간발행 실패, typed edit/취소/repair/unlink, 배치/참조 cold 복원 회귀를 그대로 실행한다. ACTIVE controller.lock만 size/mtime으로 비교하며 나머지는 full hash다.

## 미실행·경계

**Windows runtime, 실제 Qt widget/QTest, 정상·좁은 창, OS mouse, native FreeCAD/ParaView activation, Windows owned-job cleanup 캠페인은 NOT_RUN**이다. PySide6가 없으며 설치/다운로드하지 않았다. Linux loopback HTTP와 Windows HTTP/native 인수는 구분한다. 20GiB/100000files full campaign, 새 mixed-origin detail 실행/solver/provider 재실행 캠페인, 물리 승인·holdout 합격 판정도 수행하지 않았다.

C01 capsule와 Data related-save 최종 API는 NOT_INTEGRATED다. 사본에 없는 미승인 widget buffer가 복구됐다고 표시하지 않는다. 이 인도는 기존에 기록된 원실행의 정확한 cold 사용/저장·보고·명시채택 수용이며, 새 계산을 실행해 원실패를 숨기는 경로가 아니다.

개발 중 source-key/candidate-key/미보존-success fixture 기대값 오류는 교정했다. 시간 제한으로 XML이나 정상 exit가 없는 중간 실행은 NOT_COMPLETE로 보존하고 통과 합계에서 제외한다. 초기 실패와 후속 green 로그를 덮어쓰지 않는다. 본 환경의 외부 pytest plugin 자동 로딩을 끈 상태에서 built-in pytest assertions/fixture/정리를 그대로 실행했으며, 각 final process receipt의 실제 exit0만 합산한다.
