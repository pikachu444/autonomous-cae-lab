# 검증 기록과 남은 확인

## 실제 수행

공개 CSV는 `time,stress`의 3개 수치 행이다. 기존 Data owner와 JobManager를 사용한 성공 가져오기와 열 번호 9의 실패 가져오기를 실제 실행했다. Material 한 문서, 그 재료와 Data 결과를 참조하는 피팅 Plan, 별도 Numerical Plan을 저장했다. 문서 owner 총 네 개이며 Numerical ID는 서로 다르다.

사본 생성 후 예제 원 보관소 전체를 물리적으로 삭제했다. 사본을 한글·공백 경로로 이동하고 별도 프로세스에서 원자료, 원입력, 성공/실패 기록, 단위와 참조를 읽었다. 원래 owner 명령으로 Material/Data를 편집·저장했으며 또 다른 이동/새 프로세스 재열기도 전용 테스트에 포함했다. 재열기 시 계산, provider, 자료 재등록을 호출하면 실패하도록 한 검사도 통과했다.

실제 loopback HTTP 서버를 사용한 Client/직접 Workbench 비교, 정확한 저장 참조, 사본 생성/같은 요청 재시도, 다른 CLI 프로세스의 같은 서비스 위임, 원본 삭제 후 새 서비스 시작/편집/저장을 수행했다. HTTP를 대역 함수로 바꾸지 않았다. 동시에 같은 사본 요청을 보내도 새 폴더를 한 번만 발행하는 것을 검사했다.

경계 검사는 기존/빈 폴더 덮어쓰기 거절, stale generation/session/inspection, 명시 승인 누락, 의존 문서 미선택, 미저장 입력 제외, 정확한 옛 입력 보존, Unknown/알 수 없는 필드 보존, 주변 자료와 설정 비수집, 실제 원자료 누락 위치, 동일 바이트 복구/오복구 거절/손상본 보존, 발행 실패의 불완전 상태, ZIP traversal/절대 경로/ADS/Windows 장치명/대소문자 별칭/중복/symlink를 포함한다.

기존 실제 comparison 생성·보존·cold reopen·재저장을 통해 숫자 곡선은 바꾸지 않고 사본 binding만 새 문서로 연결하는 것을 확인했다. 실제 Study/Report capture/Evaluation stage 참조도 읽었다. Native descriptor 검사는 TEST_ONLY 보고를 기존 registry에 등록하는 **계약 검사**이며 FreeCAD/ParaView 실행 증거가 아니다.

최종 실행 수치와 원문 로그는 인도 패키지의 `verification/final-tests.log`, `verification/final-tests.xml`, `verification/public-check.json`, `verification/qt-check.json`, `verification/package-check.json`을 기준으로 한다. 의도적으로 중복 ZIP 이름을 만드는 안전성 검사에서 Python zipfile 경고 한 건이 발생할 수 있다.

## 수행하지 못한 것

PySide6가 현재 컨테이너에 없으며 고정 프로젝트 버전 6.9.1 다운로드는 DNS 연결 실패로 설치하지 못했다. Qt 전용 모듈은 collection 단계에서 SKIPPED이고, 별도 Qt 실행 스크립트는 BLOCKED와 `captures_created=false`를 기록했다. 실제 화면 캡처가 없다. 작성 코드의 AST/컴파일 성공을 GUI 동작 성공으로 세지 않는다.

따라서 두 크기의 실제 배치, Tab/Enter/context menu/마우스 드래그, 한국어 glyph/focus 상태, 실제 화면의 복구 동선은 미검증이다. `tests/test_connection_window_qt.py`와 `examples/connection_window_check.py`에 검사 코드를 제공한다. Windows의 실제 FreeCAD/ParaView 창 활성화, 다른 native tool 설치, WSL 환경, 물리 계산의 유효성도 이 환경에서 확인하지 않았다.

추가 비용이나 provider 사용은 없고 회사 자료도 사용하지 않았다. FN01-02의 위 공개 파일 경로는 검증했으나 FN31의 GUI 승인 및 제품 전체 인수는 남아 있다. root 공통 CLI/MCP registry 전체 통합, FN02-02, FN26, 다른 팀 동해석/GUI/설치 완료를 이 결과로 대신하지 않는다. 모든 산출물의 공학적 상태는 NOT_RELEASED이다.
