# 화면과 시제품 검토

검토 대상은 **Windows 데스크톱 제품의 설계와 실제 Qt 상호작용 시제품**이다.
형상·메시·계산값·전문가 발언 예시는 합성 자료다. 실제 FreeCAD/ParaView 연결이나
solver·optimizer·provider를 실행하는 제품 개발은 사용자 검토와 개발 시작 지시 이후다.

## 먼저 열기

기존 Python/PySide6로 실행하며 추가 설치나 계정은 필요 없다.

    Set-Location C:\SourceCodes\autonomous-cae-lab
    py -3.13 docs/design/20261012-desktop-planning/pro-ux/qt_prototype.py --tool cad

**Window 메뉴**로 Simulation, Runner, Post, Numerical, Expert 등을 연다.
이렇게 열린 창은 같은 검토 세션을 사용한다. 독립 작업만 보려면 마지막 cad를
post, numerical, expert, data, material, pde, study, report, acquisition 등으로 바꿔 바로 시작한다.
별도로 실행한 프로세스 사이의 자동 연결은 이 시제품에 없다.

표는 F2/Enter로 편집하며 Ctrl+Z/Y로 되돌린다. Ctrl+S는 현재 문서를 저장한다.
여러 도구의 작업을 함께 이어서 보려면 **File → Save review session…**으로 저장하고
다음처럼 다시 연다. 창을 닫는 것은 작업 취소와 다르다.

    py -3.13 docs/design/20261012-desktop-planning/pro-ux/qt_prototype.py --session "C:\Review\Clamp research.json"

## 형상을 만들고 결과에서 설계를 판단하기

| 순서 | 실제 조작 | 확인할 결과 |
|---|---|---|
| 형상 | CAD의 Sketch → Draw line으로 드래그한다. Width를 바꾸고 Constrain rectangle을 누른다. Features에서 두께·구멍을 편집한다. | 선이 유지되고 표와 그림이 같은 치수를 보여 준다. |
| 조립·메시 | Assembly의 부품·인스턴스, Motion의 자세를 바꾼다. Use pose 뒤 Mesh → Preview mesh를 누른다. | 선택 부품의 상대 자세와 메시가 바뀐다. 불량 요소 행 선택이 그림에 연결된다. |
| 조건 | Conditions/Contact에서 면 집합·하중·구속·마찰·간극을 편집한다. 저장한 뒤 Use in Simulation을 누른다. | 동일한 저장 형상을 해석 창에서 본다. 빈 접촉면이나 오래된 메시는 Check에서 수정 위치로 돌아간다. |
| 해석 | Simulation 트리의 Model/Steps/조건/Output을 선택해 편집한다. Save → Run analysis… → Create review attempt. | 확인한 입력의 PREPARED 작업이 Runner에 생긴다. 실제 프로세스는 제출되지 않는다. |
| 결과 | Runner에서 작업을 선택하고 Review → Load retained result fixture → Open result. | 같은 실행의 합성 결과가 Post에 열린다. 배열·단위·시각과 측정값이 함께 바뀐다. |
| 조사 | Post에서 Clip/Plot over line, Pick gauge/Measure…, Compare…를 조작한다. Register response…로 측정을 연결한다. | 선택 위치·필터·곡선·A/B 값이 보인다. 없는 프레임은 unavailable로 남는다. |
| 설계 비교 | Window → Numerical에서 변수·목표·제약과 후보 p19/p04를 비교한다. Apply to owners…에서 각 문서에 Apply, Save를 누른다. | 선택만으로 원 설계가 바뀌지 않는다. 저장한 설계와 원 평가 결과가 함께 남는다. |
| 복구·재개 | Review → Fail next Material adoption save를 선택한 뒤 같은 채택을 시도한다. 실패한 Material만 다시 Save한다. 세션을 저장하고 다시 연다. | 성공한 CAD 저장은 유지된다. 실패한 문서만 재시도하고 같은 후보 선택·결과를 다시 연다. |

CAD/FE와 Post의 최종 제품은 각각 FreeCAD·ParaView native 작업 환경으로 구현한다.
여기서의 Qt 형상 그림은 그 조작과 화면 배치를 검토하는 예시다.
접촉면의 형상 변경·참조 복구 등 더 넓은 상태 계약은
[상세 화면 명세](pro-authored/SCREEN_SPEC.md)와
[접촉·파일 복구 계약](pro-authored/spec_sections/WORKFLOW_CONTRACTS.md)에 정의돼 있다.

## 질문에서 연구를 만들고 같은 결과로 토론 이어가기

1. Window → Expert에서 질문과 논점을 편집하고, 발언을 선택해 사용자 reply를 저장한다.
   Models…의 설정은 기존 OAuth/로컬 연결의 검토용 제안이며 실제 계정이나 호출을 활성화하지 않는다.
2. Plan… → Open editable Numerical plan에서 평가기와 Add variable…/Add response…를 지정한다.
   값·단위·범위와 목적·제약을 같은 계획 안에서 편집한다.
3. 방법과 해당 입력 표를 선택한다. 작성된 예시를 보려면 Example matrix를 명시적으로 불러온다.
   DOE 예시는 4개 설계점이므로 budget도 4 이상이어야 한다.
4. Save → Run study…로 Runner에 보낸 뒤 Review → Load retained result fixture를 선택한다.
   방법별 결과 표·곡선은 **작성된 합성 예시**이며 편집한 입력을 계산한 값이 아니다.
5. Open result에서 행을 선택하고 Discuss selection으로 원 토론에 돌아온다.
   Use as Study evidence…에서는 가설과 Support/Refute/Neutral을 직접 고른다.
6. 사용자 reply, Study 판단·이유·다음 연구를 작성하고 저장한다. 다시 열어 같은 선택 결과와
   근거 위치로 이어지는지 확인한다. 실제 provider가 없어도 이 로컬 작업은 가능하다.

## 다른 도구에서 바로 시작하기

| 도구 | 검토할 작업 |
|---|---|
| Data | 시험 자료의 열·단위·역할을 지정하고 표/곡선의 같은 구간을 선택한다. 품질 제외와 피팅 포함을 구별하고 저장한 관측을 Material에 전달한다. |
| Material | 시험·법칙·계수·하중 이력을 편집한다. 관측·예측·잔차·holdout을 비교하고 채택·저장·재열기를 따른다. 원문 복구는 Review의 saved Material repair scenario에서 본다. |
| PDE | Model Builder에서 영역·식·경계를 선택한다. 각 경계의 값을 독립 Apply/Reset하고 weak form 또는 ODE 정의와 시간 곡선을 편집한다. |
| Numerical | DOE·최적화·Inverse·Sobol·UQ·RBF·MOO·MDO의 입력과 결과를 구별한다. failed/제약 위반/미계산 결과를 정상 후보와 혼동하지 않는다. |
| Evaluation | Heat/Expand 단계와 온도장 전달·반복 조건을 편집하고 해당 정확한 단계를 연다. |
| Runner | Review의 running/failed/cancel/disconnect 상태를 불러온다. 취소 요청과 terminal 취소, 원 작업과 재시도를 구별한다. |
| Study | 경쟁 가설·지지/반박 근거를 비교하고 판단과 다음 연구를 직접 저장한다. |
| Report | Study의 Report… → Use Study → 절 포함·순서·본문 편집 → Page preview → PDF/Markdown Export preview… → Save·재열기를 따른다. Open source는 보이는 절의 정확한 결과·시각으로 돌아간다. |
| Acquisition | Data의 Acquisition…에서 채널·단위·교정·수집 수치와 기존 신호를 검토한다. Add/Edit dialog의 Cancel, 표/곡선 선택, Review → Connection loss example과 저장·재열기를 따른다. |
| Workbench | 필요할 때만 문서·포트 연결을 선택해 해당 독립 도구로 이동한다. |

Material을 다른 도구의 선행조건으로 두지 않는다. 자세한 조작은
[Pro 시제품 실행 안내](pro-ux/README.md)와 [새 화면 설계](pro-ux/DESIGN.md)에 있다.

보고서의 Use Study는 편집한 절을 교체하기 전에 확인하며 Cancel과 Undo로 원 작업을
유지한다. 없는 결과 시각은 다른 값으로 대신하지 않는다. 기본 출력은 누락 근거를 차단하고,
명시적인 unavailable placeholder 선택 시 누락을 표시한다. 너무 긴 PDF 내용은 해당 절을
고칠 수 있도록 출력을 막는다. 현재 Study의 판단과 역사적 F05 자료는 서로 다른 절이다.

Acquisition의 Connect/Start/Stop은 비활성화된 검토 상태다. 요청 NOT_SENT,
ACK NOT_RECEIVED, 물리 종료 UNKNOWN을 함께 보여 준다. 기존 trace는 새로 측정하거나
계획한 sample rate로 만든 데이터가 아니다. 실제 장비 연결은 제품 구현·검증 대상으로 남는다.

## 편집 원본과 개발자 자료

- [상태별 실제 화면 원본](pro-ux/screens/README.md): SVG, 같은 상태를 재현하는 JSON과 Qt 소스.
- [작업 흐름 원본](pro-ux/Workflows.drawio): 형상→해석→결과→채택, Expert→연구→Study, 자료·교정의 편집 도면.
- [전체 기능 명세](pro-authored/FUNCTION_SPEC.md), [상세 화면·상태 계약](pro-authored/SCREEN_SPEC.md).
- [요구 대응표](pro-authored/REQUIREMENT_COVERAGE.csv), [화면과 구현 작업 연결](pro-ux/implementation_map.csv).
- [기능별·최종 통합 검증 계획](pro-authored/VERIFICATION_PLAN.md), [MoAI 인계](pro-ux/MOAI_HANDOFF.md).
- [Codex 실제 확인·독립 검토](GUI_REVIEW.md), [무료 도구·라이선스](TOOLS_AND_LICENSES.md).

오래된 D1 Qt 폼은 보존한 참고 자료다. 화면 배치와 짧은 작업명은 이번 pro-ux 시안을 따른다.
실제 Windows OS 입력·DPI·native host 확인의 제한은 GUI_REVIEW에 명시한다.
사용자 검토는 개발 착수 판단이며 solver 검증·공학적 승인과는 별도다.
