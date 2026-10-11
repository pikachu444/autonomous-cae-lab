# CAE 작업 화면 교정 — 2026-10-10

2026-10-11: 아래는 당시 합성 시안의 구현 기록이며 현재 제품 화면의 기준이 아니다.
독립 Data/Material/PDE 경계는 ADR0060, 실제 프로그램을 따르는 화면·조작과 개발 계획은
[PRODUCT_PLAN](../PRODUCT_PLAN.md)을 적용한다. 아래 5앱·Pre 모드 구성은 역사적 기록이다.

이 산출물은 변경 설계의 조작 가능한 시안이다. 합성 데이터만 사용하며 Core, 솔버, 실제 FreeCAD/ParaView, LLM, 네트워크 서비스에 연결하지 않는다. 5개 독립 앱 + 선택적 Workbench 구조와 기존 52개 요구·17개 사용 사례를 유지한다. 새 제품 구현 완료를 주장하지 않는다.

사용자가 지정한 기준은 FreeCAD·ParaView·STORM 수준의 전문 작업 도구다. 반복 질문이나 임의의 시각 콘셉트 추첨 없이 그 방향으로 구현한다. 밝은 사무실에서 오래 사용하는 조밀한 편집 환경: 중성 회색 패널, 흰 데이터 영역, 청색 선택, 상태별 별도 표시, 13px 시스템 글꼴, 작은 일관된 선형 아이콘. 웹 기술은 허용되며 제품의 기존 HTML/CSS는 재사용 기준이 아니다.

## 작업 배치

- Pre: 모델 트리·고정 편집 대상 / 큰 공간·자료 편집기 / 문서 검사. host는 작업 모드와 별개다. CAD·자료·재료점·PDE는 다른 편집기다.
- Post: pipeline·연산별 속성 / 큰 필드 또는 A/B 뷰 / 조회표·곡선. 활성 source, 보기 선택과 편집 대상을 따로 표시한다.
- Runner: 넓은 작업표와 선택 job의 상세·로그. 새 실행 초안만 검사→준비→제출하며 기존 job 입력은 읽기 전용이다.
- Optimization: 왼쪽 평가 절차·변수 / 위 Pareto·반응 곡선 / 아래 후보표. 세 보기의 후보 ID가 일치해야 한다.
- Expert: 논점 목록 / 스크롤 대화와 고정 작성창 / 선택 발언의 원문·근거. 취소는 관련 job을 직접 대상으로 한다.
- Workbench: 실제 선택·이동·연결 가능한 graph / 노드·포트·연결별 inspector. 앱 열기는 별도 명령이다.

공통 패널은 Dockview의 이동·크기 조절·배치 저장을 재사용한다. 데이터표는 AG Grid Community, 차트는 Plotly, 연결은 React Flow를 사용한다. 무료 기능만 채택하며 이 시안의 선택이 제품 패키지 채택 확정은 아니다. Pre/Post의 native 표·선택·렌더러는 제품에서 해당 host를 재사용한다.

## 소유 및 공통 코드 계약

Root: package/build, src/common.tsx, src/style.css, src/main.tsx, src/PrePost.tsx, src/Viewport.tsx와 통합·문서·검증.
Worker A: src/RunnerOptimization.tsx 및 그 전용 CSS. Worker B: src/ExpertWorkbench.tsx 및 그 전용 CSS. 공통 파일은 편집하지 않는다. 모두 합성 상태/저장만 사용한다.

common exports: Workspace({id, panels: Record<string,{title,content:ReactNode}>, setup(api)}), Toolbar({children}), Button({children,icon?,primary?,danger?,...buttonProps}), Badge({children,tone?:'good'|'warn'|'bad'|'info'|'neutral'}), Field({label,children}), Properties({rows:Array<[string,ReactNode]>}), DataGrid({rows,columns,selectedId?,onSelect?,onEdit?,height?}), Chart({data,layout?,onSelect?}), useStored<T>(key,initial), Notice({children,tone?}). Workspace setup uses DockviewApi.addPanel({id,component:'content',title,position:{referencePanel?,direction:'left'|'right'|'above'|'below'|'within'},initialWidth?,initialHeight?}); panel IDs exactly match panels map. Workspace owns layout persistence, reset, current panel maximize and accessible alternate layout controls. DataGrid rows require stable string id; columns use AG Grid ColDef. Chart onSelect receives point customdata or text ID. Workers export Runner(), Optimization(), Expert(), Workbench() components; each fills parent flex column with its toolbar/workspace. Root mounts one app and keeps each app's model in useStored, all state namespaced cae-design-v2. Changes are not remote writes.

## Acceptance before handing over

Review actual render at 1440×900, 1920×1080 and compact 1100×760. Page itself does not scroll; panels do. Check editing while selection changes, candidate table↔point selection, topic↔evidence, node/port/edge distinction, resize/maximize/restore/reload, errors preserving input, source partial restore, submitted input immutability and job request reconciliation. Record observed results and untested cases separately. Independent review must inspect source and screenshots; solver/native validation remains outside this prototype.
