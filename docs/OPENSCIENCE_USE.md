# OpenScience 사용 방식과 로컬 실행

2026-09-30. 사용법 설명을 화면 재설계 지시로 해석하지 않는다.

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

기본 프로필은 알려진 CAE Lab 도구 9개만 허용한다. study_create/inspect,
parameters_discover/register/list, experiment_run/inspect/summary/compare다.
일반 shell·file·network·delegation 도구는 거부된다. 로컬 모델도 틀리거나 호출을 생략할 수
있으므로 이 허용 범위를 넓히거나 계획 문장만으로 연구를 완료 처리하지 않는다.

## 격리된 서버와 같은 대화 기록 사용하기

기존 Node, PowerShell 7, 공식 OpenScience 2.0.146, Ubuntu WSL의 CAE Lab Python 환경,
기존 Ollama alias openscience/qwen3-4b-ctx-16384가 필요하다. 실행기는 설치나 모델 다운로드를
하지 않는다. 다른 위치의 기존 공식 runtime은 -RuntimePrefix, Python은 -WslPython,
배포판은 -WslDistro로 지정한다.
기존 -Install 인자는 호환을 위해 남겨 둔 버전 확인이며 설치하지 않는다는 경고를 출력한다.

아래는 새 run/profile/store를 사용하는 예다. 포트가 이미 사용 중이면 기존 서버를
인수하지 않고 실패한다. 다른 실행의 4096 또는 Lab 8766 프로세스를 종료하지 않는다.

~~~powershell
$run = 'openscience-' + [DateTime]::UtcNow.ToString('yyyyMMddTHHmmss')
$runtime = & .\scripts\openscience-server-local.ps1 -Mode Start -RunName $run -Port 4098
$runtime.WorkspaceURL
~~~

반환한 WorkspaceURL을 브라우저에서 열어 같은 프로젝트/프로필로 대화한다.
OwnerPath는 서버의 실제 PID·생성 시각·명령·프로필·loopback socket·health·MCP 연결을
확인하는 식별 파일이다. URL이나 임의 PID만으로 다른 서버를 인수하지 않는다.
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

시간 제한이 지나면 정확한 세션의 공식 abort를 먼저 확인하고 이 실행기의 검증된 CLI만
종료한다. 취소가 확인되지 않으면 종료를 거부하고 PID/세션/실패 근거를 보존한다.
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
