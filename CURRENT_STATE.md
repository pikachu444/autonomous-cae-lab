# 현재 작업과 제품 상태

갱신: 2026-10-12. 이 파일이 현재 사실·맡긴 작업·다음 행동의 유일한 원본이다.
제품 목표는 [PRODUCT_PLAN](docs/PRODUCT_PLAN.md), 상세 기능은
[PRODUCT_UI_MCP_PLAN](docs/PRODUCT_UI_MCP_PLAN.md), 역할·갱신 규칙은
[CODEX_WORKFLOW](docs/CODEX_WORKFLOW.md)를 따른다.

## 현재 결정과 맡긴 작업

**최신 사용자 지시(2026-10-12): 상세 기획·GUI 설계와 별도 Qt 시제품을 먼저 완성해
검토에 제출한다. 제품 본구현은 사용자가 개발 시작을 지시한 뒤에 진행한다.**
아래의 앞선 문서 통합 완료와 다음 구현 방향은 재사용 근거이며 이번 설계의 완료 근거가
아니다. 이번 배정은 MoAI의 Codex 연결, 운영 지침의 충돌 정리, 전체 기능/구현 명세,
편집 가능한 작업/화면/상태 설계, 상호작용 시안, Qt 조작 확인, 실제 Pro 작성과 Astra
독립 검토다. Windows 로컬 Qt/PySide6·FreeCAD·ParaView를 유지하고 추가 지출은 0원이다.

현재 기준은 `9a6e3083037630b45694b812b135dc1cd63cf95a`, upstream은 아래 핀과 같다.
사용자 `.codex-remote-attachments/`는 보존한다. 제품 코드 변경과 solver/provider 계산은
시작하지 않았다. 기존 문서·시안은 설계 재료이고 새 상세 기획 수용은 **미완료**다.

연결 확인: MoAI `3.2.0-dev.2aab5f7`과 ChatGPT 인증 Codex CLI `0.146.1`을 확인했다.
초기 partial wiring에서 기존 설정을 보호한 selective Codex 연결을 추가했다.
MoAI CLI status의 wired와 실제 local stdio initialize/tools/list/`spec_progress`를 확인했다.
SPEC strict lint도 통과했다. 이후 current host에 MCP 도구 4개가 실제 노출됐고
`mcp__moai__spec_progress`를 호출해 draft SPEC을 읽었다. hook trust는 별도 미확인이다.
SPEC/read 도구 4개만 config에서 허용한다. 실제 skill catalog에는 MoAI 스킬5개가 나타났다.
기존 CLI0.146.1은 global `features.context_management` map을 boolean으로 읽다 실패한다.
global bytes를 보존했고 read-only `mcp get`에만 임시 false override를 써 등록을 확인했다.
사용자 Python 3.13에는 PySide6 `6.9.1`, Matplotlib, Qt Designer가 있다. 별도 설치된
Research runtime에는 PySide6가 없으므로 둘을 같은 환경으로 보고하지 않는다.

실제 Pro 상태: **D1 작성 완료 응답 회수 / ZIP 파일 미회수**. 이전 실제 세션의 Edge 확장 경로를 확인했고
사용자가 Edge를 연 뒤 연결됐다. 실제 Pro power5/5 UI 확인 후 새 요청
`PRO-DESKTOP-DESIGN-20261012-01`을 한 번 보내고 7개 원문 구간과 마지막 본문을 대조했다.
[실제 대화](https://chatgpt.com/c/6acca3ab-15b0-83ee-8ca3-25ff00e335c5), local 전달/응답 기록은
`runs/pro-relay/20261012-desktop-design/`이다. ZIP upload는 file-URL permission으로 실패해
**inline 실제 본문**(최신 사용자 원문·Pro 요청·source reuse·Astra·PROJECT_SCOPE·v2·ADR 기준)을
전달했다. Pro는 공개 pinned source 조회·전체 명세/화면/도면/별도 Qt 시제품을 작성해 D1 ZIP을
제출했다고 보고했다. 같은 요청의 실제 cloud 작업 완료와 final 응답을 공식 read_thread에서
회수해 local relay 폴더에 보존했다. 파일을 받거나 실행한 것으로 처리하지 않는다.
다른 모델/API로 대체하지 않았다.

Penpot은 로그인 화면까지 확인했으나 **계정이 없으니 탭을 닫고 무시하라는 최신 사용자
지시로 제외**했다. 계정 생성/유료 trial 없이 editable SVG/.drawio/.ui와 native Qt interaction을
사용한다. 새 Pro 원문 회수 뒤 이 변경을 명세에 반영하고 독립 Astra와 실제 산출물을 검토한다.
내장 브라우저 attach/Windows browser URL-policy 실패는 초기 연결 근거로만 보존한다.
현재 브라우저 연결은 복구됐으며 그 실패를 전체 작업 금지로 확대하지 않는다.

별도 [Qt 시제품](docs/design/20261012-desktop-planning/qt_prototype/README.md)의 Material
import/단위/구간/DEMO 비교/채택/save/cold-reopen에서 Astra가 재현한 P1/P2 8개를
bounded Sol/high가 교정했고 Astra가 관련 QTest·코드·캡처를 독립 재검토했다.
최종 표시 gate 교정도 읽기 전용으로 확인했다. Codex는 actual Windows CSV/저장 chooser,
표 선택/Shift 방향키·채택/Undo/Redo·dock Float/기본 배치 복구·종료 뒤 새 프로세스 재열기를
확인했다. [검토/실제 조작 기록](docs/design/20261012-desktop-planning/QT_REVIEW.md)에
최종 소스 해시와 최초 표시 불일치·교정 범위를 보존한다. native drag/Shift-click·여러 DPI·
접근성·제품서비스/physics·새 전체 Pro 설계 수용은 아직 미확인이다.
검토 자료 입구는 [새 설계 자료](docs/design/20261012-desktop-planning/README.md)다.

추가 환경 확인: 처음 Qt Designer 캡처는 Windows PIN 잠금 화면이라 입력을 중단했다.
사용자가 직접 잠금을 해제한 뒤 새 창 상태에서 Designer 원본·Qt 실제 조작을 확인했다.
보호된 인증 화면은 조작하지 않았다. draw.io Desktop32.4.1은 공식 portable
ZIP을 ignored `runs/tools`에 내려받아 path containment 확인 후 추출했다(추가 비용0).
실제 `.drawio` 열기/export는 Pro 원본 회수 뒤 확인한다.

모델 실행 기록: Astra `gpt-6-astra/xhigh`, 조사 `gpt-6-luna/high`, Qt spike `gpt-6.1-sol/high`를
확인했다. 주 Codex의 앞선 실행 기록은 project/global Sol/xhigh 설정과 달리 **Sol/high**였다.
사용자가 활성 추론 수준을 바꿨다고 답했다. 변경 전 기록을 xhigh로 소급 표시하지 않는다.
init/merge 단계에서 global 보호 해시는 유지됐고 이후 외부 변경으로 global hash가 달라졌다.
사용자/host 변경을 되돌리지 않는다.

관련 Space의 [제품 입구](https://chatgpt.com/space/page_6ac6e5e8d7688191a58c5760fda2d2d9)에
최신 기획 우선·개발 시작 지시 관문·Penpot 제외와 Git/Pro 링크를 반영했고 본문 재조회에서
나머지 블록/첨부 보존을 확인했다. Git–Space 자동 동기화가 아니다.
기존 PRODUCT_PLAN의 없는 owner/창 분류와 상세 v2의 작성 당시 T표를 현재 소스 재사용
기준에 맞춰 정리했다. Qt 교정·native 조작 기록은 `963ccf75474b3589f8fde804743171e9a9c444c1`로
게시했고 원격 main의 같은 SHA를 확인했다. 별도 Codex [소유권·상태 도면](docs/design/20261012-desktop-planning/ownership-and-gates.drawio)은
draw.io Desktop32.4.1에서 열기·페이지 전환·SVG 두 페이지 export를 확인했다. 이는 Pro의
전체 작업 도면을 대신하지 않는다.

현재 회수 장애: Pro 작업은 completed지만 새 브라우저 탭은 '이 대화를 불러올 수 없습니다',
원 탭은 debugger unattached다. 공식 followup 도구는 active compatible turn이 필요하다며
후속 전달을 거절했다. 준비한 `PRO-DESKTOP-DESIGN-20261012-02`는 **미전송**이다.
documented browser API 복구 시도 뒤 native Browser 접근성 경로에서도 Windows URL을
정책 판정에 충분히 확인하지 못해 Computer Use가 **현재 턴의 입력을 중단**했다.
정책을 우회하거나 새 paid/provider 호출로 대체하지 않는다. 아직 ZIP을 회수하지 않았고
새 전체 명세·상호작용 시안의 완료를 선언하지 않는다. 다음은 실제 Pro 산출물 회수→
최신 Penpot 제외 반영→전체 Astra 독립 검토→도면/Qt 실제 열람·교정→사용자 검토 제출이다.

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
