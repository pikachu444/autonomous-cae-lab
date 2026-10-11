# 조작 시안 검수 기록 — 2026-10-10 교정 완료

기준 제품 소스는 `a10f2023a2084512839b5e0af8ab0adc0aeb9293`이다. 이 디렉터리는 별도의 합성 설계 시안이며 제품 Core·solver·native bridge는 변경하지 않는다. 2026-10-10 로컬 Windows의 실제 Codex 브라우저에서 아래 조작을 확인했다. 개발자가 쓴 동작 설명을 시험 결과로 세지 않는다.

| 검수 | 실제 관찰 | 범위 |
|---|---|---|
| Pre host / mode | FreeCAD 표시를 유지한 채 자료→CAD 왕복 | mock host 상태. native 전환 아님 |
| Pre 고정 편집 대상 | Clamp arm의 48 mm 초안 중 Base plate 선택. command는 arm으로 유지. 적용 후 base 68 mm, arm 48 mm | 객체별 합성 기하·속성 |
| Pre 저장 실패 | 쓰기 실패 시험 후 수정값·dirty 보존, 재시도 시 r8 저장 | 실제 파일 I/O 실패 아님 |
| Pre 재열기 | 문서 재열기로 페이지를 실제 재시작하고 저장 문서·선택 복원 | 브라우저 저장 |
| Post source | B 선택 시 source ID, 입력 200 N, mesh-B-r1로 변경 | 합성 메타데이터 |
| Post 연산 | 보간 탐침에는 좌표/좌표계/보간 방식, 선에는 시작·끝·표본 수 | native 연산 실행 아님 |
| Post 부분 복구 | B 누락 시 B 기반 분석 보존/사용 불가, A 원위치 조회 명령은 계속 가능 | synthetic missing-source 시험 |
| Runner invalid 차단 | 표본 수 0 입력→오류와 제출 disabled. 1200으로 수정→준비 | 실제 runtime 사전검사 아님 |
| Runner 응답 유실 | 요청 REQ-DRAFT-mv1x4xhq-fk2t 생성 후 페이지 재시작, 요청 조회→JOB-mv1x54fa-nbk2 복구. 전체 job 수 4개로 유지 | 로컬 mock 원장 |
| Runner 제출 입력 | 실행 이름 input readonly 확인. 새 실행은 별도 draft | 합성 고정 입력 |
| Optimization 연동 | 표의 C003→상세/곡선 C003, Pareto 점 클릭→C024 및 표·상세·곡선 동일 ID | 합성 후보 |
| Expert 근거 | mat-3 선택→screening.csv, 논점 변경→impact-observation.txt | 미리 쓴 원문·대화 |
| Expert 초안 | mat-3 답글 초안을 쓰고 다른 논점 왕복 및 페이지 재시작→내용과 reply 대상 보존 | 실제 LLM 호출 없음 |
| Expert job 취소 | E-014 취소 후 E-014만 취소됨, E-015는 진행 중 유지 | mock job 상태 |
| Workbench 선택 | 실제 SVG 연결선→연결 inspector, 포트 버튼→포트 inspector. 앱 열기는 별도 명령 | 실제 React Flow 조작 |
| Workbench 불일치 | field→response 연결 시 자료 형식 불일치 표시, 새 edge 없음 | type/schema 정책 |
| Workbench 부분 저장 | analysis r2 생성 후 연결은 r1 유지. 연결 갱신 실패→pending, 재시도 후 r2 연결. 원본 r2 재생성 없음 | mock 문서·연결 원장 |

초기 렌더에서 Dockview 기본 테마와 초기 Optimization 폭 오류를 찾아 수정했다. Runner 상세의 재실행/취소 동작을 스크롤 영역 밖 고정 footer로 옮겼다. strict TypeScript 검사와 standalone bundle 빌드가 통과했다.

## 독립 검수에서 발견한 문제와 교정

첫 독립 검수는 그래프 연결선이 보이지 않는 캡처, 모드와 맞지 않는 Pre
속성, 자료 변환 불일치, 동작 없는 Post 옵션, 스크롤 아래로 사라지는
명령, 저장 예외를 숨기는 처리의 여섯 문제를 지적했다. 교정 후 재검수했다.

| 교정 | Root의 추가 실제 관찰 |
|---|---|
| Workbench 그래프 | 노드 측정 및 dock 크기 변경 후 맞춤. 1100 화면에 모든 노드와 실제 연결선 표시. response→expert 호환 포트 연결로 네 번째 edge `link-1791608720158` 생성 |
| Pre 문맥 | 자료1행 선택 시 값·mask inspector 동기화. 재료점/PDE 속성 분리. 고정 Face set12 뒤 Base plate를 보아도 `BC-FIX-12`와 Support block 참조 유지 |
| Pre 변환 | 배율2와 구간0.00–0.05가 변환 열·inspector·곡선과 mask에 반영. 원본 열 별도 보존. 작은 화면에서도 변환 명령 표시 |
| Post 시간/범위 | 연결 상태에서 A=0.50s→B=0.50s. 해제 후 B=0.75s, A 유지. 별도 색 범위 A0.043/B0.059, 표·속성·합성 geometry/color도 같은 시간 사용 |
| 고정 명령 | Workbench 연결 검사/저장/취소와 Optimization 범위 적용/취소가 본문 스크롤 밖. 1100×760에서 실제 버튼 위치 확인 |
| 저장 실패 | 저장 경로 오류 주입→미저장 경고, Pre revision r8와 입력 유지. 해제→재시도→문서 저장 r9. 앱 이동 시 pending 값도 보존하도록 수정 |
| 패널 수명 | Post 경계 포인터 드래그176→232px. 실제 재시작 뒤232px 유지. 확대/복원, 조회표를 속성 패널 아래로 이동, 기본 배치 복원 |
| Optimization 초안 | 상한4→4.5 편집 중 합성 표본24개 추가→총48개. 미적용4.5와 기존C001 값 유지. 편집 취소 뒤 원 범위4 복원 |
| Expert 계획 | 변경 적용→후보36/예산45분/검증시험02. 기존 job2개 유지, 새 실행 없음 |

독립 검토자는 수정 소스와 여섯 앱 × 세 해상도(1440×900, 1100×760,
1920×1080)의 **18개 실제 캡처**를 열어 확인했다. 이번 여섯 문제 교정
범위에서 추가 P1/P2를 발견하지 못했다. 이는 소스·시각 검토이며,
검토자가 브라우저 조작이나 빌드를 재실행한 것은 아니다.

캡처: `artifacts/ui-design-20261010/{pre,post,runner,optimization,expert,workbench}-{1100,1440,1920}.jpg`.
두 크기의 DOM 측정은 `viewport-evidence.json`에 있으며 페이지 자체의
추가 스크롤은 없었다. 패널 내부는 스크롤한다. 작은 그래프는 확대·목록·
속성창을 함께 사용한다. TypeScript 검사와 standalone 빌드가 통과했다.

## 한계와 다음 제품 수용

기준 제품 commit의 CI run `37789173095`는 **failure**다. 이번 UI 시안의
로컬 빌드 통과와 섞지 않는다. 새 solver/native CI나 수치 시험은 수행하지
않았다. 실제 quota/security 예외, native I/O, 파일 transaction,
제품 source별 부분 복구, exact-open, 키보드/보조기술 전체 수용,
실제 FreeCAD/ParaView·Core·solver·LLM 연결, 전체52 요구와 A–D 제품 수용은
미검증이다. 초기 Runner 완료 후 선택 유지 관찰은 비동기 완료 도중의
독립 재현을 대신하지 않으며 해당 제품 수용은 남긴다.

설계/시안 교정 상태만 완료다. 엔지니어링 승인은 UNKNOWN/NOT_RELEASED다.
