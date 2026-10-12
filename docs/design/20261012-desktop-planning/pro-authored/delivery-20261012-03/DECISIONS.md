# 결정 부록 — Penpot 제외

**PRO-DESKTOP-DESIGN-20261012-03 · 2026-10-12 (Asia/Seoul)**

## D03-PENPOT-EXCLUDED — 최신 사용자 결정

사용자 원문: **“기존 계정이 없어서 penpot은 탭 닫고 무시해줘”**.

결정 상태: **적용**. 이미 답한 선택이므로 계정·도구 방향을 다시 묻지 않는다. 실제 Penpot 탭 닫기는 Codex 측 직접 지시의 일부이며, 이 Pro 세션에서 그 탭을 조작했다고 주장하지 않는다.

| 대상 | 현행 적용 |
|---|---|
| Penpot 계정·로그인 | 생성·연결·재시도 작업에서 제외 |
| Penpot 화면 편집·native `.penpot` export | 사용자 검토/설계 완료/구현 인계의 관문에서 제외 |
| 유료 대안·trial·추가 hosting | 도입하지 않음 |
| 편집 원본 | 기존 SVG의 text/shapes, screens JSON의 state/layer/hotspot/target, `.drawio`, Designer `.ui`, Qt Python source 유지 |
| 클릭·키보드·표/곡선·저장/재개 | 로컬 Qt gallery/Material prototype 및 Codex의 실제 Windows 검토로 확인 |
| 실제 D1 Qt 실행 | 아직 이 회수 작업의 새 실행 증거 없음. Codex가 회수한 정확한 D1 파일로 별도 확인 |

## 원 D1 문서에 대한 적용 범위

원 D1 문서의 바이트와 `ARCHIVE_MANIFEST.json`을 보존하기 위해 본문을 덮어쓰지 않고 이 부록을 최신 해석으로 적용한다.

| 원 D1 문서 | 이 부록으로 바뀌는 지시 |
|---|---|
| `README.md` | Penpot 계정에서 원본 제작·native export를 이어서 하라는 인계 제외. Qt/SVG/JSON/draw.io 경로를 사용 |
| `DECISIONS.md` | Penpot 이용 가능성·export 미확인을 현행 미해결 사용자 결정 또는 완료 gate로 유지하지 않음 |
| `CODEX_HANDOFF.md` | Penpot 접속·계정·편집/export 담당 작업 제거; 이 부록의 CODEX_HANDOFF로 대체 |
| `PROTOTYPE_SCENARIOS.md` | 화면/flow 데이터와 대표 작업은 유지. Penpot 연결 확인이 필요한 관문은 Qt 갤러리의 동일 ID/전이 확인으로 수행 |
| `SCREEN_SPEC.md`, `screens/screens.json` | 편집 원본과 화면/상태 정의 유지. Penpot 사용 또는 export를 runtime/검토 의존성으로 요구하지 않음 |
| `VERIFICATION_PLAN.md`, `QA_REPORT.md`, `reviews/` | 과거의 실제 미실행 사실·검토 결과는 보존. Penpot 미실행 자체는 앞으로의 미완료 gate에서 제외 |

전체 사용자 기능, owner, material/contact/Study/Evaluation workflow, native host, 단위·mask·저장 계약, 기존 구현 재사용과 공학적 UNKNOWN은 변경하지 않는다. F05 `3.32295e-6 > 1e-6`을 유지한다. Penpot 제외는 제품 본구현 승인이나 새로운 Qt/solver/provider 수용 판정이 아니다.

## 원본 보존 결정

원 D1 ZIP·287개 member·원 manifest·최종 독립 리뷰를 그대로 게시한다. 이 부록은 D1 재작성본이나 D2가 아니다. 추가 게시 파일의 무결성은 별도 `PUBLICATION_MANIFEST.json`으로 관리하며 원 D1 해시와 혼합하지 않는다.
