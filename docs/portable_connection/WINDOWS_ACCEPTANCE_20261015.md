# Windows 연결·이동 사본의 좁은 수용

실제 Pro Portable C2 반환 ZIP SHA256은 `51a89195483f27d0cd386a4810b40d50d36e5aee3e9ff0ad9cbc8d41d65b9512`다. 요청 source 기준은 `86bc7db`와 C1 전용28 WIP이며, 아래 실행은 현재 main의 root 공통 통합 뒤 수행했다. Pro의 Linux238PASS/3SKIP 보고를 Windows 실행으로 바꾸지 않았다.

## 실제 확인한 동선

- 원 Windows 재현3종(pending evidence, Data frozen input, detail attempt identity)을 원 store 없는 별도 프로세스에서 읽었다. 원 result·evidence bytes를 보존하면서 상세·보고서·비교·재복사가 종결됐다. 원 미보존 성공 상세는 그대로 남기고 원 실패 후보를 실패 보고서로 읽었다. 모든 cold 결과는 Job0/evaluator·dispatch0이다.
- 새 Data-bound 사본에서는 저장된 보고서의 정확한 자산과 증거2개, 재료 채택1개를 새 프로세스에서 읽었다. 기존 복사 기능으로 다시 발행하고 다른 프로세스에서 증거2개·채택1개·끊긴 참조0을 확인했다. 이 재복사 selection은 Data2/Material/Numerical4문서다. Report 자체를 재복사한 것은 아니다.
- 실제 HTTP 서버 스레드에서 기존 request-local immutable 검증을 공유하고, 다음 요청의 파일 변조는 다시 거절함을 확인했다. 늦게 바뀐 원문서에는 이전 관계 변경을 적용하지 않았다. 쓰기 경로에 읽기 scope를 추가하지 않았다.
- Windows Qt에서 Ctrl+Delete → 영향 확인 취소 → 원문서 bytes 불변 → 연결 해제 → 연결 추가 → 같은 원 Material 참조의 동작을 확인했다. 새 계산·provider는 생성하지 않았다.
- 실제 `apps.research.desktop.main`과 기존 HTTP Client로 connection 창을 열어 정확한 사본 문서를 선택했다. 1200×780/820×600 캡처를 직접 읽었다. 한글·상태·선택 표시가 읽히며 좁은 그래프는 scroll로 이어진다. 앱을 닫은 뒤 문서 파일 bytes 불변, Job0을 확인했다.
- 임시 폴더에서 실제 Windows COM으로13개 바로가기를 만들고 같은 설정으로 재실행했을 때 링크 bytes가 유지됨을 확인했다. 사용자 시작 메뉴는 변경하지 않았다. 두 PowerShell launcher는 connection과 정확한 문서 ID를 같은 서비스 주소로 전달했다.

## 실패 기록과 교정 범위

처음 supplied3+bound 전체와 bound 단독을 각각100초로 실행했을 때 최종 재복사 검증 중 시간 제한에 걸렸다. 두 timeout과 최종 pytest XML 부재를 유지한다. 동일 bound 동선의 남은 읽기·재복사·재열기는 이미 저장된 사본에서 각각12.86/49.99/17.18초로 나누어 종결했다. 이를 원 전체 pytest4PASS로 집계하지 않는다.

기존 Qt 실패는 실제 top-level 활성화 전제가 빠졌고, 검사 도우미가 실제 비동기 대화상자 도착 전에 끝났다. 그 전제를 확인한 뒤에도 `QTest.qWait` busy loop에서 Python worker의 진행이 지연됐다. 실제 HTTP catalog는0.579초였지만 같은 GUI 검사에서는12초 이상 걸렸다. 검사 spin을 `processEvents`와 짧은 `time.sleep`로 바꾸자 같은 취소·불변·해제·추가 조건이10.74초에 통과했다. 선택창은0.266–0.547초, 영향창은0.357–0.635초에 도착했다. 제품 입력·수치 threshold·CAS·성공 조건은 바꾸지 않았다. 제품 Qt worker에 별도 캐시를 추가하지 않았다.

처음 COM과 모든11도구×2launcher 검사를 함께60초로 실행한 것은 전체 시간 제한에 걸렸다. 전체22경로 완료로 세지 않는다. 변경된 connection2경로만 기존 fixture로 분리 확인했고, COM1검사도 독립적으로 최종 XML을 남기며 통과했다.

## 실행 영수증과 한계

| 실행 | 실제 결과 |
|---|---|
| HTTP scope·변조·late owner | `c2-windows-scope-http-qt`의 HTTP1PASS; 같은 군집의 Qt는 당시 실패로 유지 |
| Qt 원 실패의 최종 교정 | `c2-windows-qt-worker-yield`, pytest1PASS10.74초, native receipt11.97초 |
| 실제 desktop 진입·두 크기 | `c2-entry-gui-native`,18.88초 exit0 |
| connection launcher2경로 | `c2-connection-launcher-only-native`,8.59초 exit0 |
| 실제 임시 COM13개·동일 재실행 | `c2-shortcuts-com-only`, pytest1PASS8.24초, native receipt9.10초 |

로그·JSON·XML·캡처는 `_workspace/delivery-install-connections` 아래 해당 이름에 보존했다. 각 native_check는 정확히 소유한 프로세스를 Job으로 추적했고 `job_empty`, `cleanup_error=null`로 끝났다. 사용자 창이나 이름으로 찾은 프로세스를 종료하지 않았다. 실제 마지막 GUI는 QApplication.exec를 사용했으며 OS 마우스·키보드 자동화 전체를 검증했다는 주장은 아니다.

C01 raw-cell archive는 아직 NOT_INTEGRATED다. Data C3의 원 identity 읽기 API와 Material/Plan의 미구현 ownerless archive 읽기를 분리한다. Portable의 편집 사본 지원 owner는 Data/Material/Numerical이다. 모든 도구·native 문서의 이동 사본, 신규 설치 PC, 전체20GiB/100000파일 캠페인, 새 솔버·AI·원격 실행 및 공학적 적합성 승인은 이 수용 결과에 포함되지 않는다. FN01/FN31 전체 완료로 표시하지 않는다.
