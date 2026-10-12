# 현재 작업과 제품 상태

갱신: 2026-10-12. 이 파일이 현재 사실·맡긴 작업·다음 행동의 유일한 원본이다.
제품 목표는 [PRODUCT_PLAN](docs/PRODUCT_PLAN.md), 상세 기능은
[PRODUCT_UI_MCP_PLAN](docs/PRODUCT_UI_MCP_PLAN.md), 역할·갱신 규칙은
[CODEX_WORKFLOW](docs/CODEX_WORKFLOW.md)를 따른다.

## 현재 결정과 맡긴 작업

**상세 기획·GUI 설계와 별도 Qt 시제품을 먼저 완성해 사용자 검토에 제출한다.
제품 본구현은 이후 사용자가 개발 시작을 지시한 뒤 진행한다.** 전체 배정은 운영 지침의
충돌 정리, 전체 개발 명세·작업 목록, 편집 가능한 작업/화면/상태 설계와 상호작용 시안,
Qt 조작 확인, 실제 Pro 작성과 Astra 독립 검토다. Windows 로컬 Qt/PySide6·FreeCAD·
ParaView와 추가 지출0원을 유지한다. 과거 문서의 기획 완료·다음 구현은 이번 수용 근거가 아니다.

최근 사용자 지시는 CAD/전처리→solver/Runner→native Post→최적화와 Co-STORM 연구의
독립 작업·도구 연결을 중심으로 완성하는 것이다. Material 예시를 전체 우선순위로 확대하지
않으며 그 교정이 다른 도구를 기다리게 하지 않는다. Data/Material/PDE/Numerical/Runner/
Expert/Study·선택 Workbench와 넓은 물리·수치 범위는 그대로 유지한다.

현재 설명문·보조 기능이 많은 Qt 폼은 **사용성 미수용 초안**이다. 사용자는 긴 제목·파일명에
`• r2` 등 내부 접미사를 이어 붙이는 표시를 싫어한다. 주 화면은 짧은 작업명·값·단위·선택·
상태·다음 조작을 보여주고, 정확한 원본/개정/실패는 이력·근거·진단에서 조회한다.
이미 지정한 FreeCAD/ParaView/HyperStudy/Co-STORM/Origin/MCalibration/COMSOL 원형은
[PRODUCT_PLAN §3](docs/PRODUCT_PLAN.md#3-화면마다-주-기준을-고정한다)을 따른다.
참고 이미지를 사용자에게 요청하지 않는다. 세부 화면 시안은 검토용 제안이며 사용자 결정과 구별한다.

기준 제품 source는 `9a6e3083037630b45694b812b135dc1cd63cf95a`, upstream은 아래 핀이다.
제품 코드·solver/provider 실행은 이번 배정에서 시작하지 않았다. 사용자
`.codex-remote-attachments/`와 기존 설정·AGENTS를 보존한다.

### 실제 Pro 원고와 검토

초기 실제 Edge UI에서 Pro power5/5를 확인하고 요청01의 원문7개를 inline으로 전달했다.
ZIP 첨부는 실패했으므로 첨부 성공으로 표시하지 않는다.
[원 D1 대화](https://chatgpt.com/c/6acca3ab-15b0-83ee-8ca3-25ff00e335c5)의 완료 응답을
회수했고, 사용자 지시에 따라 같은 작성 task에 공식 도구로 요청03을 전달해
별도 `design/pro-desktop-d1-20261012` 브랜치에서 D1 핵심 파일을 회수했다.
로컬 원고는 [pro-authored](docs/design/20261012-desktop-planning/pro-authored/README.md),
개발 명세·작업표·화면/원요구 대응·검증 계획은 [검토 입구](docs/design/20261012-desktop-planning/README.md)에 있다.
전체 SVG/JSON/.drawio·ZIP의 추가 회수와 교정 수용은 미완료다. 원고의 제출·검사 주장과 실제 수용을 구별한다.

[D1 실제 검토](docs/design/20261012-desktop-planning/D1_REVIEW.md): Astra/xhigh는
MOO 채택 완료, SI stage 재열기, Material 참조 복구, 교정 원문 이동의4개 경로 결함을
확인했다. Sol/high는 dirty Data의 실행 입력 누락, 구간 선택/곡선·mask 불일치,
Tab 편집기 갇힘을 QTest로 재현했다. 원14개 상태 검사는 통과했으나 위 경로가 실패하므로
전체 시제품 수용으로 처리하지 않는다. 기능·화면·Qt 교정을 원 Pro task에 전달했다.
재현 자료는 `runs/pro-relay/20261012-desktop-design/pro-qt-review/`에 있다.

최신 사용자 GUI/우선순위 지시를 반영한 요청06을
[새 실제 Pro 대화](https://chatgpt.com/c/6accef3a-e650-83ee-89e2-3f48a60dd17a)에 전송했다.
실제 UI의 Pro/GPT-6·power5/5, 요청ID·최신 문구·전체 도구 범위·끝 경계를 확인했고
Pro가 공개 원본 조회와 전체 Qt 시안 작성을 시작한 응답을 읽었다.
[위임 요약](docs/design/20261012-desktop-planning/PRO_UX_REQUEST.md)과 실제 보낸 본문을 구별한다.
작성 소유권은 `pro-ux/`, 별도 `design/product-ux-20261012` 브랜치로 원 D1 작업과 분리했다.
이 브랜치 생성은 확인했으나 아직 새 화면/코드를 받은 것은 아니다.
이후 초기 상태 소스 커밋이 게시된 것은 확인했다. 전체 Qt 화면은 아직 회수 전이다.
사용자의 ‘metadata와 유지 절차가 중심이 아니다’라는 최신 지시를 같은 Pro UI에
`UX-STEER-01`로 보내 실제 사용자 메시지에 나타난 것을 확인했다. 형상·해석 조건·계산·
결과 분석·최적화·Co-STORM의 실제 기능을 화면과 조작의 중심으로 한다.

### 도구와 실제 확인 범위

MoAI `3.2.0-dev.2aab5f7`의 공식 Codex 초기화를 분리해 확인한 뒤 필요한 설정만 병합했다.
실제 skill catalog의 MoAI5개, local stdio initialize/tools와 현재 host MCP4개를 확인했고
이번 재개에서도 `spec_progress`로 draft SPEC을 조회했다. [MoAI SPEC](.moai/specs/SPEC-DESKTOP-001/spec.md)은
기능·화면·작업표·수용 조건에 연결하며 현재 큐를 중복하지 않는다. strict lint는 구조 검사이며
사용성 통과가 아니다. hook trust는 미확인이다. CLI0.146.1의 기존 global context_management
map 호환 오류는 read-only 검사에만 임시 override를 사용했고 사용자 설정을 덮어쓰지 않았다.

기존 사용자 Python3.13에는 PySide6 6.9.1·Matplotlib3.10.1·Designer와 Qt SVG가 있다.
별도 Research runtime에는 PySide6가 없다. 새 D1 Qt 프로세스/접근성 구조는 확인했지만
창 활성화 실패와 검은 캡처 때문에 native 입력을 중단했다. Segoe UI offscreen 렌더링·
QTest의 범위만 기록한다. 이전 [Qt spike 검토](docs/design/20261012-desktop-planning/QT_REVIEW.md)의
CSV/저장 chooser·선택·채택·Undo/Redo·dock Float·새 프로세스 재열기 근거가 새 D1을 대신하지 않는다.
FreeCAD/ParaView exe는 Program Files·사용자 AutonomousCAELab·현재 runs/tools에서 찾지 못했다.
이 검색 범위의 미발견을 설치 부재로 확대하지 않는다. 이전 버전/실행 기록을 새 실행으로 표시하지 않는다.

draw.io Desktop32.4.1의 기존 portable 무료 도구로 Codex의 소유권·상태 도면을 열기/export했다.
Pro 계약에서 작성한 [전체 연결 원본](docs/design/20261012-desktop-planning/research.drawio)은
CAD/FE 준비·실행/Post·최적화/채택·Co-STORM/Study 경로를 연결하며 CLI export/렌더링을 확인했다.
프로그램 화면 또는 solver 실행의 대체물이 아니다. Desktop 해당 버전 라이선스는 GPLv3로 교정했다.
Penpot은 계정이 없어 제외하라는 사용자 결정으로 닫고 무시하며 계정·편집·export를 완료 gate로 두지 않는다.
[무료 도구 기록](docs/design/20261012-desktop-planning/TOOLS_AND_LICENSES.md)을 따른다.

주 Codex는 사용자 변경 이후 실제 실행 기록에서 Sol/xhigh를 확인했다. 변경 전 Sol/high
기록을 소급 변경하지 않는다. 핵심 독립 검토 Astra/xhigh, bounded 코드 Sol/high,
코드 조사 Luna/high를 사용했다. 실제 Pro UI 설정과 Codex의 추론 수준은 별개다.
브라우저의 기존 대화 회수 장애를 공식 파일/저장소 작업 전체의 금지로 확대하지 않는다.
수동 다운로드 요청은 공식 회수 경로가 동작한 뒤 철회했고 추가 사용자 조작을 기다리지 않는다.

### 이어서 할 작업

Pro의 전체 도구 화면·Qt 소스와 원 D1 편집 원본을 회수하고 실제로 열어, 위 결함과 사용자
피드백의 교정을 확인한다. Astra에 최신 원문·같은 실제 산출물을 전달해 시각·hotspot·
전체 경로를 독립 검토하고 필요한 Pro 교정을 반영한다. 사용자가 시작·선택·입력·결과·
오류/취소·저장/재개를 직접 따라갈 수 있는 검토본으로 제출한 뒤 개발 시작 지시를 기다린다.
CURRENT_STATE/HANDOFF·요구 상태와 관련 Space 입구는 실제 진행에 맞게 갱신한다.
현재 전체 상세 기획·사용성 수용은 미완료이며 과거 수치 실패·UNKNOWN은 그대로 유지한다.

### 앞선 통합 기록

사용자는 Codex와 실제 ChatGPT Pro가 문서 정리와 작업 방식을 토론해 **확정하고 반영**하도록
지시했다. 제안·상태 보고만 반복하거나 일상 반영을 위해 다시 승인을 기다리는 단계가 아니다.
맡긴 현행 문서/진입점 정리, Pro/Codex 책임 확정, Space 안내와 Git 기준 연결은 **완료**했다.
문서 통합 커밋 `6b0c2ed14f9d61204cabfe3c47288f2438202798`을 원격 main에 게시하고
같은 SHA를 확인했다. 관련 Space 6개 Page의 갱신·본문 재조회·기존 첨부 보존도 확인했다.
앞선 통합에 남은 문서 승인이나 제안 확정 단계는 없다. 아래 제품 방향의 본구현은
최신 사용자 지시에 따라 이번 상세 기획 검토와 개발 시작 지시를 기다린다.

다음 제품 작업은 아래 **독립 도구군의 실제 작업 완성**으로 확정한다. 특정 C3D10 메시나
F05 진단을 전체 제품 개발의 우선 과제 또는 선행조건으로 두지 않는다. 제품 구현 자체를
완료로 선언하거나 원래 수치·물리 요구를 없애는 결정은 아니다. 이번 문서 정리 중 새 제품
구현·native 계산·provider 실행은 시작하지 않았다.

## 기준 버전과 근거

- 검토한 기준: `b3fa9188490ea42399974ae07c10e83521f14d1d` (문서 정리 전 main).
- 제품 통합: [PR #7](https://github.com/pikachu444/autonomous-cae-lab/pull/7),
  merge `92a51fd7967ba1127b5a56755ebef6a46f41f04e`. 사용자는 알려진 F05 실패를
  이 개발 통합에 대해 수용했다. 병합 전 진단을 다시 선행조건으로 되살리지 않는다.
- 실제 확인한 CI: source `385818bab785bfbf2c1e5880371970e475c90d68`,
  [run 38159523618](https://github.com/pikachu444/autonomous-cae-lab/actions/runs/38159523618),
  9 jobs pass / Code_Aster failure. 원 측정과 제한은
  [정확한 실행 기록](benchmarks/records/20261012-stabilization-s5-ci-native-continuation.json)에 있다.
  뒤의 문서 커밋과 병합은 새 solver 검증이 아니다.
- pinned upstream: `3e48bf6138f495299f45b1af254bfb4aaff307b8`.
- 아래 현황은 해당 코드와 기존 실행 기록을 대조한 것이다. 이번 문서 정리에서 새 GUI·
  solver·실제 AI 계산을 실행한 것으로 읽지 않는다.

## 전체 제품 현황

전체 구성은 FreeCAD CAD/FE, ParaView Post, 독립 Research 도구와 선택 Workbench로
정해져 있다. 상당한 구현과 부분 실행 근거가 있으나 전체 제품·사용성·배포는 미완료다.
구성·기존 구현을 재사용하되 최신 요청의 상세 화면·사용성 기획은 다시 검토한다.

| 영역 | 현재 구현/근거 | 남은 주요 제품 작업 |
|---|---|---|
| CAD/FE Pre | native 치수·Assembly·FEM 명령, 관리형 저장, 지원 계산 제출, 결과/원 설계 이동 | 실제 사용자 모델의 편집·선택·오류 복구·저장/재개를 포함한 전체 화면 작업. 넓은 접촉·비선형 지원은 별도 범위 |
| Post | 외부 결과 열기, 필터·측정·지원 비교, Apply/Undo, 원자료 수리, 부분 저장·재열기. 실제 ParaView의 제한된 실행 근거 | 실제 화면에서 대상·필드·위치·시간을 다루는 작업, 지원 비교 범위와 도구 이동 |
| Data | CSV/NPZ, 채널·축·단위·매핑·구간/mask, 보존 응답 비교, 실제 HTTP/Qt 저장·재시작 | 표·그래프 연동 선택, 처리 정의 편집과 큰 자료의 조작성 |
| Material | FELUPE 및 일부 MFront 법칙, 계수·이력, 평가·보존 응답·Plan/채택 연결 | 법칙·시험·관측·계수·상태 연구의 화면과 범용 protocol/FE 연결. 대역 UI 검사는 실제 native 물리 수용과 구별 |
| PDE | 선언된 모델의 편집·지원 검사·평가·보존 결과와 Post/Plan 이동 | 식·영역·조건·결과의 편집 깊이와 일반 ODE/약형식·solver 설정 등 지원 범위 |
| Numerical / Evaluation | Material/범용 Request Plan, 변수·응답·방법·후보·채택, 단계/전달/반복 정의와 일부 실제 수치/연성 실행 | 내부 key/value 중심 편집 개선, 방법별 의미·결과 해석, 지원 조합·재개 범위 |
| Runner | 실제 job 입력·상태·진단·취소·결과와 원 문서/Post/Study 이동 | 실제 배포 환경의 실패·취소·재접속·장시간 실행과 도구 이동 |
| Expert | 역할·논점·reply·개입·pause/resume·근거·Plan, 실제 provider/callback 기반. 이전 웹 화면의 실제 연구 왕복 기록 | 새 독립 Qt 화면의 자료/모델 설정부터 실제 대화→계획→계산→결과 후속 논의까지 연결·확인 |
| Study / 선택 Workbench | 질문·가설·근거·판단과 참조/도구 이동 | 별도로 계획한 문서·연결 그래프, 개정·변경 영향 화면. 기존 서비스 이름은 이 UI의 완성 근거가 아님 |
| 공통 GUI/CLI/Python/MCP | 같은 HTTP 서비스·문서 owner·명령·결과, native 명령 경로 | 실제 열린 native GUI와의 교차 작업, 지원 기능 노출과 클라이언트 사용 |
| 설치/독립 실행 | Windows private runtime, 서비스 재사용, 도구별 실행 helper | 기본 시작이 옛 웹 Workbench로 향함. 도구별 직접 진입·파일 열기·종료 후 재실행을 제품 구성에 맞춰 완성 |

코드 위치는 `apps/desktop_pre`, `apps/desktop_post`, `apps/research`,
`caelab/workbench*`, `caelab/adapters`, `scripts/start_cae_research.ps1` 및 기존
설치/실행 스크립트다. [실행 기록](docs/WORKBENCH_PROGRESS.md)의 S1/S2와 후속 교정에서
이미 고친 Pre/Post Save, 초안, 선택·응답 읽기 결함을 새 미해결 과제로 복사하지 않는다.

## 승인 후 이어갈 제품 구현 방향

**목표:** 사용자가 원하는 독립 도구에서 자기 자료·모델을 열고 주요 편집과 필요한 계산을
수행하며, 같은 개정·결과를 다른 도구에서 이어 보고, 저장·종료 후 다시 연구를 계속한다.
제품 작성자는 Pro, 독립 검토·환경 확인·통합은 Codex가 맡는다.

진행할 범위:

1. 기존 실행 helper를 제품 진입에 연결한다. 도구·문서 선택, 올바른 창 열기, 서비스
   시작/재접속, 저장 후 새 프로세스 재열기를 완성한다. 계산 backend가 없어도 독립적인
   자료·문서·기존 결과 읽기는 계속 가능해야 한다.
2. Data·Material·PDE·Numerical의 주요 편집을 각 작업의 표·곡선·모델·변수/응답 중심으로
   보완하고, 기존 Pre/Post native 작업과 Runner를 연결한다. 내부 JSON/key를 사용자가
   알아야만 대표 작업을 끝낼 수 있는 부분을 남기지 않는다.
3. Expert에서 자료·모델·역할을 고르고 실제 대화와 개입을 진행한다. 제안된 Plan을
   사용자가 편집해 실행하고 실제 결과를 읽어 후속 논의를 이어간다. 이전 provider와
   공통 도구 구현을 재사용한다. 새 단독 화면의 실제 전체 흐름은 별도로 확인한다.

독립된 도구 보완은 병행할 수 있다. 모든 backend 설치, 선택 Workbench 그래프,
전체 원요구 재감사, C3D10 비교 수정이 다른 도구의 착수를 막는 전제는 아니다.
범용 구성식·PDE·연성·접촉·외부 solver 등의 확장은 제품 범위에 계속 남긴다. 이번
작업의 지원 범위를 명시하면서 확장하며, 첫 연결의 완료를 전체 물리 범위 완료로 바꾸지 않는다.

사용자 관점의 완료 기준:

- 원하는 도구로 직접 들어가 자기 파일/문서를 열고 대상과 관련 설정을 실제로 편집한다.
- 지원 입력은 실제 평가/계산과 결과로 이어지고, invalid 입력은 고칠 위치를 알려 주며 실행을 막는다.
- 다른 도구로 이동해도 같은 문서·개정·선택 결과를 사용한다. 과거 결과는 바뀐 입력과 구별해 남는다.
- 저장·닫기·새 프로세스 재열기 후 편집 내용, 결과와 연구 맥락이 이어진다. 누락 파일·실패·취소는 복구 가능하게 설명한다.
- Expert는 실제 provider와 도구 결과에 근거해 논의한다. 대역 답변·고정 숫자·옛 웹 검증으로 새 화면의 완료를 대신하지 않는다.
- 설치 후 시작/재실행 안내가 실제 동작과 맞고, GUI·CLI·Python·선택 MCP의 지원 범위가 일치한다.

Pro에게는 이 절과 제품 계획·관련 코드의 동일 기준 버전, 미반영 사용자 결정·산출물,
실제 확인 범위를 함께 전달한다. 이번에는 전체 기능과 화면/상태에 연결한 개발 명세와
구현 작업표를 보완한다. 기본 문서 소유와 native 재사용 경계를 임의로 교체하지 않는다.

## 문서와 새 세션 운영

현행 계획·상태·협업은 Git, 사용자 결정·이유·원자료는
[Space](https://chatgpt.com/space/page_6ac6e5e8d7688191a58c5760fda2d2d9)에서 보존한다.
Codex가 의미 있는 변경의 관련 Page 요약/링크까지 맞춘다. 자동 동기화는 없다.
최신 사용자 결정은 Git 반영 전에도 유효하다. Pro와 Codex는 각각 새 세션에서 같은
기준 자료로 작업하며 [시작문](CODEX_START.txt)과 [운영 규칙](docs/CODEX_WORKFLOW.md)을 쓴다.

현재 미반영 제품 코드 산출물은 없다. 앞선 Pro 대화는 문서·우선순위 결정이며 새 구현이
아니다. [실제 Pro 협의](https://chatgpt.com/c/6acc2538-ed3c-83ee-8e6b-6b98c52ea109)를 출처로 남긴다.
기존 `.codex-remote-attachments/`는 사용자 로컬 untracked 자료로 보존한다.
새 세션은 현재 프로세스·설치·인증·ignored 산출물의 존재를 다시 확인하며 가정하지 않는다.

문서 반영 확인(2026-10-12): 원래 52개 ID/설명 일치, 보존본 3개의 Git 저장 바이트와
SHA256 일치, 새 로컬 문서 링크, `git diff --check`를 확인했다. 제품 코드는 바꾸지 않았다.
Page 저장본은 [제품 입구](https://chatgpt.com/space/page_6ac6e5e8d7688191a58c5760fda2d2d9) 13,
[제품 설계·원문](https://chatgpt.com/space/page_d99abd5a046c8191b16263e448c8d8ee) 19,
[결정 기록](https://chatgpt.com/space/page_6ac6e6a501508191913070f4ef51eae9) 7,
[이전 상세기획](https://chatgpt.com/space/page_6ac6e67d6efc8191af147db299b3cf3b) 13,
[검토 원자료](https://chatgpt.com/space/page_6ac79c9b17c48191a63e2775c75fa1d2) 5,
[화면 도면](https://chatgpt.com/space/page_e314876e22bc8191b562de881de7f3b6) 24다.
수정 대상 외 본문과 첨부 참조를 보존했다. 확인 범위는 저장본문과 참조이며 앱 미리보기
요청은 응답하지 않아 렌더링 검토를 추가로 주장하지 않는다.

## 남겨 두는 수치·공학 한계와 기록

F05 원 측정 `3.32295e-6 > 1e-6`과 별도 실패한 AMD 시도는 그대로 남는다. 해당 실패를
이번 문서 정리나 PR 병합으로 통과시키지 않는다. 알려진 실패는 필요한 후속 수치 작업에서
다루며 전체 앱 구성의 선행조건으로 재시작하지 않는다. 물리·재료·강도·내구·회사 배포
승인은 별도이며 UNKNOWN/NOT_RELEASED를 유지한다.

이전 상세 상태/인계는 [보존 원문](docs/history/20261012-before-consolidation/README.md),
실제 실행은 [WORKBENCH_PROGRESS](docs/WORKBENCH_PROGRESS.md),
[PREPOST_VERIFICATION](docs/PREPOST_VERIFICATION.md), `benchmarks/records/`에서 찾는다.
원시 CI ZIP/로컬 runs는 Git clone에 포함되지 않으며 보존 기한과 위치는 해당 기록에 있다.
