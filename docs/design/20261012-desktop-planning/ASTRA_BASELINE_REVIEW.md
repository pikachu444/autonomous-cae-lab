# Astra 독립 검토 — 기존 설계의 교정 기준

2026-10-12 `astra_design_review`에 명시적으로 `gpt-6-astra/xhigh`를 배정했다.
읽기 전용, 기준 main `9a6e308`, upstream `3e48bf6`, 최신 사용자 원요구와 실제 기존
계획/코드/보존 그림을 전달했다. **기존 계획은 새 상세 설계 완료 조건을 충족하지 않는다.**
Pro에게 새 요청은 아직 미전송이며 이 검토를 새 Pro 결과의 검수나 통과로 표시하지 않는다.

| 우선 | 요구·화면/경로 | 지적과 수정 기준 | Codex 적용/다음 확인 |
|---|---|---|---|
| P1 | 사용자 §1/4/7, CURRENT_STATE, v2 §11.3 | 다음 구현/cloud-only/기획만 아님 지시가 새 범위를 거스름 | current assignment와 계획 entry, §11.3를 수정. 기존 중단 FreeCAD 세션은 재사용하지 않음 |
| P1 | §2/5, v2 §10/T17/18/21/25-C1 | 이미 있는 owner/bridge를 신규로 분류 | SOURCE_REUSE로 현재 코드 분리, Pro가 작업표에서 재작성 제거 |
| P1 | R01/14–18/28–32, T24/T25 | nonlinear/explicit/failure/constitutive/UQ/surrogate/MOO/remote가 한 포괄 행 | 각 사용자 결과별 workflow·input/output·code·validation 명세 필요, 무료 미결은 유지 |
| P1 | §6/7, UI01–12 | 3D/곡선/graph가 설명문인 배치도 | 실제 합성 데이터·선택·행/곡선·활성 행동·오류 위치의 상태별 편집 원본 필요 |
| P1 | Material UI07→Data/Plan | import/단위 변환·stress/strain 척도·횡조건·train/holdout·residual·채택 흐름 단절 | bounded Qt spike는 일부 조작만 확인. Pro 전체 화면·owner 연결과 두 CSV 시안 필요 |
| P1 | Contact UI03→Post→Pre | face pair/friction/gap 의존성·normal·결과·저장·재연결 부족 | 사용자 면 집합 선택부터 split/normal flip/unsupported law/convergence/rebind cancel까지 명세 필요 |
| P1 | Study, Evaluation, UI09/UI12 | Study 독립 화면 누락, Workbench와 통합 | Study 별도 화면·가설/근거/판단/후속 연구, 같은 Evaluation editor/owner 설계 필요 |
| P1 | 화면별 편집/저장 상태 | Material+Plan 동시 dirty, cell buffer/owner draft/saved rev, 다른 client 충돌·부분 save 구체화 부족 | 작업별 전이에 영향 문서·Undo 대상·save/close/cancel 복구 결과 표시 필요 |
| P1 | §2.2·직접 실행/휴대 저장 | `.caelab` 권고와 현재 `.caepre`/store 방식 사이 미결 | 기존 형식 재사용·더블클릭·최근 파일·same owner·Save As/branch·새 store migration의 행동 확정 필요 |
| P1 | 비용, Expert, T22 | 개발 Pro relay와 제품 inference 혼동 위험 | existing subscription 경로 실제 확인, no provider도 drafts/retained discussion 보존, 자동 유료 fallback 금지 |
| P2 | 도킹/키보드/배율 | 크기/shortcuts 원칙에 비해 최소 폭/축소/focus/restore/시각 규칙 부족 | Qt spike offscreen만으로 desktop/DPI 통과 아님. 실제 dock/focus/file dialogs 확인 필요 |
| P2 | §4/7 검증 | 계획/조작/회귀/수치/최종 통합의 시점·source 재사용 대응 부족 | 기능별 검증 목적/시점/선행/source/run/차이 표 필요. UI 변경에 무관 solver gate 금지 |

적절한 기존 기준: ADR0060–0062의 독립 문서/native owner, Domain–Evaluation–Plan–Runner
분리, exact revision, invalid draft 저장, 이전 결과와 UNKNOWN/NOT_RELEASED 보존.
새 공통 실행기·대체 optimizer가 필요하다는 결론은 아니다. 실제 Windows GUI/solver/provider
실행과 전체 과거 ADR 감사는 하지 않았다. 새 산출물은 별도로 다시 검토해야 한다.
