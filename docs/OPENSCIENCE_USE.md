# OpenScience 사용 방식과 로컬 실행

OpenScience는 연구 목표·가설을 정리하고 CAD·메시·솔버·수치 탐색 도구를 호출한 뒤,
같은 실험 기록을 비교·해석해 다음 연구 조건을 제안하는 역할을 맡는다. 수치 후보는
수치 엔진이 생성하고 실행·근거·판정은 Core가 기록한다. 현재 검증은 이 도구들이
실제 연구 흐름 안에서 정확한 기록을 돌려주는지 확인하는 과정이다. 자유로운 연구
계획 전체의 자율 완수는 아직 UNKNOWN이다.

이번 새 지붕 연구는 정해진 질문3개와 실제 도구16건을 마쳤다. 승인한 GPT-5.6 Sol이
연구를 등록하고 두 솔버를 요청한 뒤, 새 절반 하중 결과를 비교하고 전체 기록을
해석했다. 전체 하중 계산은 반복하지 않았다. 수치 계산과 원시 결과 검토는 Core·
솔버 및 독립 검토가 맡았고, AI가 강도나 최종 승인을 결정하지 않았다.

CalculiX의 기준값·메시·반하중 수치 검증은 통과했지만 Code_Aster는 CPU 제한으로
실패했다. 마지막 AI 설명에는 반하중 비교식의 분모 오류1건이 남았다. 원문을
보존하고 정확한 식·단위를 명시한 추가 해석으로 보완한다. 전체 결과는 부분 성공이며,
이번 화면 확인과 자유로운 연구 계획의 자율 완수는 UNKNOWN이다.
근거: [새 지붕 실제 연구](../benchmarks/records/20261002-openscience-roof-refinement-research.json).

### 이전 체크포인트: 첫 질문 완료, 후속 질문 대기

이번 새 지붕 연구에서는 승인 모델이 질문·가설을 등록하고 두 솔버를 직접 요청한
첫 질문과9개 도구 호출을 마쳤다. CalculiX의1.2449% 기준값 오차·0.1052% 메시
변화는 원래 기준 안에 들었고, Code_Aster의 실패는 사용할 수 있는 결과로
바꾸지 않았다. 보조 검증이 동일한 시각의 UTC 문자열과 한국 시간 객체를 다르게
비교해 후속 질문 전 멈췄다. 원본을 보존하고 해당 비교를 고친 뒤 아직 실행하지
않은 절반 하중·종합 해석을 이어간다. 별도의 직접 Core 실행3건은 독립 원시 결과
검토를 마쳤다. 이 기록을 전체 연구 완료로 해석하지 않는다.
근거: [새 지붕 native 실행](../benchmarks/records/20261002-roof-refinement-native.json).

2026-10-02 현재: 공식 OpenScience2.0.146과 승인한 GPT-5.6 Sol의 로그인은
완료돼 있다. 연구자는 공식 프로젝트의 대화창에 연구 목표와 조건을 전달한다.
AI가 필요한 조건을 확인하고, 허용된 Core 도구로 실행·비교한 기록을 해석한다.
수치 탐색 후보는 기존 numerical engine이 만든다. 긴 문서 양식을 모두 채우는
방식이 필수인 것은 아니다. AI의 계획 문장과 실제 도구·실험 기록은 구분한다.

공식 OpenScience도 자연어 목표를 받아 계획·자료 조사·코드와 실험 실행·결과
정리를 수행하는 연구 도구로 설명한다([현재 사용 버전의 공식 설명](https://github.com/synthetic-sciences/openscience/blob/4082a2ecb73e166d4503963798228ba700f3840f/README.md#what-it-is)).
우리 시스템에서는 이 연구 과정이 CAD·메시·솔버·수치 탐색 도구와 공통 실험
기록으로 이어지게 구성한다. 솔버 검증은 계산 도구의 신뢰성을 확인하는 단계다.

실제 확인한 P1.3 범위는 clean04ff148의8 연구 단계/41 도구 영수증/23 실험이다.
폭38/40 CAD·CalculiX 비교, SciPy의9 후보 탐색, 스칼라 FEniCSx 계산과 AI 해석,
같은 기록의 화면·종료·보존을 확인했다. 탐색은1세대 MAX_GENERATIONS이며
최적점 수렴이나 전체 시스템·강도 승인을 뜻하지 않는다. 근거:
[P1 실제 연구 기록](../benchmarks/records/20261001-openscience-research-04ff148.json).

연구06은 main에 반영한94773a3의 깨끗한 소스·새 저장소에서 질문9개와 도구44건,
실험9건, 마지막 종합 해석을 마쳤다. 전체360998바이트 입력도 공식 표준 입력으로
전달했고, OpenScience에 저장된 원래 질문이 줄바꿈+전체 원문과 정확히 일치했다.
같은 승인 모델·프로젝트를 유지했고 화면의 같은 연구·결과·해석 텍스트를 확인했다.
실행 종료,1094개 원본·보조 파일의 동일한 보존과 새 실행의 독립 검토도 마쳤다.
근거: [실제 연구06](../benchmarks/records/20261002-openscience-structural-research06.json).

연결 흐름이 끝났다는 뜻이며 수치 검증 전체의 성공은 아니다. 실린더의 해석식·전체
변위·응력·솔버 비교와 빔·실린더의 하중 절반 비례성은 통과했다. 빔 Code_Aster의
실패와 지붕의1% 메시 수렴 기준 초과는 남았고 지붕의 수치는 무효로 유지한다.
AI가 마지막 설명에서 완료된 원시 결과 개수를 한 곳에서7개로 쓴 오류도 보존했다.
실제 파일은 완료8개×3레벨+실패한 빔2레벨=26레벨이며, 원본 검사로 확인한다.
AI가 하중 절반 오차의 분모를 다르게 쓴 문장도 고정된 검증식과 구분해 기록했다.
AI 답변을 수치 검증이나 강도 승인으로 대신하지 않는다. 전체 상태는
FAILED_OR_PARTIAL/NOT_RELEASED이며 자유로운 연구 계획의 자율 완수는 아직 미검증이다.
같은 소스의 CI는 소스 검사127개 통과, 전체8개 성공·2개 실패다. 먼저 같은
P2.2에서 Fz 정확도와 지붕 메시 수렴을 해결한다. 아래 연구05와
[06 시작 기록](../benchmarks/records/20261002-openscience-structural-research06-start.json)은 이전 시점의 보존 결과다.

현재 P2.2에서는 AI가 세 구조 문제의 두 솔버를 실행하고 하중을 바꾼
새 실험을 만들며 결과를 비교·해석한다. 실제 연구05는 질문8개와 도구45건,
실험9건을 남겼다. 독립 검토에서 실린더의 해석식·전체 변위·응력·두 솔버 비교와
빔·실린더의 하중 절반에 대한 비례성을 확인했다. 빔 Aster의 계산 실패와 지붕의
메시 수렴 기준 초과는 성공으로 바꾸지 않았고, 지붕의 결과 수치는 무효로 유지한다.

이 실행은 주 세션이 미리 정한 질문 순서에서 AI가 도구와 실행 순서를 선택하고
해석한 범위다. 자유로운 연구 계획과 캠페인 전체의 자율 완수는 아직 미검증이다.
마지막 종합 해석은 큰 입력을 실행 인자로 전달하지 못해 끝나지 않았다. 전체
연구05는 FAILED_OR_PARTIAL이며, 서버 종료와1071개 원본 파일의 동일한 보존,
독립 검토를 마쳤다. 공식 화면에서 같은 지붕 연구·결과·AI 해석의 텍스트도 확인했다.
근거: [실제 연구05](../benchmarks/records/20261002-openscience-structural-research05.json).

전체 입력을 공식 OpenScience의 표준 입력으로 전달하는 수정은 로컬 검사80개,
기존 소스 검사127개·인증 경로 모의 검사63개와 독립 검토를 통과했다. 질문이나
실험 결과를 줄이지 않았고, 공식 CLI가 입력 앞에 추가하는 줄바꿈은 별도로 기록한다.
이 검사는 실제 새 연구의 성공을 뜻하지 않는다. 수정본을 반영한 새 연구06에서
같은 승인 모델·프로젝트·질문 순서로 마지막 해석까지 확인한다. 수치 기준은 유지한다.
수정 근거: [전체 연구 입력 전달](../benchmarks/records/20261002-research-prompt-transport.json),
[P2 연결 상태](STRUCTURAL_FAMILIES_ACCEPTANCE.md).

실행05의 고정 소스9d62273은 main에 반영했고, 그 소스의 CI는 검사127개를
통과했지만 전체8개 성공·2개 실패다. OpenRadioss 다운로드와 Aster Fz의 실패는
남아 있다. 새로운 수정본의 CI와 실제 연구06은 별도로 확인해야 한다. 과거
[05 시작 기록](../benchmarks/records/20261002-openscience-structural-research05-start.json)의
질문4개·도구17건·결과3건은00:09Z 당시의 보존 기록이다. 종료한4098 화면은
현재 실행 증거가 아니다.

`127.0.0.1:4098`은 공식 OpenScience이고, `127.0.0.1:8766`은 이 저장소의
별도 CAE Lab 결과 화면이다. 후자는 같은 Core store의 실제 원본·근거를 읽으며
OpenScience 제품 화면을 대신하지 않는다. 공식 프로젝트와 CAE 소스 폴더의 연결은
이미 구성했다. 서버·대화는 공식 프로젝트에, MCP·실험은 지정한 CAE 소스와 새
store에 묶인다. 대화의 연구 질문, 실제 도구 호출과 AI 답변을 같은 session에서
확인한다. 현재 소유 실행의 경로·모델·인증을 임의로 바꾸지 않는다.
근거: `benchmarks/records/20261001-openscience-native-research.json`.

아래 날짜별 설명과 Ollama 예시는 과거 경로의 기록이다. 현재 사용자 선택은
`openai-codex/gpt-5.6-sol`이며 자동 대체 모델을 실행하지 않는다.

2026-09-30. 사용법 설명을 화면 재설계 지시로 해석하지 않는다.

아래는 2026-10-01 로그인 완료 전의 연결 기록이다. Qwen 자동 선택을 제거했다. 공식 OpenScience2.0.146은
ChatGPT 로그인(`keys signin`, provider `openai-codex`)을 지원하며,
`scripts/openscience-chatgpt.ps1`이 저장소 밖의 별도 인증 프로필을 준비한다.
사용자는 본인 계정 로그인·동의만 수행한다. 주 세션이 설정·실행·검증을 담당한다.
첫 로그인은 완료되지 않았고 실제 모델 응답과 연구 transport는 아직 검증 전이다.
로그인 성공이나 모델 목록을 연구 완료로 취급하지 않는다. 모델은 명시적으로 선택하며
다른 모델이나 유료 API로 자동 전환하지 않는다. 아래 Ollama 실행 예는 과거 경로다.

## 어떤 화면을 쓰는가

Autonomous CAE Lab의 로컬 화면(현재 127.0.0.1:8766)은 사람이 연구·CAD·해석·결과
기록을 직접 확인하는 화면이다. 공식 OpenScience 대화 workspace는 별도 서버에서 열린다.
공식 workspace에서는 프로젝트와 모델을 선택하고, 대화창에 연구 목표와 조건을 전달한다.
등록된 CAE Lab MCP 도구의 실제 호출과 결과를 보면서 후속 대화를 이어간다.

이 컴퓨터에서는 공식 2.0.146의 일반 serve 경로에서 저장된 거부 CAD 도구 기록과
실제 AI 해석 문장을 브라우저로 확인했다. 주 세션이 보존한 근거는
기존 main의 ignored artifacts/local-20260930-openscience-live-05/official-gui-interpretation.png다.
해당 일반 웹 경로에서 계정 로그인은 요구되지 않았다. 다른 제품 모드, desktop onboarding,
유료 제공자 계정 접근까지 확인했다는 의미는 아니다.

공식 openscience web 명령은 onboarding 경로를 거쳐 브라우저를 열고,
openscience serve는 로컬 서버를 시작한다. openscience run은 한 요청을 실행한다.
이 저장소의 실행기는 검증한 serve와 run --attach를 사용하며, 브라우저를 자동으로 열거나
사용자 계정·기존 프로필·Ollama 모델을 바꾸지 않는다.

## 대화로 연구하기

프로젝트를 연 뒤 조건을 구체적으로 말한다. 예를 들어 “현재 등록한 폭과 볼트 간격으로
정상 형상과 거부되는 형상을 비교하고, 거부 근거와 아직 검증하지 않은 항목을 설명해 달라”는
요청을 할 수 있다. 긴 연구 양식을 먼저 모두 채울 필요는 없다.

모델이 실행했다고 말한 것과 실제 tool receipt를 구분한다. 도구 기록에는 함수 이름,
입력, 실제 결과가 있어야 하고, CAD 결과는 같은 Core store의 원본 파일·ledger·artifact
해시로 확인한다. DOE/최적화 후보는 numerical engine이 만든다. 미검증 조건은 UNKNOWN,
설계 판단은 NOT_RELEASED로 유지한다.

검증용 Acceptance 프로필은 알려진 CAE Lab 도구9개만 허용한다. study_create/inspect,
parameters_discover/register/list, experiment_run/inspect/summary/compare다.
연구용 FixtureScalar는 CAD·CalculiX·수치 탐색·PDE 도구14개, StructuralFamilies는
study·모델해석·결과조회·요약·비교 도구6개를 허용한다. 프로필 범위 밖의 기능은
실행하지 않는다. 일반 shell·file·network·delegation 도구는 거부된다. 모델도 틀리거나 호출을 생략할 수
있으므로 이 허용 범위를 넓히거나 계획 문장만으로 연구를 완료 처리하지 않는다.

## 격리된 서버와 같은 대화 기록 사용하기

기존 Node, PowerShell 7, 공식 OpenScience 2.0.146, Ubuntu WSL의 CAE Lab Python 환경,
기존 Ollama alias openscience/qwen3-4b-ctx-16384가 필요하다. 실행기는 설치나 모델 다운로드를
하지 않는다. 다른 위치의 기존 공식 runtime은 -RuntimePrefix, Python은 -WslPython,
배포판은 -WslDistro로 지정한다.
기존 -Install 인자는 호환을 위해 남겨 둔 버전 확인이며 설치하지 않는다는 경고를 출력한다.

아래는 모델을 명시한 과거 Ollama 경로의 새 run/profile/store 예다. 현재 ChatGPT
연결 지시의 대체 실행으로 사용하지 않는다. 포트가 이미 사용 중이면 기존 서버를
인수하지 않고 실패한다. 다른 실행의 4096 또는 Lab 8766 프로세스를 종료하지 않는다.

~~~powershell
$run = 'openscience-' + [DateTime]::UtcNow.ToString('yyyyMMddTHHmmss')
$runtime = & .\scripts\openscience-server-local.ps1 -Mode Start -RunName $run -Port 4098 -ModelId 'openscience/qwen3-4b-ctx-16384'
$runtime.WorkspaceURL
~~~

반환한 WorkspaceURL을 브라우저에서 열어 같은 프로젝트/프로필로 대화한다.
OwnerPath는 서버의 실제 PID·생성 시각·명령·프로필·loopback socket·health·MCP 연결을
확인하는 식별 파일이다. URL이나 임의 PID만으로 다른 서버를 인수하지 않는다.
서버는 MCP가 Lab을 읽기 전에 소스 HEAD와 tracked/plugin/submodule 파일 bytes를 고정한다.
연결 완료와 각 추론 직전에 같은 소스인지 확인한다. 시작 후 코드·체크아웃이 바뀌면 CLI와
공식 Workspace의 새 추론을 차단하므로, 바뀐 소스로 실행하려면 기존 서버를 정상 종료하고
새 RunName을 사용한다. 이전 대화·실험과 조회 기록은 보존한다. Core/MCP/plugin 소스 변화는
소유한 세션의 취소·Stop을 막지 않으며, controller 자체의 변조에는 엄격한 소유 검사를 유지한다.
한 프로필의 모델 요청은 순서대로 실행한다. CLI는 프로필 command lock과 활성 세션 상태를
확인한다. CLI와 브라우저에서 동시에 연구를 시작하지 않는다. 정상 CLI 완료 후에는 일시적인
interpretation 전용 guard를 기본 9개 도구 설정으로 복원한다.

짧은 CLI 대화도 동일한 공식 서버에 붙는다. 멀티라인 입력은 공식 JS launcher를 Node로
직접 호출하는 ArgumentList로 전달하여 .cmd의 줄바꿈 확장을 피한다.

~~~powershell
$prompt = '이미 있는 실제 실험 결과를 확인하고 UNKNOWN과 NOT_RELEASED를 유지하여 설명해 줘.'
& .\scripts\openscience-local.ps1 -OwnerPath $runtime.OwnerPath -OpenScienceArgs @(
  'run', '--format', 'json', '--workspace', 'project', '--agent', 'caelab-acceptance',
  '--delegation', 'off', '--model', $runtime.Model, '--', $prompt
)
~~~

이 예는 모델을 실제 호출한다. 대화 세션은 공식 API로 먼저 생성·프로젝트 workspace를
검증하고 정확한 --session ID로 CLI에 넘긴다. 같은 대화를 이어가려면 보존된 command.json의
session_id를 별도 --session 값으로 지정한다. --continue로 최신 세션을 추측하지 않는다.

~~~powershell
& .\scripts\openscience-server-local.ps1 -Mode Status -OwnerPath $runtime.OwnerPath
& .\scripts\openscience-server-local.ps1 -Mode Stop -OwnerPath $runtime.OwnerPath
~~~

시간 제한이 지나면 정확한 세션의 공식 abort를 확인한 뒤, 같은 프로젝트의 세션인지와
실제 idle 상태를 확인·기록하고 이 실행기의 검증된 CLI를 종료한다. 취소 또는 idle을
확인하지 못하면 종료를 거부하고 PID/세션/실패 근거와 계속 기록되는 로그를 보존한다.
취소 응답 성공과 idle 확인은 별도 근거다. a1 연구 run01은 취소 응답과 자연 CLI 종료,
나중의 서버 종료 전 idle만 증명한다. 해당 소스의 timeout idle 누락은 별도 보완한다.
CLI는 독립적인 task relay를 통해 로그 파일에 직접 쓰므로 호출자가 반환하거나 종료해도
실행 중인 로그를 끊지 않는다. 이때 command.json의 해시는 당시의 진단용 snapshot이며,
실제 종료 후 relay-final.json에 기록한 해시와 구분한다. 종료 근거가 없는 이전 CLI가
있으면 같은 프로필의 새 CLI 연구를 차단한다.
서버 종료도 활성 대화가 있으면 취소 확인과 idle 검사를 선행한다.
종료 중 guard 변경·복원을 막고, 종료한 프로필을 다시 활성화할 때는 새 RunName을 사용한다.
세션·DB·예전 결과를 DELETE하지 않는다.

## 실행 근거와 검증 모드

실행기는 task profile 아래 HOME/USERPROFILE, OpenScience config/data, 모든 XDG,
TEMP/TMP를 명시한다. 상속된 계정/제공자 credential 환경 이름을 필터링하고 값을 출력하지
않는다. 이미 소유자가 있는 profile은 설정을 덮어쓰지 않는다.
MCP에는 새 프로필의 PYTHONPYCACHEPREFIX를 지정하여 이전 저장소의 Python bytecode cache를
재사용하지 않는다. 설치된 Python 환경과 모델 weights는 교체하지 않는다.
Windows sandbox warn fallback은 도구 권한 검사이며 OS containment는 아니다.
기업 배포의 license/security 승인은 별도 UNKNOWN이다.

등록 모델은 Qwen3-4B-Thinking-2507이다. 생각 토큰이 필요한 실제 template을 유지하고
temperature 0.6, top_p 0.95, reasoningEffort low, output 4096, steps 3을 사용한다.
provider 제한은 260초, 요청의 외부 제한은 기본 300초다. low가 생각 깊이를 줄였다는
주장은 하지 않는다. /no_think나 reasoningEffort none으로 template의 <think> prefill을
제거할 수 있다고 가정하지 않는다. 원본 모델과 기존 16k alias의 weight/template는 변경하지
않았다. loopback guard는 요청의 tool schema와 허용 이름을 확인한 뒤 원본 요청 bytes를
그대로 로컬 Ollama에 전달한다. tool_choice를 강제하거나 입력을 만들어 넣지 않는다.

모델 없이 실행기와 proxy를 검증하려면 다음 모드를 쓴다. 모의 HTTP는 실제 제공자를
호출하지 않으며, readiness 검증은 연구 완료 근거가 아니다.

~~~powershell
& .\scripts\openscience-server-local.ps1 -Mode SelfTest -RunName controller-check-new
& .\scripts\verify_openscience_live.ps1 -RuntimeChecksOnly -RunName launcher-check-new
~~~

실제 고정 연구 acceptance는 별도로 명시 실행한다. 새 빈 store의 연구 생성→발견한 실제
native path 등록→폭 38 CAD→볼트 간격 30 거부→조회/비교→근거 해석을 수행한다.
이 모드는 실제 모델·MCP 호출을 요구하고 모델 응답만으로 PASS하지 않는다.

~~~powershell
& .\scripts\verify_openscience_live.ps1 -RunName $run -OwnerPath $runtime.OwnerPath
~~~

원본 stdout/stderr, 세션 ID, CLI 종료 상태, 각 실제 tool receipt, config hash,
Core ledger/artifact bytes는 별도 기록된다. 실패한 stage는 남고 재실행은 새 기록을 만든다.
-Resume는 원래 소스 HEAD와 tracked/submodule 파일 bytes, 설정, 모델 manifest digest,
프로필·runtime owner·store, 원래 명령과 raw 해시가 모두 같을 때만 체크포인트를 재사용한다.
과거 trace를 현재 소스의 성공으로 재표기하거나 실패 trace를 성공 trace로 덮어쓰지 않는다.
각 stage와 최종 판정 직전에 소스·설정·모델·runtime을 다시 확인한다.
전체 acceptance를 재시도할 때는 새 RunName/profile/store를
쓴다. 기존 연구의 조회와 후속 대화는 기존 프로필의 정확한 세션에서 별도 CLI 요청으로 이어간다.

## 실제 확인된 범위와 한계

기존 live-04는 연구 생성/변수 조회 뒤 등록에서 도구 호출이 없어 FAILED_OR_PARTIAL이었다.
registry revision 0, 실험 0개인 당시 기록을 그대로 보존한다.

후속 live-05에서는 실제 13개 MCP 호출, registry revision 2, 폭 38의
COMPLETED_REVIEW_REQUIRED와 볼트 간격 30의 REJECTED를 같은 store에서 확인했다.
두 결과는 NOT_RELEASED, solver는 NOT_RUN이다. 거부 결과는 cad_source_relation의 실제
evidence를 유지했고 export/deck가 없다. machine_interface/static_strength/physical_load_test/
fatigue_durability는 모두 UNKNOWN이다. result/thread ledger와 artifact hash/size,
raw inspect와 저장 JSON의 동등성을 확인했다. 별도 해석 재시도에서 canonical UNKNOWN,
거부 evidence, 실제 측정 25단어를 확인했다. 모델의 “38 words” 자기 평가는 채택하지 않았다.

이 통과는 고정한 두 CAD 조건의 제한된 연구 흐름이다. 자유로운 장기 계획/모든 자연어 요청,
임의 CAD 편집/solver/strength/release, 새 실행기의 전체 모델 연구를 검증했다는 주장은 아니다.
새 실행기 검증 범위는 [별도 실행 기록](OPENSCIENCE_RUNTIME_ACCEPTANCE.md)에 구분해 남긴다.
기존 live-05는 초기 wrapper 03bfd7115ca3933cb18af17c55cc751839e91c98과 CAD Core
d0473e45af6575f7d7e319729681b72bb355385c의 혼합 실행 근거다. 문서나 새 launcher 커밋을
그 CAD 실행의 새 solver 검증으로 취급하지 않는다.

openscience/openscience.json.example는 pinned schema를 보여 주는 placeholder template다.
provider port 1은 시작 전 fail-closed 값이며 직접 실행 설정이 아니다. 위 controller가 고유한
profile·WSL path·store와 검증된 loopback guard 주소를 생성한다.

## 공식 근거

OpenScience 2.0.146 upstream commit은
4082a2ecb73e166d4503963798228ba700f3840f다.

- [시작 안내](https://github.com/synthetic-sciences/openscience/blob/4082a2ecb73e166d4503963798228ba700f3840f/frontend/docs/src/content/openscience/index.mdx)
- [Workspace 사용법](https://github.com/synthetic-sciences/openscience/blob/4082a2ecb73e166d4503963798228ba700f3840f/frontend/docs/src/content/openscience/workspace.mdx)
- [공식 serve](https://github.com/synthetic-sciences/openscience/blob/4082a2ecb73e166d4503963798228ba700f3840f/backend/cli/src/cli/cmd/serve.ts)
- [공식 run/attach/세션 검증](https://github.com/synthetic-sciences/openscience/blob/4082a2ecb73e166d4503963798228ba700f3840f/backend/cli/src/cli/cmd/run.ts)
- [Config/Agent schema](https://github.com/synthetic-sciences/openscience/blob/4082a2ecb73e166d4503963798228ba700f3840f/backend/cli/src/config/config.ts)
- [세션 abort 및 runner_timeout](https://github.com/synthetic-sciences/openscience/blob/4082a2ecb73e166d4503963798228ba700f3840f/backend/cli/src/server/routes/session.ts)
- [Qwen3-4B-Thinking-2507 공식 model card](https://huggingface.co/Qwen/Qwen3-4B-Thinking-2507)
- [이전 실패/연결 상태 기록](CONNECTED_CONTINUATION.md)
