# Windows 데스크톱 상세 설계 검토 자료

최신 사용자 요청(2026-10-12)에 따른 작업 자료다. **전체 상세 기획은 진행 중이고
제품 본구현은 승인 대기다.** 이전 Pro v2와 현재 코드를 재사용한다. 최신 원요구와
7개 설계/조사 본문을 실제 Pro 새 대화에 전송했고 작성 중이다. 여기의 Codex 정리와
기술 spike를 새 Pro 설계로 표시하지 않는다. 현재 배정·연결 상태·다음 행동은
[CURRENT_STATE](../../../CURRENT_STATE.md)에 있다.

| 검토 자료 | 성격과 현재 확인 범위 |
|---|---|
| [현행 ADR 적용 기준](../../ADR_APPLICABILITY.md) | 유효한 경계·역사 근거·기능별 검증 분리. 원 threshold/실패 보존 |
| [코드 재사용 조사](SOURCE_REUSE.md) | `9a6e308`의 owner/창/명령과 화면 개선 지점. source와 이전 실행 증거 구별 |
| [Astra 기준 설계 검토](ASTRA_BASELINE_REVIEW.md) | 실제 `gpt-6-astra/xhigh` 배정의 독립 검토. 기존 v2의 누락과 수정 기준. 새 설계 통과가 아님 |
| [Pro 전달 본문](PRO_REQUEST.md) | 새 요구·원본·기준 버전·책임·완료 조건. initial ZIP 첨부 실패, 실제 inline 원문 전달. latest Penpot 제외 결정은 후속 교정에서 반영 |
| 편집 가능한 흐름 원본 | actual Pro가 `.drawio` 산출물 작성 중. 회수 뒤 실제 파일과 앱/export 확인을 연결 |
| [Qt 시제품](qt_prototype/README.md), [실제 창 재열기](native-material-reopen.png) | 별도 PySide6/Designer 시제품. offscreen 교정과 제한된 실제 Windows 파일/선택/채택/Undo/도킹/저장·새 프로세스 재열기 확인. 계산은 DEMO/SIMULATED UI |
| [Qt 독립 검토와 실제 조작 기록](QT_REVIEW.md) | 원 P1/P2 교정·최종 해시, Astra 판정 범위와 Codex의 native 경로·남은 확인 |
| [무료 도구와 라이선스](TOOLS_AND_LICENSES.md) | 공식 자료/설치 사실/접속 확인을 구별. 제품 배포 승인은 별도 |
| [MoAI 연결 증거](tool_connection.json), [stdio MCP 검사](moai_mcp_probe.json) | 기존 설정 보존·CLI 연결·실제 local handshake. 현재 호스트 도구 노출과 `spec_progress` 호출 확인, hook trust는 미확인 |
| [MoAI SPEC](../../../.moai/specs/SPEC-DESKTOP-001/spec.md) | 전체 기능·설계/수용 계약으로 연결하는 draft. 기존 문서 복사나 별도 현재 큐가 아님 |

시제품은 현재 제품 서비스·solver·provider에 접속하지 않는다. 사용자/회사 자료를 넣지
않으며 제공된 공개 합성 CSV로 조작한다. `.ui`와 Qt 소스는 편집 가능하다. 이미지 수나
offscreen assertion 통과로 전체 GUI·DPI·물리·공학적 release를 완료 처리하지 않는다.

Penpot은 계정이 없다는 사용자의 최신 지시로 제외하고 탭을 닫았다. 모든 화면과 기능의
상세 대응, editable SVG/.drawio와 새 실제 Pro 설계·교정은 아직 회수/제출 전 단계다.
Qt의 제한된 실제 조작은 전체 제품 화면의 수용을 뜻하지 않는다. 기존 PDF나 웹 시안을 이 결과의
대체물로 인정하지 않는다. 브라우저는 기획/협업 도구이고 제품의 주 화면이 아니다.
