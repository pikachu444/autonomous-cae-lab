# OpenScience 사용 방식과 현재 로컬 상태

2026-09-30. 사용법에 대한 질문을 화면 변경 지시로 해석하지 않는다.

## 화면의 구분

`http://127.0.0.1:8766/`의 Autonomous CAE Lab은 이 저장소에서 만든
연구·설계·해석·탐색·결과 화면이다. 공통 Core의 기록과 도구를 사람이
직접 실행하고 확인한다. 현재 AI 대화 기능은 연결되어 있지 않다.
이 화면을 공식 OpenScience 화면이나 실제 에이전트 사용 예로 설명하면 안 된다.

공식 OpenScience는 프로젝트 폴더를 열고 모델을 선택한 뒤 대화로
연구를 진행한다. 웹 workspace, 데스크톱 앱, 단일 요청을 실행하는
터미널 인터페이스가 있다. 긴 연구 양식을 모두 채우는 것이 필수는 아니다.
아래 설명은 설치 버전과 대응하는 공식 문서를 확인한 결과이며,
이 컴퓨터에서 공식 GUI의 전체 흐름을 실행했다는 주장이 아니다.

## 기본 사용 흐름

1. 프로젝트 폴더를 연결한다.
2. 사용할 모델을 고른다. 자신의 모델 제공자 계정/API 키 또는 로컬 모델을 연결할 수 있다.
3. 대화창에 목표, 사용할 자료, 조건, 원하는 결과를 말한다.
4. 에이전트의 방법 제안과 실제 도구 호출·실행 상태를 확인한다.
5. 생성한 결과와 원본 근거를 확인하고 후속 질문으로 이어간다.

CAE Lab에 연결할 때는 등록된 MCP 도구가 같은 Core를 호출해야 한다.
예를 들어 ‘지지부 폭을 바꾸어 형상을 비교하고, 거부된 조건의 이유와
미검증 항목을 설명해 달라’는 연구 요청을 전달할 수 있다.
모델의 설명과 실제 도구 실행 기록은 별도로 확인한다.
DOE와 최적화의 수치 후보는 기존 numerical engine이 생성한다.
AI의 판단이나 solver 실행 성공만으로 강도 승인 또는 RELEASED를 부여하지 않는다.

## 현재 검증된 범위

- OpenScience 2.0.146과 로컬 Ollama 모델의 설치·연결을 확인했다.
- 실제 OpenScience → MCP → Core 연구 생성 및 CAD 변수 조회가 성공했다.
- `live-04`에서는 변수 조회가 같은 입력·결과로 두 번 실행된 것을 기록했다.
- 이후 변수 등록 단계는 모델이 도구를 호출하지 않아 실패했다. registry revision은 0,
  실험은 0개이며, 이 실행의 CAD·검증·해석·설명 전체 흐름은 미검증이다.
- 공식 OpenScience GUI의 전체 로컬 사용 흐름은 아직 검증하지 않았다.
- 별도 Lab HTTP 화면의 실제 CAD 성공·거부 및 PDE 실행은 통과했다.
  이것이 OpenScience 에이전트의 완료를 뜻하지 않는다.

## 공식 근거

설치된 2.0.146에 대응하는 upstream commit:
`4082a2ecb73e166d4503963798228ba700f3840f`.

- [공식 소개](https://github.com/synthetic-sciences/openscience)
- [해당 버전의 시작 안내](https://github.com/synthetic-sciences/openscience/blob/4082a2ecb73e166d4503963798228ba700f3840f/frontend/docs/src/content/openscience/index.mdx)
- [해당 버전의 workspace 사용법](https://github.com/synthetic-sciences/openscience/blob/4082a2ecb73e166d4503963798228ba700f3840f/frontend/docs/src/content/openscience/workspace.mdx)
- [실행 상태와 실패 시도](CONNECTED_CONTINUATION.md)

공식 문서의 `openscience`/`openscience web`는 프로젝트의 브라우저
workspace를 시작하고, `openscience run`은 단일 에이전트 요청을 실행한다.
현재 로컬 설치는 저장소 밖의 격리된 task runtime에 보존된다.
계정 인증과 모델 접근 권한, GUI 첫 실행 조건은 실제 화면에서 확인해야 한다.
