# Autonomous CAE Lab

A local-first engineering research workbench: use existing numerical tools,
material models, solvers and data analysis through a common working environment.
CAD-based design is one use case, not the definition of the product. Optional
expert assistance combines project knowledge, literature and engineering tools.

## Codex 개발 시작 — 아래 프롬프트만 전달

Codex에서 주 담당 모델을 **GPT-6 Astra**, 추론 수준을 **High**로 선택한다.
개발에 필요한 설계 원문, 사용 사례, 운영 지침, 스킬 원문과 프로젝트 설정은
이 저장소에 있다. 이전 대화의 첨부파일이나 긴 프롬프트를 다시 업로드하지 않는다.
현재 인계 기준은 PR #1의 브랜치 `redesign/research-workbench-20261007`이다.
PR이 이미 병합됐다면 현재 병합된 내용을 사용하고, 작업 중인 로컬 변경은 보존한다.

```text
pikachu444/autonomous-cae-lab의 PR #1 최신 내용을 기준으로,
CODEX_START.txt와 연결된 문서·스킬·설정을 읽고 W1–W5를 구현해.
기존 작업은 보존하고, 검토와 필요한 검사를 마친 변경은 PR을 통해 main에 병합해.
주 담당은 Astra High로 시작해.
```

위 예시는 구현과 검토 후 병합까지 맡기는 지시다. 저장소에 영구적인 병합 금지
정책은 없다. 문서 검토 당시의 미병합 상태와 이후 개발의 병합 권한을 구분한다.
현재 사용자 지시가 병합까지 포함하면 같은 범위의 매 작은 변경마다 재승인을
요구하지 않는다. 보호 규칙과 필수 검사는 지키고, 부분 기능의 병합을 전체 완료로
표시하지 않는다. 병합을 맡기지 않은 세션에서는 PR 제출로 종료한다.

[CODEX_START.txt](CODEX_START.txt)가 상세 시작 지시다. 필요한 문서는 아래처럼
역할을 나눠 보관한다. 같은 제품 설계를 새 문서로 다시 작성하지 않는다.

| 참조 | 역할 |
|---|---|
| [AGENTS.md](AGENTS.md) | 전체 목표, 개발 원칙과 문서 진입점 |
| [WORKBENCH_REDESIGN.md](docs/WORKBENCH_REDESIGN.md) | 개정 4: 기존 W1–W5 유지, 외부 파일 응답·LLM 연구 반복의 공통 연결 보강 |
| [WORKBENCH_USE_CASES.md](docs/WORKBENCH_USE_CASES.md) | 기존 16개 사용처 + 외부 파일 기반 연구의 공통 사용 패턴 UC17 |
| [CODEX_WORKFLOW.md](docs/CODEX_WORKFLOW.md) | 모델·추론·토큰·분업·통합·진행·세션 재개 |
| [DEVELOPMENT_SKILLS.md](docs/DEVELOPMENT_SKILLS.md) | 기존 스킬의 원본·의존성·호출 시점과 선택 도구 |
| [.codex/config.toml](.codex/config.toml), [.codex/agents](.codex/agents/) | 개발 모델 기본값과 조사·구현·검토 역할 |
| [.agents/skills](.agents/skills/) | research, grill-me, grilling 원문과 라이선스 |

기본 개발 구성은 주 담당 Astra High, 보조 Sol High, 동시에 열린 보조 최대
2개다. 필요할 때만 분업한다. 제품 안의 연구용 모델·솔버 설정과 혼동하지 않는다.

설정을 보관한 것과 사용자 PC에서 실제 활성화한 것은 다르다. 첫 세션은
선택된 모델·추론, 프로젝트 신뢰, 스킬·역할 발견 상태를 짧게 확인한다.
빈 폴더에서 저장소를 가져온 뒤 설정 재로딩이 필요한 경우에는 그 사실과
재개 위치만 안내한다. 자동 적용을 가장하거나 사용자의 인증·전역 권한을
변경하지 않는다. 스킬이 목록에 없으면 지침에 지정된 원문 경로를 읽는다.
필수 접근 승인은 사용자에게 요청하되 설정 확인을 별도 개발 프로젝트로
늘리거나 자료를 다시 업로드하도록 요구하지 않는다.

이 시작 지시는 제품 구현을 시작하기 위한 것이다. 설명용 HTML·영상의 수치
예시나 규칙 기반 자문은 실제 제품 솔버·LLM 연결의 완료 증거가 아니다.
이전 PDF/HTML/영상은 개정 3 시점의 설명 자료이며, 개정 4의 구현 기준은
저장소 Markdown이다.

## External solver results and AI-assisted research

LS-OPT is unavailable and is not a dependency or fallback. Keep existing solver
inputs and execution/extraction tools. Read separate ASCII/CSV/text outputs into
the same response, DOE, optimization and sensitivity interfaces. Results-only
analysis does not require the source solver. Automated new evaluations require
an actual execution connection; missing results are not fabricated.

An optional expert helps choose variables, ranges, objectives and a DOE plan.
Numerical libraries generate candidates and calculate responses and sensitivity.
The expert reads those results and proposes the next search, experiment or stop.
The chip-impact identification example must not define all supported variables,
file names or physical domains. The same path supports thermal, structural,
material and numerical studies. See redesign sections 4.4, 7.1 and 12.8.

Build the generic file/execution boundary during W1–W5. Add specific commercial
solver cards, native output formats and company execution environments as domain
connections. Do not block the first workbench on LS-DYNA access or convert all
models to OpenRadioss. This is target behavior, not a claim of a working LS-DYNA
adapter or a completed AI optimization loop.

## Current development direction

Read [the workbench redesign and implementation plan](docs/WORKBENCH_REDESIGN.md).
It separates verified implementation from target behavior and identifies the
next coherent improvement bundle. [AGENTS.md](AGENTS.md) is the development entry
point; cumulative historical records are no longer mandatory startup reading.

Python/API and CLI are the primary computation interfaces. OpenScience and MCP
are optional integrations in the target architecture. Existing code already has
CAD-free model/PDE interfaces and SciPy-based search, but portable installation,
extension, runtime admission and performance still need work. This documentation
change does not claim that those improvements have been implemented.

## Existing code and usage

- `caelab/`: Python API, CLI, experiments, numerical drivers and backend adapters.
- `plugins/`: domain-specific models/checks and the reused fixture implementation.
- `apps/lab/`: local human interface and existing job coordination.
- `openscience/`: current MCP and OpenScience integration; not the intended owner
  of the numerical core.
- `tests/`, `scripts/`, `benchmarks/`: existing checks and recorded examples.

Existing environment instructions remain in [local execution](docs/LOCAL_EXECUTION.md)
and [OpenScience use](docs/OPENSCIENCE_USE.md). They describe specific historical
installations; confirm applicable paths, dependencies and current code before use.
The CAD demo is not the complete product. No universal clean-install or current
native-solver qualification is asserted here.

Older status histories, architecture decisions and execution records remain
available for targeted reference. They must not override the current owner-approved
direction or be mistaken for measurements from the latest checkout.

Do not commit credentials, company models, private reports or experimental data.
