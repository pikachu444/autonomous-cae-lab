# 개발 스킬과 도구 사용 기준

2026-10-07 · Codex 개발용 · 제품 기능/필수 설치와 별도

## 1. 이번에 실제 저장한 것

`.agents/skills/`에 Matt Pocock의 기존 `research`, `grill-me`, `grilling` 원문을 저장했다. 전용 CAE 스킬을 새로 만든 것이 아니다. 원문 출처와 MIT 허가문은 아래와 `../.agents/skills/LICENSE.mattpocock`에 있다. 조사 시점의 버전을 보관하며, 미래 제품의 실행 조건으로 그 버전이나 지문을 고정하지 않는다.

각 스킬의 `agents/openai.yaml`은 이 프로젝트에서 추가한 Codex 호출 메타데이터다. **세 스킬 모두 묵시적 호출은 끄고 필요할 때 명시적으로 선택한다.** 스킬이 중요하지 않아서가 아니다. 긴 인터뷰나 매번 새 조사·보조 생성을 막고 해당 기능의 필요에 맞춰 사용하기 위해서다. 원문 본문은 바꾸지 않는다. [S0]

| 스킬/도구 | 저장·사용 상태 | 쓸 때 | 이번에 하지 않을 일 |
|---|---|---|---|
| `research` | 원문 저장, 주요 외부 구현 조사에 명시 호출 | 새 공통 기반·주요 라이브러리·불명확한 API를 조사 | 작은 수정마다 새 조사 파일·새 보조 스레드 |
| `grill-me` + `grilling` | 두 원문 저장, 남은 중요한 결정에만 명시 호출 | 사용자 결정이 필요한 쟁점을 압박 검토 | 이미 합의한 제품 전체 재인터뷰 |
| `find-skills` | 원문 확인, 선택 후보로 기록. 아직 설치하지 않음 | 실제로 필요한 개발 스킬이 없는 경우 | 라이브러리/solver 검색 대체, 전체 카탈로그 설치 |
| `search-first` 계열 | 대안. 기본 조사 경로는 저장된 `research` | 적합한 기존 설치본이 있고 역할을 더 잘 수행할 때 | 이름만 보고 채택, research와 동일 조사 중복 |
| Codex 기본 review / 검토 에이전트 | 기존 도구를 사용. 새 리뷰 스킬 불필요 | 의미 있는 기능 묶음의 오류·수치·실사용 검토 | 매 수정마다 최고 모델 리뷰, 근거 없는 형식 지적 |
| GitHub 검색 | 사용 가능한 연결/CLI/공개 검색 활용 | 저장소·구현·테스트·유지보수 확인 | 스킬 설치만 하고 실제 소스는 안 읽음 |
| Context7 | 필요 시 선택할 문서 도구, 이번에 설치하지 않음 | 선택 라이브러리의 현재 API/버전 확인 | 도입을 모든 개발의 선행 조건으로 설정 |
| Ouroboros | 아래 2026-10-08 제한 설치·호스트 호출 확인. 제품과 별도 개발 도구 | 실제 분업/재개 문제가 생기고 명시적으로 호출할 때만 | 제품 runtime 의존성, 전체 재인터뷰·seed 재작성 강제 |

**등록·발견·실행은 다르다.** GitHub에 스킬 파일이 있다는 사실은 사용자 PC의 Codex가 이미 읽었다는 증거가 아니다. 최초 세션은 로컬 파일 존재와 스킬 목록을 확인한다. 같은 이름의 전역 스킬이 있으면 경로를 보고 프로젝트의 원본을 선택한다. 스킬이 목록에 없으면 원문 경로를 명시해 읽는다. 스킬 활성화 시험을 못 했으면 못 했다고 보고한다. [S0]

## 2. 실제 호출 방법

### 조사: `research`

주 담당이 주요 재사용 결정을 해야 할 때 `$research`를 명시적으로 선택한다. 해당 기능의 질문·관련 W절·현재 코드 위치·반환할 판단을 전달한다. 보조가 필요하면 `reuse_researcher`를 하나 사용한다. 이 스킬이 요구하는 보조도 CODEX_WORKFLOW의 동시 실행 상한에 포함한다.

예: ‘W2의 준비된 재료 평가를 병렬 동정에 연결한다. 기존 코드와 SciPy 공식 문서에서 작업자별 준비, 상태 분리, 직렬화, 라이선스/설치 부담을 확인하라. 새 optimizer 대신 어떤 연결을 재사용할지 답하라.’

외부 솔버/파일 연결의 조사 예: ‘설계 4.4절·7.1절에 맞춰 기존 ASCII reader, 사용자 추출 도구, 표 처리와 SciPy/SALib 연결을 확인하라. LS-OPT는 사용할 수 없다. 파일의 숫자를 읽는 일과 응답의 물리적 의미를 구분하고, 같은 수치 계획을 다른 솔버에도 적용할 수 있는 최소 연결을 제안하라.’ 이미 표준 표로 추출되는 경우 native 바이너리 parser나 전체 솔버 SDK를 먼저 만들지 않는다. 기존 사실을 조사하는 것과 회사 채널·단위·파손 관측을 사용자에게 확인해야 하는 일을 구분한다. 필요한 근거는 현재 설계의 출처 절에 남기고 칩 전용 스킬을 추가하지 않는다.

원문은 조사 결과를 Markdown에 남기도록 한다. **선택한 설계 절 또는 기존 관련 조사 기록 한 곳**에 짧은 판단과 출처를 반영한다. 같은 결론의 별도 감사·새 계획서를 만들지 않는다. 조사 전용 보조는 제품 코드와 공통 계약을 바꾸지 않는다. 자식 조사 에이전트가 다시 `research`를 호출하여 자식을 만들지 않는다. 보조 도구가 없으면 주 담당이 직접 같은 조사를 하고 그 실행 방식을 알린다.

### 요구 검토: `grill-me`와 `grilling`

현재 `grill-me`는 `grilling`을 호출하는 진입점이다. 둘을 함께 둔다. 원문은 호스트의 `Skill` 도구를 가리킨다. 그런 도구가 없는 Codex에서는 `$grilling` 또는 `../.agents/skills/grilling/SKILL.md`를 명시적으로 읽어 같은 절차를 사용한다. 존재하지 않는 도구 호출을 했다고 말하지 않는다.

인터뷰 범위는 아직 결정하지 않은 중요한 쟁점이다. 기존 설계·사용 사례에서 답을 찾고도 결정이 필요한 경우에만 사용한다. 권장안과 기능·비용 영향을 함께 질문한다. 사용자가 결정해야 할 선택을 에이전트가 임의로 정하지 않는다. 파일 위치·설치 상태·API 정보처럼 조사로 해결할 사실은 사용자에게 묻지 않는다. LS-OPT 비사용·상용 출력파일 활용·칩 사례의 비고정은 이미 결정됐으므로 다시 선택시키지 않는다.

원문의 ‘모든 분기를 합의할 때까지’는 선택한 미결정 쟁점의 범위에 적용한다. W1–W5 전체를 다시 설계한다는 뜻이 아니다. 원문 절차가 현재 지시와 맞지 않으면 무리하게 강제하지 않고 해당 쟁점의 질문만 한다. 이는 제품 계약을 몰래 바꾸는 허가가 아니다.

### 검토·단순화

일반 변경은 주 담당과 Codex 기본 리뷰로 본다. 공통 경계나 수치 의미가 바뀌는 묶음은 `integration_reviewer`를 사용한다. 필요한 경우 실제 실행을 부모에게 요청하고, 수행하지 않은 검사를 통과했다고 쓰지 않는다. 검토가 끝나면 해당 결함을 해결하고 다음 사용자 기능으로 간다.

검토 질문은 다음으로 충분하다. 실제 사용 흐름이 연결됐는가? 수치·단위·상태·오류를 올바르게 전달하는가? 이미 있는 구현을 재사용했는가? 같은 책임을 여러 곳에 복제했는가? 단지 옛 이름을 바꾼 profile 체계를 만들었는가? 외부 파일과 메모리 모델을 같은 수치 기능에 넣을 수 있고, LLM의 계획이 실제 DOE와 영향도 자료로 이어지는가?

### 새 스킬 탐색: `find-skills`

이름만으로 새 스킬을 설치하지 않는다. Vercel 원문은 `npx skills find ...`와 카탈로그 탐색을 안내한다. 설치 수는 발견의 참고일 뿐 품질 증명이나 채택 조건으로 삼지 않는다. 원본·의존성·라이선스·현재 도구 호환성을 읽는다. 원문의 전역 설치 예시를 그대로 실행하지 않는다. 필요하다면 저장소 범위 설치를 선택하고 실제 설치 명령은 설치판 도움말로 확인한다. Node/네트워크가 없으면 웹/기존 검색 도구로 조사한다. [S4]

## 3. 원본과 출처

| 항목 | 원본 |
|---|---|
| research | https://github.com/mattpocock/skills/blob/6fd947921b935b7e1e69293a200400f0fdd5c15f/skills/engineering/research/SKILL.md |
| grill-me | https://github.com/mattpocock/skills/blob/6fd947921b935b7e1e69293a200400f0fdd5c15f/skills/productivity/grill-me/SKILL.md |
| grilling | https://github.com/mattpocock/skills/blob/6fd947921b935b7e1e69293a200400f0fdd5c15f/skills/productivity/grilling/SKILL.md |
| 세 스킬 MIT 라이선스 | https://github.com/mattpocock/skills/blob/6fd947921b935b7e1e69293a200400f0fdd5c15f/LICENSE |
| [S4] find-skills | https://github.com/vercel-labs/skills/blob/b3810644fb13ecbc2a2664afa2042f656357c544/skills/find-skills/SKILL.md |
| Ouroboros | https://github.com/Q00/ouroboros |
| Context7 | https://context7.com/docs/overview |
| [S0] Codex 스킬 위치·호출·메타데이터 | https://developers.openai.com/codex/skills/ |

스킬의 버전 기록은 출처를 알기 위한 것이다. 최신 버전의 개선을 막는 실행 규칙이 아니다. 업데이트할 때 본문과 의존성 변경을 읽고 필요한 것만 바꾼다. 자동 전역 업데이트·전체 하네스 설치·새 유료 서비스 연결은 하지 않는다. 라이브러리·도구마다 라이선스가 다르므로 한 스킬의 MIT 허가를 다른 도구에 확대하지 않는다.

## 4. 저장된 파일과 아직 하지 않은 일

세 SKILL.md, Codex 명시 호출 메타데이터, 라이선스, 개발 역할·모델 설정은 이 저장소의 개발 파일이다. 제품 Python 패키지, 배포 의존성, 전문가 수, 솔버 권한에 포함하지 않는다.

초기의 저장 작업에서는 새 스킬 엔진, 강제 hook, 자동 인터뷰 봇, 토큰 사용량 감시 서비스를 만들지 않았다. 아래 설치 검증은 나중에 사용자 지시로 별도 수행한 것이며, 제품 실행 조건을 바꾸지 않는다. 개정 4 보완에서는 스킬 원문·설정은 그대로 두고 기존 스킬이 조사할 외부 파일 연구 문맥만 이 문서에 추가했다.

## 5. 2026-10-08 로컬 설치·호스트 발견·제한 호출 결과

요청에 따라 이 PC의 **개발 환경**만 확인했다. 기준 원본은 `mattpocock/skills`의 `f3fc5632f401156837ee3872f14fe33ccf1024ea`와 `Q00/ouroboros`의 `f587795674999a09b51530779640730eda55b174`이다. 기존 저장소의 2026-10-07 스킬 복사본은 덮지 않고 최신 원문을 별도 전역 위치에 설치했다. 실행 중인 Codex Desktop 세션에 새 스킬이 즉시 검색되는지는 확인하지 않았다. Codex의 [스킬 개념](https://developers.openai.com/plugins/concepts/skills)과 [MCP 등록 방식](https://developers.openai.com/learn/docs-mcp)은 별도 경계다.

| 단계 | 실제 확인과 남은 한계 |
|---|---|
| 스킬 로컬 설치 | 시스템 `skill-installer`의 `install-skill-from-github.py`로 `research`, `grill-me`, `grilling`을 `C:\Users\pikac\.codex\skills\`에 설치. 세 `SKILL.md` 모두 위 최신 clone과 줄바꿈 정규화 후 본문 일치. 기존 설치 항목이 없음을 확인하고 설치했다. 새 세션에서의 자동 발견은 별도 확인 대상이며, 현재 살아 있는 세션의 자동 발견을 증명하지 않았다. `grill-me` 원문은 `Skill` 도구로 `grilling`을 부르므로, 해당 도구가 없는 호스트에서는 `grilling/SKILL.md`를 직접 읽어 적용한다. |
| Ouroboros 패키지 | `work/ouroboros-venv`에 cloned source의 `ouroboros-ai[mcp]`를 private Python 3.12.14와 uv 0.12.5로 설치했다. 실제 `ouroboros --help`, `setup --help`, `mcp serve --help`가 실행됐고 버전은 `0.1.dev1`. 설치는 이 작업 폴더 안에 한정된다. [공식 Codex runtime 지침](https://github.com/Q00/ouroboros/blob/f587795674999a09b51530779640730eda55b174/docs/runtime-guides/codex.md)은 native Windows를 experimental로 표시하고 `--mcp-mode http`를 요구한다. |
| Ouroboros 등록 | `ouroboros setup --runtime codex --mcp-mode http --non-interactive`가 종료 코드 0으로 마치고 `~/.codex/config.toml`에 `http://127.0.0.1:8765/mcp` URL, 관리 규칙 1개, `ouroboros-*` 스킬 23개 및 worker profile을 등록했다. `~/.ouroboros/config.yaml`은 runtime=codex와 기본 역할 effort를 기록한다. 설치 stdout에 별도 `subprocess` reader thread의 Windows cp949 `UnicodeDecodeError`가 있었으므로 완전 무오류 실행이라고 부르지 않는다. 그러나 설치된 파일과 HTTP host를 각각 다시 확인했다. 제품의 모델/솔버 인증 또는 장기 자동 작업은 설정하지 않았다. |
| Codex CLI 호환 | 사용자 Desktop의 `codex-cli 0.146.1`은 기존 `~/.codex/config.toml`의 `[features.context_management]` map을 boolean으로 기대하며 `codex mcp list`에서 실패했다. 기존 사용자 설정을 삭제·완화하지 않았다. 최신 `@openai/codex 0.161.0`을 **전역 npm 업데이트 없이** `work/codex-cli`에 설치했고, 그 CLI의 `mcp list`는 Ouroboros를 enabled URL로 표시하고 `login status`는 기존 ChatGPT 로그인 경로를 사용한다고 반환했다. `~/.ouroboros/config.yaml`의 `orchestrator.codex_cli_path`만 이 로컬 0.161.0 실행 파일로 바꿨다. 기존 Codex 모델과 자격 증명은 변경하지 않았다. 작업 폴더를 지우면 이 지정 경로도 사라지므로 그때 재설치/경로 갱신이 필요하다. |
| 실제 HTTP MCP 호출 | `127.0.0.1:8765`의 streamable HTTP 서버를 직접 띄워 Python MCP 2.0 클라이언트로 `initialize`/`list_tools`를 호출했다. `ouroboros-mcp` `0.1.dev1`, 도구 36개를 실제 반환했다. 이어 읽기 전용 `ouroboros_query_events(limit=1,offset=0)`가 `is_error=false`로 응답했다. 이는 **설치+호스트 접속+제한 호출 성공**이다. 실제 Codex 모델의 Ouroboros 작업 실행, seed/interview/evaluate/ralph, 유료 API 호출, 제품 AI 기능은 수행하지 않았다. 시험 스크립트는 `work/verify-ouroboros-mcp.py`. |

검증 시 HTTP host는 작업 폴더의 격리 venv로 `127.0.0.1:8765/mcp`에서 실행했다. 600초 무호출 시 종료하므로 이후에도 계속 떠 있다고 보장하지 않는다. 영구 서비스 등록은 없다. 다음에 재현하려면 작업 폴더에서 `work/ouroboros-venv/Scripts/python.exe -m ouroboros mcp serve --runtime codex --llm-backend codex --transport streamable-http --host 127.0.0.1 --port 8765 --workspace-root work`로 서버를 시작하고, 새 Codex 세션에서 사용한다. native Windows의 stdio MCP는 공식 지침상 사용하지 않는다. HTTP host는 로컬 loopback 전용이고 이번 시험에서는 모델 호출 권한을 쓰지 않았다.

## 6. Windows 공학 앱 시안을 위한 UI 스킬 평가와 설치

기존 웹 시안이 거부된 뒤, 두 공개 원본의 `SKILL.md`를 실제로 읽고 시스템 `skill-installer`로 전역 설치했다. 설치본은 다음 Codex 턴부터 검색될 수 있다. 저장소의 `.agents/skills` 복사본이나 제품 runtime에는 추가하지 않았으며 자동 hook도 설치하지 않았다. 아래 커밋은 **원본 식별**을 위한 것으로 향후 업데이트를 막는 버전 고정 규칙이 아니다.

| 설치본과 정확한 원본 | 이번 Qt Widgets 시안에 적용 | 적용하지 않을 부분 |
|---|---|---|
| `C:\Users\pikac\.codex\skills\frontend-design`, [Anthropic `frontend-design/SKILL.md`](https://github.com/anthropics/skills/blob/683bc88e56f3e09ba94f7055977f3d3aa499f202/skills/frontend-design/SKILL.md), 라이선스는 [같은 폴더의 LICENSE.txt](https://github.com/anthropics/skills/blob/683bc88e56f3e09ba94f7055977f3d3aa499f202/skills/frontend-design/LICENSE.txt) | 실제 해석·시험 대상에 맞춘 화면 내용; 구조선·레이블·번호는 의미를 전달할 때만 사용; 버튼 이름과 완료/오류 문구 일치; 오류에는 복구 방법 명시; 스크린샷 자기 검토. | 웹 랜딩의 hero, 마케팅 타이포, 스크롤 연출, 모바일 breakpoint와 큰 여백을 이 고밀도 데스크톱 작업화면에 기계적으로 적용하지 않는다. |
| `C:\Users\pikac\.codex\skills\impeccable`, [pbakaus `.agents/skills/impeccable/SKILL.md`](https://github.com/pbakaus/impeccable/blob/778c8a7b71ccd5bfe3ca6ac68c15d9d872d0f87d/.agents/skills/impeccable/SKILL.md), [Apache-2.0](https://github.com/pbakaus/impeccable/blob/778c8a7b71ccd5bfe3ca6ac68c15d9d872d0f87d/LICENSE) | [`reference/operate.md`](https://github.com/pbakaus/impeccable/blob/778c8a7b71ccd5bfe3ca6ac68c15d9d872d0f87d/skill/reference/operate.md)의 **Operate** 모드: 과업 중심 탐색, 익숙한 기본 조작, 밀도 있는 표/패널 허용, 선택·집중·진행·실패 상태 구분, 일관된 control/shortcut. [`craft-floor.md`](https://github.com/pbakaus/impeccable/blob/778c8a7b71ccd5bfe3ca6ac68c15d9d872d0f87d/skill/reference/craft-floor.md)의 실제 작동·키보드 focus·오류 복구 점검. | Persuade/Experience형 시각 과시, 장식용 카드·배경·애니메이션은 적용하지 않는다. 스킬의 `audit.native.md`는 iOS/Android/adaptive용이라 Windows Qt 검증 근거로 쓰지 않는다. 웹용 detector/hook도 Qt 검증 결과로 주장하지 않는다. |

두 설치본의 `SKILL.md`는 각각 지정 커밋 checkout과 **줄바꿈 정규화 후 동일**했다. Impeccable의 `impeccable.cmd context --target prototypes/desktop-lab/desktop.py`는 저장소에서 exit 0으로 실행됐다. 대상 파일 존재와 `PRODUCT.md`/`DESIGN.md` 부재, 시각 구현 미판정을 보고했다. 이 설정 출력은 후속 새 화면 작업 시 제품 문맥을 기록하라고 안내한다. 현재 상세 기획의 제품 사실을 되풀이해 새 요구로 바꾸거나, Windows Qt 화면을 웹 detector 통과로 표시하지 않는다.
