# 현재 자료와 재사용 판단

## 조사 범위

기준 main `1820cf1`, native upstream pin `3e48bf6138f495299f45b1af254bfb4aaff307b8`.
설치된 MoAI `moai-plan`, `moai-workflow-spec`, `moai/workflows/plan.md`,
`plan/spec-assembly.md`, `run/task-decomposition.md`를 읽고 요구→구현→수용으로 분해했다.
Codex에 없는 manager-spec/Claude Team 도구를 호출했다고 기록하지 않는다.
별도 사용자 인터뷰/재승인은 하지 않는다. 이번 목표·무료 조건·플랫폼·역할은 이미
사용자가 결정했고 기술상세 작성은 허가된 범위다. `.moai/project/tech.md`는 없으므로
재초기화하지 않고 ARCHITECTURE와 제품 계획/계약을 기준으로 사용한다.

## 소스에서 확인한 사실

- `motion.py`, `motion_panel.py`, `motion_path.py`: 복수구동·가동하위조립·참조복구,
  원경로 저장/CSV/Data 연결이 있다. 이를 새 구현으로 다시 세지 않는다.
- `fem_edit.py`: native 재료/조건·메시 품질·선택·국부크기·비동기 생성 경로가 있다.
  현재 허용 메시/실행 family에 한계가 있어 E1–E6의 실제 확대가 필요하다.
- `contact.py::law_errors`: 현 경로는 linear/tie, frictionless/Coulomb, 첫 단계부터
  전체유지 등을 허용한다. hard/cohesive, 다른 미끄럼 방식과 단계활성화는 거절한다.
- `freeze_contact.py`: 이미 static/dynamic 절차와 dynamic 밀도를 처리한다.
  ‘동해석이 전혀 없음’으로 새 계획을 만들면 중복이다. NS2는 그 다음 연결을 정의한다.
- `contact_fem.py`, `contact_results.py`: native접촉 DAT합력/모멘트와 실패 전 증분
  읽기가 이미 있다. R1/R2는 기존 parser를 지우거나 새로운 결과 owner를 만들지 않는다.
- `tie_adjustment.py`: 평면 단일대응 조정과 실제초기좌표/결과 재열기 인도가 있다.
  곡면/경계/복수후보는 별도 작업 C3이며 기존 인도 완료와 혼동하지 않는다.
- `CODEX_WORKFLOW.md`: Pro 큰 기능 작성, Sol 범위명확 연결, Astra 독립검토,
  Codex 공통통합과 상태기록. 사용자 요청대로 개발 중 전수 벤치마크는 하지 않는다.

기존 FN-10–15/25 본문에는 과거 ‘no contact’ 또는 단일 solid 제한이 남아 있다.
그 문장을 현행 구현으로 간주하지 않고 CURRENT_STATE와 위 소스의 실제 차이를 따른다.
전수 과거 문서 재작성은 이번 작업이 아니다.

## 미확정과 실행 위험

무료 backend별 hard/cohesive·주기·pretension·적층·mixed procedure의 정확한 native
지원 조합은 아직 이 SPEC에서 확인하지 않았다. 각 해당 작업의 처음에 공식 소스/문서와
기존 adapter를 대조하고 input→output 경로를 선택한다. 검토만 끝나거나 미지원표시만
추가되면 해당 작업은 미완료다. 새로운 모델·유료API·서버는 연결하지 않는다.
수치 허용치는 기존 기준을 사용하고 미정인 물리 요구는 UNKNOWN이다.

MoAI 형식 검사와 Astra의 기능/수용 검토 결과는 [review.md](review.md)에 남겼다.
형식 통과는 코드 구현이나 공학적 정확성 증명이 아니다.
