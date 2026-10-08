# Current workbench implementation

## 상세 기획과 로컬 화면 검토 — 2026-10-08

**상태 정정 — 사용자 거부 후 재설계 중.** 사용자가 아래 웹 시안의 낮은 정보·기능 밀도, 두서없는 명령 구성, 독립 공학 프로그램 경험 부재, 참고 UI/STORM 반영 부족을 지적했다. 앞선 기획·화면 검토 완료 판정을 철회한다. V00–V10과 E01/E02는 제한된 기술 관찰로 보존하며 제품/UI 적합성이나 사용자 수용의 통과로 해석하지 않는다. 이전 독립 검토의 통과 판정도 사용자 거부를 대체하지 못한다. PR #5는 Draft를 유지하고 병합하지 않는다. Windows Qt Widgets 기반 시안을 같은 명세에서 재검토 중이며 본 제품 전체 구현으로 범위를 확대하지 않는다.

현재 작업 브랜치 `design/local-workspaces`, 기준 remote main `fc7c82d`. Space 4개 페이지 원문을 실제 읽었고 인계 ZIP의 context/references/rejected-prototype를 비교했다. ZIP의 시작 지시는 개정2이므로 Space 개정3의 기획 우선 지시를 적용한다. 전체 제품 본 구현은 이번 범위가 아니다.

현재 설계: `PLANNING_DESIGN.md`, `PLANNING_SCREENS.md`, `PLANNING_CONTRACTS.md`, `PLANNING_CODE_REUSE.md`, `PLANNING_HANDOFF.md`. 첫 전체 구성안과 보완 명세는 기존 Space 상세 기준 페이지의 현재 상세 설계 절에서 관리한다. Space와 Git 자동 동기화는 없다.

### 재설계: Windows 독립 창 시안

`prototypes/desktop-lab/`에 Qt Widgets 기반 전처리·실행기·후처리·최적화·전문가·Workbench를 구현했다. 공통 실행 파일을 앱별 인자로 별도 프로세스에서 시작한다. 브라우저·WebView·로컬 HTTP 서버를 요구하지 않는다. `PRODUCT.md`와 `DESIGN.md`는 기존 명세와 사용자 거부 사유에 연결된 짧은 UI 기준이다. 설치한 frontend-design, Impeccable의 도메인 중심 구성·Operate·정보 밀도·조작 상태 기준을 적용했으며 외형의 독창성이나 마케팅 화면을 목표로 삼지 않았다.

| 확인 항목 | 실제 관찰 | 판정 범위 |
|---|---|---|
| Windows 실행 파일 | 6종과 Workbench r1의 offscreen 시작 7/7, Qt Widgets 로드. 복사된 bundle 457개 파일의 SHA-256 일치 | 설치된 Python/브라우저 없이 여섯 종류의 별도 프로세스·창을 실제 시작 |
| 전처리 → 실행기 | 재료 E210→205 GPa 편집·저장 r2·닫기·재실행에서 205 복원. r2를 실행기에 전달, 시연 R001의 24회 반복과 잔차·로그·입력버전2 표시 | 실제 문서/프로그램 전달. 솔버 계산은 시연 |
| 후처리 CSV | 네이티브 파일 대화상자에서 세미콜론 CSV 선택. 2열 시간[s]/3열 하중[N] 매핑→4행 0/10/20/25 N 곡선→r2 저장. 저장 파일의 열 선택·단위·수치 확인 | 실제 파일 읽기. 필드가 없는 곡선에 남던 필드 안내는 수정 후 화면 재확인 대상 |
| 최적화 | 두께 하한1→1.5 mm 수정→시연 DOE 생성→산점도 C003 클릭→표·속성 변경→r2 저장 | 트리와 선택 점 강조가 빠진 것을 발견해 수정. 수정된 exe의 화면 재확인 대상 |
| 전문가 | 참여로 일시정지→추가 관측 입력·전송→이어가기→다음 발언. 사용자 발언6을 참조하는 진행자 발언7과 근거 표시. r2 저장, 1100×760에서도 입력/전송 유지 | 실제 대화 문서/참여·근거 조작. 고정 시연 발언이며 LLM 미연결 |
| Workbench | r1 고정 프로젝트에서 변경 영향 확인→Pre 현재r2/고정r1·하위 입력 변경 표시→정확 r1 전처리 열기→E210 GPa·읽기전용 확인→프로젝트r2 저장 | 정확한 버전과 이전 결과 보존. 가려진 시스템 제목·트리 선택 동기화를 수정 후 화면 재확인 대상 |
| 파일 계약·독립 검토 | 실제 임시 파일의 저장·불변 과거 버전·오래된 revision 저장 거부·정확 ID/revision 경로 복구, 입력 지문 검사. 독립 검토 지적 6건 수정 후 재확인 | 프로세스 간 동시 저장 잠금은 제품 구현 대상. 코드/화면 검토가 사용자 수용을 뜻하지 않음 |

실제 기본 창 캡처는 외곽 1482×972(클라이언트 1480×940), 전문가 작은 창은 외곽 1102×792(클라이언트 1100×760)다. 화면 잠금 해제 후 여섯 앱을 직접 조작했고 저장된 창을 닫았다. 독립 검토자는 Pre 재료/고정 버전, Runner 수렴·로그, Expert 대화/작은 창의 실제 캡처를 확인했다.

실제 캡처: [전처리 E205](../prototypes/desktop-lab/evidence/pre-material.png), [실행기](../prototypes/desktop-lab/evidence/runner-result.png), [고정 r1 E210](../prototypes/desktop-lab/evidence/workbench-pinned-pre.png), [전문가 대화](../prototypes/desktop-lab/evidence/expert-chat.png), [전문가 작은 창](../prototypes/desktop-lab/evidence/expert-small.png). 독립 검토자는 이 다섯 캡처와 최종 교정 소스에서 새 진행 차단 결함을 발견하지 못했으며, 최신 교정 화면과 나머지 다섯 작은 창 검수는 OPEN으로 남겼다. 전체 UI 통과·사용자 수용 판정은 하지 않았다.

**남은 화면 검토:** 최신 선택 강조·필드 없는 상태·Workbench 제목 교정은 새 exe에서 재확인해야 한다. 나머지 다섯 앱의 작은 창, 닫은 문서들의 최종 재개, 필드 표시/추출 및 두 창 충돌을 실제 UI에서 확인한다. 최종 실행 파일 교체 후 `GetCursorPos: 액세스 거부`로 Windows 화면 접근이 다시 막혀 사용자에게 잠금 해제/활성 상태 유지를 요청했다. 이 미확인 범위는 내부 자동 검사로 통과 처리하지 않는다. 사용자 수용은 대기다.

최신 실행 패키지는 457파일·240,525,908바이트이며 exe SHA-256은 `0BB4C4CEFF0CCEC5E08EF4BF6FC902A8B84C735EE4B7A9248CA083896D187BB1`이다. 실행 파일 시작/무결성 검사는 실제 화면 검사를 대체하지 않는다.

### 거부된 웹 방향에서 확인했던 실행과 화면

| 기록 | 환경·행동 | 기대와 실제 관찰 | 증거와 남은 문제 |
|---|---|---|---|
| V00 기존 앱 시작 | Windows native Python3.12 private venv, loopback8766 `/workbench`. 실제 Codex 내장 브라우저 기본1021×1244 | 메뉴·시작 카드가 렌더됨. 서버 `/api/overview` 200 | 로컬 PC 실행이며 Cloud 아님. 기존 앱은 여섯 독립 프로그램이 아님 |
| V01 기존 파일 작업 클릭 | 시작의 시험·해석 파일 읽고 비교 클릭 | 파일/열 매핑·작업기록·결과가 긴 세로 구역으로 함께 나타남. 중앙 대상/객체 트리 없음 | [기존 화면](../prototypes/design-lab/evidence/current-data.jpg). 응답열 속성에 가로 스크롤, 결과가 화면 아래. 이 구조를 새 시안에서 교체 |
| V02 실제 입력 반영 | 축 이름 `time`을 `strain`으로 입력 | 화면 입력값과 포커스 변화를 캡처 이미지로 확인 | [입력](../prototypes/design-lab/evidence/current-input.jpg). 파일을 계산한 증거는 아니며 화면 접근·입력 시험 |
| E01 CSV reader | 한글 헤더 시간/하중, axis s·force N·z·support 명시 | 실제 `[0,10,20] N` 읽기 | `work/code-reuse-smoke/`, 재사용 문서에 입력·API 기록 |
| E02 FELUPE 저장·재열람 | E1000MPa, nu.25, constrained strain.001 | 실제 stress_xx `[0,1.2] MPa`, save/read_result 동일 | 재료점 연결 시험. native FE 전체 검증 아님 |

### 거부된 웹 시안의 조작 기록 — 새 데스크톱 검증으로 재사용 금지

시안은 Windows의 Python 표준 라이브러리 서버 `127.0.0.1:8791`에서 실행했다. 다섯 앱을 Workbench보다 먼저 직접 열어 문서를 만들고 작업·저장·닫기·최근 문서 재개를 수행했다. URL 개수가 아니라 이 행동과 디스크 파일로 독립 문서 수명을 확인했다. 서비스 재시작 후에도 저장 문서를 열었다. 대규모 계산/LLM은 아래처럼 명시한 시연이며 제품 엔진 연결 시험 E01/E02와 다르다.

| 기록 | 실제 조작 → 기대 | 이미지와 관찰·수정 |
|---|---|---|
| V03 전처리 | 새 문서→점3 Y .41→.46→저장r3→닫기/재개. 구간 .2~.6 생성→조건 연결. 중앙 점5 클릭 | [전처리](../prototypes/design-lab/evidence/pre-selection.jpg). tree·curve·property 값 일치, 실제 디스크 재열기 확인. native prompt 미지원, input 저장 누락, blur 포커스 소실을 발견해 HTML dialog/입력 반영/부분 렌더로 수정 후 재시험. 조건 기본 대상도 현재 구간으로 변경 |
| V04 실행기 | 전처리r4를 케이스 전달→입력검증→시연 실행→고정 r4·수렴/로그→닫기/재개→후처리 | [실행기](../prototypes/design-lab/evidence/runner-result.jpg). run-iawyo50과 입력r4 보존. solver 호출 안 함을 화면 표시. 실제 job 취소/실패·checkpoint는 D05 구현 합격행동으로 유지 |
| V05 외부 결과 | 한글 `시험_힘.csv` 실제 파일 선택→시간/하중, s/N 매핑→0/10/20 곡선→저장·닫기·재개→CSV 추출 | [외부 결과](../prototypes/design-lab/evidence/post-import.jpg). 원 solver 없이 값 보존. 잘못 남던 σxx/범례0..1을 실제 채널·표본3·범위0..20N으로 수정·재검증. 추출값도 0/10/20 일치 |
| V06 필드 | 내장 시연 field→σyy/frame2→중앙 셀8 선택→저장 | [필드](../prototypes/design-lab/evidence/post-field.jpg). 위치8·σyy 0.469MPa 선택과 트리/속성 일치 확인. σxx 값이 그대로 보이던 문제를 시연 성분별 값으로 고쳤고, 실제 데이터가 없는 온도/변위 옵션을 제거했다. 실제 solver field reader 연결을 증명하지 않음 |
| V07 최적화 | E 범위650~1550 편집→시연DOE→저장/닫기/재개→c-03 선택 | [후보](../prototypes/design-lab/evidence/opt-candidate.jpg). 후보/속성 연동. 처음에는 절차 아래에 후보가 가려져 평가절차/설계공간/비교 탭으로 수정. 시연/가져온 값 출처 구분. 산점도 눈금·겹친 라벨은 후속 가독성 개선 |
| V08 전문가 | 일시중지→'속도2배 때 피크차이, 온도동일' 사용자 개입→이어가기→시연응답→저장/닫기/재개 | [대화](../prototypes/design-lab/evidence/expert-chat.jpg), [작은 창](../prototypes/design-lab/evidence/expert-small.jpg). 사용자 메시지m-gustkga→reply m-lexowsg 보존. 입력란이 진단 아래 가려지는 문제를 timeline 내부 스크롤로 수정. 1440×900 및 실제1100×760에서 입력/전송 노출 재검증. 고정 응답·실LLM 미연결 명시 |
| V09 Workbench | 별도 프로젝트 생성→전처리r4/실행기r4 등록·연결→저장→전처리수정r5→영향확인→정확r4 열기→프로젝트닫기/재개 | [연결](../prototypes/design-lab/evidence/workbench-stale.jpg). 해당 연결 stale, 이전결과 보존. 과거r4 문서 값.46·읽기전용, 현재r5 값.49 구별. 자동 새 실행 없음. 시안은 수동 영향확인, 제품 저장이벤트 반영은 D11 |
| V10 충돌 | 동일 전처리r5 두 창→첫창r6 .50 저장→둘째창 .48 저장 | [충돌](../prototypes/design-lab/evidence/save-conflict.jpg). 409 대화상자에 편집r5/디스크r6 표시, 둘째 편집 보존·저장중단. 디스크 재열기 복구 확인 |

주 담당이 위 조작과 실제 이미지 확인을 수행했다. 보조 A는 코드·재사용·개발 도구, B는 화면명세와 시안을 작성했다. A 완료 후 별도 독립 검토자(Astra High)가 요구·명세와 6개 도구의 실제 캡처를 대조했다. PDE/재료점/UQ/대리/비교/전문가 권한·단독 bundle 위치 명세 누락 및 V05/V07/V08 화면 결함을 지적했고 수정본을 다시 읽고 이미지로 확인했다. 중대 잔여 결함 없음이라는 판정은 **이 기획·핵심 시안 범위**이며 검토자가 동일 UI 조작을 재실행했다는 주장은 아니다. 보조 동시2개 이내, 파일 소유 분리, 재귀 위임 없음.

### 이전 판정 기록과 다음 구현 — UI 완료 철회

전체 구성, 화면별 명령/상태, 독립 저장/연결 계약, 재사용 결정, 조작 가능한 핵심 시안과 위 관찰, D01–D12 코드경로별 인계를 작성·검토했다. 실제 제품 전체는 미완성이다. 제품 bundle 저장/파일 연결, VTK 등 실제 mesh/field reader, native solver 자격 검증, live LLM, 모든 UQ/약형식 GUI는 후속 본 구현 대상이다. 시안의 단일 JSON·SVG·고정 응답과 제품 목표의 차이는 README/화면명세에 남긴다. 미지원 기능을 실행 가능으로 가장하지 않는다.

추가 검사: B의 짧은 API 시험에서 저장·409·과거 revision·표시만 바뀐 내용 지문 동일·잘못된 ID/경로 거부를 확인했다. JS/Python/PowerShell 구문 검사와 다른 데이터 폴더를 사용하는 서버에 런처 연결을 거부하는 실제 시험이 통과했다. UI 관찰을 이 검사 수로 대체하지 않는다.

요청 개발 도구는 별도 `DEVELOPMENT_SKILLS.md` 5절에 설치·호스트 발견·호출을 구분했다. research/grill-me/grilling 원문 설치, Ouroboros HTTP MCP 36도구와 읽기 조회 성공을 확인했다. 기존 CLI 호환 문제는 작업 폴더의 새 CLI로 우회했다. 현재 Desktop의 새 스킬 자동 발견, 실제 모델 작업, 네이티브 Windows 실험 상태는 성공 범위를 넘어가지 않는다.

## Windows installation and usability continuation — 2026-10-08

Product source `6d9909f830b50f924d17ff8e3278dad9a491bd50` adds the actual
online Windows path and guided workflows after PR #3 was merged as `59577ed`.
The user's priority is Windows without WSL, then a future Linux server connection.
Offline distribution is a design consideration only: no bundle was implemented.
[Windows quick start](WINDOWS_QUICKSTART.md) gives the double-click entry and scope.

- `Start-CAE-Lab.cmd` reuses fixed, hash-verified uv to install private Python3.12
  and numerical/material packages. Actual stock PowerShell5.1 tests cover a fresh
  managed interpreter, a source ZIP without the upstream submodule, spaced/trailing
  paths, same-store reopening, different-store rejection and an owned explicit stop.
  No WSL, preinstalled Python, Git or admin rights were used by this bootstrap.
  uv's minor-version junction check failed on this host after unpacking Python;
  the completed private interpreter was verified and used directly. There is no
  silent fallback to system Python. Exact uv0.12.19/Python3.12.14 receipts remain.
- Root reran the final script and real HTTP FELUPE job
  `J0ec1660e55614a24bef499ba902de25e`: 1.2MPa agrees with the analytical constrained
  Hooke response for E1000MPa, nu.25, strain.001. An independent installed-wheel
  test outside the checkout also passed CSV/FELUPE/SciPy LHS/HTTP. That immutable
  wheel predates final UI edits; it is packaging evidence, not a new solver result.
- The Windows browser actually changed E to1500MPa and submitted named job
  `Ja80b7371342148b0b23ad678a1fc6a6f`; stress_xx is [0,1.8,3.6,5.4]MPa. The final
  source was restarted and the same result reopened. Expert follow-up selection
  opens the proper panel with that result selected; no model call was made in this
  fresh, deliberately unconfigured installation.
- Actual file chooser uploads of two Korean-header CSVs in a fresh store used
  explicit axis/units/component/location, produced two real imports and comparison
  `J842ff29e5d764a00a7dcbd739dc97ac3`: RMSE .1095445115N and MAE .08N. Both curves
  overlay; a selected three-row report window contains three samples per curve.
  The UI explicitly says error metrics belong to the whole five-sample comparison.
- Independent review caught a first-row NaN/Inf being guessed as a header. The
  corrected preview preserves numeric invalid rows, rejects ambiguous mixed rows
  as a suggestion, aligns BOM/`#` comments with NumPy and declines unsupported
  quoting/solver-block formats. The real reader remains authoritative and rejects
  invalid values. Units are never guessed. File names and user research names now
  distinguish jobs; internal IDs/raw values remain available in details.
- CAD linkage was separately exercised using the existing integration: an editable
  public FCStd length changed12→16mm, new revision `E-native-box-revision-r01`,
  volume1280mm3, 905 C3D10 elements/1714 retained nodes, actual Gmsh/CalculiX solve,
  matching native revision/export/input, analytical normalized error3.4983e-7
  under the unchanged1e-5 gate. This is one supported solid, not arbitrary CAD
  feature reconstruction or generic-CAD shape optimization qualification.

Final Windows repeat: actual two-file comparison `J2026025f383c4dfea14e61e312bff955` reproduces the same errors and five samples in the private Windows store. Browser inspection found grid min-content overflow; the CSS follow-up permits columns to shrink. Measured document width now equals viewport width (1265px), with both curves visible. The extra public screenshot records this final view.

Validation: **121 Python workbench tests and19 Node UI tests passed**. Independent
UI/parser and Windows launcher reviews closed their bounded findings. Windows CI
now includes table-preview regressions and the actual private-runtime HTTP smoke.
CI for this new commit is separate from the previous source verification below.
The merged59577ed run37674032477 finished9 successful jobs and Code_Aster failed;
no new canonical solver success is claimed by this UI/installation change.

Final product source is `a06b747729cce7cec169281747bcfc2b248a0f13` (the
`6d9909f` implementation plus the bounded grid correction).
[PR #4](https://github.com/pikachu444/autonomous-cae-lab/pull/4) carries this increment.
Exact [CI 37696870570](https://github.com/pikachu444/autonomous-cae-lab/actions/runs/37696870570)
completed **Core PASS: 6590 Python tests, 10 skipped**, and **Windows PASS: 121
Python / 19 Node tests plus fresh private-runtime HTTP calculation**, before this
documentation checkpoint. CI job `J5954f8a33ae6498a9c52449a80418b68` produced
1.2MPa. Tested PR merge `02717bc83a7270b56547a8a73ad574499b3f4349` and the source
head have identical tree `d8cefb53e6e5aa2e6c191030ce42c6188450170d`.
Native jobs were still running at this checkpoint; no overall workflow or new
canonical solver PASS is claimed. Subsequent evidence/documentation commits do
not change the tested product source or constitute another solver verification.

Evidence, hashes, precise limitations and retained stores:
[`20261008-windows-usability.json`](../benchmarks/records/20261008-windows-usability.json).
The public UI snapshot and three screenshots contain only synthetic verification
data. Private install logs and original run artifacts remain local. The existing
52-section requirements and Code_Aster F05/physical/company release gates remain
open as previously recorded. Basic Windows installation does not certify every
native backend on Windows. Continue with those explicit gaps; a merged usability
bundle is not whole-system completion.

## Scope status for the R1–R5 continuation

| Area | Actual status and boundary |
|---|---|
| R1 local runtimes | Actual small computations run for each configured backend. OpenCourant download/qualification and PDE convergence are repaired. Canonical Code_Aster F05 remains OPEN under unchanged gates. |
| R2 shared responses | Native transient fields/histories and real external ASCII feed selection, comparison and numerical research; retained results reopen without the original solver. |
| R3 research/expert | Actual authorized OpenScience host reads, editable bounded DOE, numerical interpretation, limited testing consultation and follow-up comparison are proven below. Model errors and their corrections remain recorded. |
| R4 numerical execution | Real two-property/multiple-history MFront fit and holdout, two-worker execution/cancellation and measured preparation/read costs are retained. Broader material-law qualification is not implied. |
| R5 user path | Actual file/native/expert screens, restart, result reopening and report preview are exercised. IAB download delivery itself remains unconfirmed. |

This is a partial project completion with the listed connections verified;
canonical Code_Aster and engineering/company release remain open. A–F describe
bounded real user workflows, not support for every material law or file format.

## Exact source validation and integration

Product source is `9d0aeed3cef9c7f353bb2c907a5f789b65d88f63`.
CI run [37665791166](https://github.com/pikachu444/autonomous-cae-lab/actions/runs/37665791166)
finished with **9 successful jobs and Code_Aster failed**. Core passed 6575 tests
(10 skipped); Windows workbench passed 106. The tested PR merge commit was
`f9a5abfe72fe0309fec8b27d3b32d533c4160563`; its tree
`843650e54e8977cde216d8f636e5fe4c012f2ad0` exactly equals the source-head tree.
The Code_Aster worker is unchanged from base `afcfd27`; canonical Fz remains
rejected, so this is not an overall green workflow or engineering approval.

Optimization's first runner was cancelled after about 22 minutes in package
index update, before any solver execution. Its isolated retry completed the
actual numerical benchmark successfully. The same local benchmark also passed
in fresh `workbench-optimization-9d0aeed-20261008-01`: 9 evaluations, 8 structural
children, 2 saved evaluations resumed without rerun, invalid CAD blocked and
unchanged CAD/solver input identity checked. Baseline volume 36783.82988 mm3
reduced to 28185.59319 mm3 under the declared displacement screen; this bounded
one-generation search is not a global optimum or physical release. Original
receipt/hash and 1.337 GB of local artifacts are retained. Its dirty flag records
staged documentation/evidence; product source remained identical to 9d0aeed.

[PR #3](https://github.com/pikachu444/autonomous-cae-lab/pull/3) is the publication
and integration pointer. Subsequent documentation/evidence commits are not new
solver verification. Raw runs are local; CI artifacts have 30-day retention.

## Verified live research chain — 2026-10-08

The optional OpenScience 2.0.146 provider uses the existing approved ChatGPT
OAuth profile and `openai-codex/gpt-5.6-sol`. It now connects through the official
SDK's authenticated, ephemeral loopback Streamable HTTP MCP server. A Windows
stdio host startup race was reproduced; the installed runtime was not patched
or its process ownership checks bypassed. Temporary configuration exposes only
scoped tools and disables unrelated deliverable/acceptance/review continuation
harnesses. Exact result/document scope remains enforced by Core callbacks.

- D: GUI expert job `Jba9efaca329c4ba7a5baae3213de7d99` read the selected local
  document and one actual public abstract (doi:10.2478/sgem-2025-0008), inspected
  registered inputs, and proposed DOE8 through five real tools. The operator
  edited mass to 1.2 kg, stiffness upper bound to 130 N/m and seed to 41 in the
  form, then ran `Jaad26b66365245399a1fb91113c779b8` (8 real external DOP853
  evaluations). Analysis `J29e8f4c5acc747b28312a62886ebcfc7` computed force
  abs_max 0.5044949266–1.1935027409 N, normalized stiffness/damping regression
  coefficients 1.0000000000 / 3.14e-16, and two-point holdout RMSE 2.15e-16 N.
- E: `Jd9657039f35a4b9099c58c1cbcec0825` actually read both saved results and
  consulted the authorized testing expert once. It explained the initial-force
  confound, limited holdout and lack of causal/physical proof, then proposed
  the same DOE with initial velocity 0.05 m/s. After bounded GUI authorization,
  `J50df681fd4aa42e79a44cd7e6e8a9ec9` submitted the actual eight-evaluation
  job `J8bbbc7942c9046f9aed41babedbb9193`. Analysis
  `Jcabf6666d9e24925b5135d747fe43ab7` computed force range
  0.7353048127–1.3527743352 N, stiffness/damping coefficients
  1.0990343106 / 0.1465053562, and two-point holdout RMSE 0.00370097494 N.
  These are conditional sample statistics, not invented model influence scores.
- F transport/recovery: after service restart, the same conversation
  `f18e42c48dfd43f187f45ef54ab1528f` used the actual external OpenScience host
  to read the generated DOE through its persisted grant, without adding it to
  the new selected list. `Jdf79a382e204427c99cc833672c71186` made six real
  status/result calls. Its final answer lost useful claims during strict
  citation repair; this failed interpretation is retained. Follow-up
  `J6cd084f4d2cf435db9c7f5f3e1b28a7c` copied the true numbers but wrongly
  claimed mass had changed. Selecting the original DOE as well let
  `J757e599719804e189c3bf5ec11d310bd` reread both conditions and correct
  that claim: both mass1.2 kg, identical eight candidate pairs/seed41, only
  initial velocity0→0.05 m/s changed. Five real tool calls, no new calculation
  or consultation, accepted exact citations and correct coefficient/RMSE
  comparison. SDK-only tests are separate from this actual external-host proof.
- Current remote-host cancellation: GUI job
  `Jaad4a1c294ef496796531e4fbf3adf9c` transitioned RUNNING → CANCEL_REQUESTED
  → CANCELLED (18:06:22–18:06:36 UTC). Owned Windows CLI PID101776 was observed
  before cancellation and absent afterwards; structured host cleanup was
  confirmed. Receipt: local `output/gui-model-cancel-remote.json`.
- B rerun with the newly qualified OpenCourant pin: fresh
  `workbench-native-flow-20261008-06` passed actual PDE33 and explicit200
  selected samples, changed-gravity comparison, PDE self-comparison and
  solver-free restart. PDE `Jcd0169062ba04feb84d0eda001631d98`, explicit
  `Je927911d3989472995e531034a9c9387`, changed gravity
  `Je159c0b46d074f47a3eeb1ee3acd0904`. Previous OpenRadioss22-channel output
  remains readable; the new runtime's23-channel format is separately admitted.
- Actual GUI displays influence statistics, conditional coefficients, heldout
  error and limitations. Report preview uses the same standalone HTML as the
  download action and includes selected study arguments. Saved local evidence:
  `output/ui/actual-influence.jpg`, `research-report-preview.jpg`,
  `followup-research-report.html`, native and file/curve screenshots.
  IAB download delivery itself was not confirmed; displayed report HTML was
  saved directly and visually checked.

The upstream OpenRadioss release URL now returns404. New official community
successor OpenCourant source/runtime pins and clean-source analytical flight
and compliant-contact qualification are documented in
`OPENCOURANT_RUNTIME_QUALIFICATION_20261008.md` / ADR0059. Two rigid-wall tests
remain rejected; unknown physics is not promoted to approval. No republished
third-party release was created. Canonical Code_Aster Fz remains rejected;
MUMPS iterative-refinement probe also failed FACTOR_57 (3.07939e-6 > 1e-6).

Full local regression during concurrent integration: 6541 passed,20 failed,
4 skipped. Failures included source drift during edits, Windows/WSL Git setup,
CRLF-only source fingerprint, a missing ignored artifact folder and process
startup timing. Focused repairs passed; final frozen-source checks and exact
PR-head CI are tracked below. Prior `acbe38c` CI `37656946351`: seven jobs
passed; explicit failed on upstream404, PDE on reaction-case preasymptotic
convergence, Code_Aster on the retained canonical reaction gate. The download
and PDE issues have been corrected without changing numerical limits. Clean
`f64584f` full vector verification passed all6 accepted,3 expected numerical
rejections and5 preflight refusals over27 meshes; exact hashes and retained
coarse failures are in `PDE_VECTOR_PACKET.md`. Independent final Astra High
review reports no remaining actionable blockers after the continuation fix.


Final review also reproduced an upstream continuation issue: the next CLI
invocation automatically resumed the cancelled internal session. The official
`harness.durable-jobs=false` overlay now gates bootstrap `resumeInterrupted()`.
A following actual turn left the still-eligible interrupted session untouched;
its own answer/tool calls completed. No runtime/auth patch or history deletion
was used. Cancellation means owned process cleanup plus no later automatic
revival through this host, not simply a CANCELLED label. The erroneous earlier
mass interpretation and initial citation-repair failure remain visible evidence
that model interpretation needs checking against source conditions.

Current targeted workbench tests: **106 passed**; UI Node tests: **15 passed**.
Committed public synthetic screenshots and standalone HTML report are under
`benchmarks/workbench/20261008/`. Raw provider logs, full result artifacts and
private configuration remain local. Frozen-source replay regressions, final
review conclusion and exact source CI are recorded above and below.


Code_Aster additional isolated probes also retained their failures: exact
Lagrange elimination requires SuperLU absent from the pinned PETSc runtime;
nonsymmetric/full-dual MUMPS estimates were3.69293e-6/3.42181e-6 versus1e-6.
Physically coherent kN/mm and MN/mm scratch variants still failed at finest
mesh (2.90616e-6/2.76773e-6); coarse/middle reaction-resultant drift also exceeded
the original1e-7 gate. No unit rewrite entered the product. The subsequent K/u/b diagnostic below narrows the GCPC reaction failure;
MUMPS conditioning remains a separate unresolved cause.
Exact scratch paths/hashes are in the integration record. F05 remains OPEN.
One further same-mesh GCPC solve captured the actual native assembled K/u/b
(6675 DOFs, 870351 nonzeros) and `REAC_NODA`. Across 2160 free DZ DOFs,
`REAC_NODA` summed to -8.16885e-7 N; assembled residual sums were -1.40610e-7 N
with ordinary sparse float64 matvec, -5.15927e-10 N with row-wise `math.fsum`,
and -8.98256e-9 N with 80-bit longdouble accumulation. Thus ordinary diagnostic
matvec itself has substantial cancellation error. Better accumulation narrows
the dominant GCPC discrepancy to native reaction postprocessing/aggregation;
it does not prove the separate MUMPS FACTOR_57 cause. Code_Aster documents
`REAC_NODA` as Gauss-stress-derived nodal forces minus external loading
([U4.81.04](https://code-aster.org/doc/v17/manuals/man_u/u4/u4.81.04/Operandes_forces_reactions.html)).
The scratch capture and 17.9 MB raw evidence are in `workbench-aster-kub-20261008-01`
with hashes in the integration record. No alternate reaction replaced the
native acceptance value. Next: diagnose/qualify the native reaction accumulation
path and separately resolve MUMPS conditioning, then rerun all original
fields/reactions at unchanged limits. F05 remains OPEN.
### Reproduce on this configured PC

Start `scripts/cae-research-local.ps1`, then open
`http://127.0.0.1:8776/workbench`. The private deployment file restores the same
WSL interpreter, solver roots, store and approved model profile; no credentials
are committed. Direct Python/file workflows do not require an AI/MCP/CAD setup.

The committed `benchmarks/workbench/20261008/live-research-api-snapshot.json`
contains the actual public synthetic job arguments, DOE candidate values,
analysis results, model answers and tool-event summaries. The original public
input document is next to it. Its suggested mass1 kg is not the executed
condition: the operator edited both actual DOE runs to1.2 kg. Original raw
result hashes/paths remain in the integration record. To reopen, choose the
saved job in Results; use row/channel controls for native/large histories.
The same conversation can read its generated jobs through retained grants.
For a new expert run, select the documents/results, allow their transmission,
review its plan in the editable form, and only then enable a bounded calculation.
Exact model wording is nondeterministic and must be checked against the records.

Independent numerical replay commands (each timestamp creates a new store):

```powershell
$tag = Get-Date -Format 'yyyyMMdd-HHmmss'
./scripts/local.ps1 -PythonArgs @('-m','scripts.verify_workbench_external','--output',"artifacts/workbench-external-$tag")
./scripts/local.ps1 -PythonArgs @('-m','scripts.verify_workbench_native_flow','--store',"artifacts/workbench-native-$tag")
./scripts/local.ps1 -PythonArgs @('-m','scripts.verify_workbench_mfront_fit','--store',"artifacts/workbench-mfront-$tag")
./scripts/local.ps1 -PythonArgs @('-m','scripts.verify_workbench_exchange','--output',"artifacts/workbench-exchange-$tag")
```

These programs execute numerical producers and compare actual saved outputs;
they do not replay a scripted model answer. Use a new tag for every rerun and
retain failed stores. Raw local runs are not a managed remote archive.

Frozen-source recheck at `9d0aeed`: all20 failures from the concurrent-edit full
run passed (568.49 s, one CadQuery deprecation warning). The base-only wheel was
built (SHA256 d8a8160df0e58dfaa5889bb9d051419bbe0260214ead3e7f971e4aecbbb27b02)
and installed in a fresh environment without CAD/SciPy/MCP/Haystack/FELUPE;
file registration and bounded result reread passed, and the optional PowerShell
host helper is packaged. This is separate from actual native/model acceptance.

## Earlier 2026-10-08 local integration evidence

Latest-main base is `afcfd27f2ff60c7fac77bbb12c750819702391bf`; exact-base CI
`37643454243` failed. Work is isolated on `codex/workbench-local-integration`;
the original checkout's user edits are preserved. The evidence below was produced
from the dirty integration source and is not exact-commit CI or release approval.

- Actual WSL FEniCSx/OpenRadioss managed jobs, selected common responses, changed
  gravity comparison and solver-free restart passed in
  `workbench-native-flow-20261008-04`: PDE 33 samples and explicit 200 samples,
  explicit changed-gravity comparison and PDE identity comparison.
  The preceding `-01` harness status mistake and `-02` packed-outcome reader
  identity failure are retained; the reader identity defect was corrected.
- Real external SciPy DOP853 process → ASCII → two-coefficient/multiple-history
  fit, independent-history holdout, DOE8 and DE17 passed in
  `workbench-external-20261008-01`. Independent analytical history errors were
  below `3.58e-12 m`; observations are explicitly synthetic from the same law.
- Actual MGIS prepared-library fit through jobs passed in
  `workbench-mfront-fit-20261008-01`: E=274.99999999999994 MPa,
  nu=0.2800000000000008, two fitted histories and separate mixed-history holdout;
  37 updates, 8.52 s preparation and 0.092 s summed candidate execution.
  The prepared product route now uses an operator-registered library/hash and
  does not rerun the fixed package-fingerprint benchmark. Current law coverage
  remains infinitesimal isotropic Elasticity with zero initial state.
- Actual two-worker prepared MFront fit/cancellation passed in
  `workbench-mfront-parallel-20261008-02`: E=275 MPa, nu=.28, 37 model calls,
  independent six-component stress error <=4.44e-16 MPa; 20.37 s fit wall.
  Active DOE cancellation retained 4 successful and 508 cancelled rows and
  closed every owned MGIS child. Five active fit resources and two DOE
  resources were isolated. Peak sum RSS was 387508 KiB (shared pages counted
  repeatedly); child maxrss was 121416 KiB. Verified saved fit/DOE reads took
  .128/.036 s. The preceding `-01` verifier watched the wrong directory and
  missed cancellation; its completed 512-candidate DOE is retained.
  `workbench-mfront-prepared-cost-20261008-01` measured 3.262 s preparation
  and A/B/A calls of 56.3/2.71/1.82 ms, with exact A reproduction.
- Actual external exchange passed in `workbench-exchange-20261008-01`:
  two real program outputs imported, one missing candidate stayed unknown;
  duplicate, changed-value and stale same-case exports were rejected. New
  manifests bind returned rows to an exchange nonce as well as case/values.
  Historical manifests remain readable with explicitly weaker legacy identity.
- Native doctor actual small calculations passed separately for OpenRadioss,
  Code_Aster affine and MFront. Vector PDE finer meshes [16,32,64] pass unchanged
  thresholds; original [8,16,32] remains rejected. Canonical Aster Fz remains
  unresolved: changing essential-condition enforcement did not repair fine-grid
  MUMPS precision or MULT_FRONT reaction balance. GCPC/LDLT_DP with tighter
  1e-12 solver residual also failed the unchanged 1e-7 reaction gate. The
  retained nodal reaction audit shows summed free-node residual explains the
  support imbalance; parser summation is not its cause. No limit was loosened.
- Actual GUI registered an external CSV, mapped units/component/location and
  plotted its 201 samples. It also streamed a Korean-named 25,239,040-byte file
  from an approved root and read 300001 samples. GUI now loads an explicit
  2000-row window, preserving unsliced arrays on disk. Actual GUI PDE run,
  node544 selection (33 samples), explicit run and edited gravity rerun passed.
  Screenshots are under local `output/ui/` (not remotely archived).
- OpenScience 2.0.146 with the existing authorized ChatGPT OAuth profile has
  executed actual MCP tools, local archive lookup and accepted citations.
  First GUI research turn timed out after real literature reads and plan
  creation because nested consultation hit a 60 s MCP timeout. This failed
  turn is preserved. Later runs exposed final-text concatenation, a rejected
  MCP root schema, and a metadata-only citation; all failed runs remain.
  At this earlier checkpoint, canonical DOE planning succeeded but full D/E
  remained pending; the verified later chain above supersedes that status.
  No credentials were extracted.
- Independent Astra High review reproduced and root fixed: penalized failed fit
  reported as success; completed batch results lost on failure/cancellation;
  compact response retention breaking follow-up numerical analysis. Reviewer
  reran all reproductions successfully. Eight new regression cases pass.

All named raw run directories above are under the private local runtime's
`runs/` directory. The private deployment file selects WSL Ubuntu, the existing
py312 environment, service port8776 and `workbench-service-20261008-01`.
`scripts/cae-research-local.ps1` restarts it without manually combining paths.
At this earlier checkpoint, D/E, external host acceptance, GUI comparison/
cancellation/report and final review were still pending. The verified chain
above supersedes those pending statuses; exact source CI/publication is tracked
separately.
Numerical checks never establish physical/material/strength/durability release.

## Prior W1–W5 record

2026-10-07. Based on PR #1 head `90952c5bc1c55da81c4c80b5e266c13339755263`.
This is the single current progress record; historical results and design files
remain intact. W1–W5 code is integrated below. Live model/host/native qualification
and remote merge status are separate from local implementation checks.

## Implemented user outcomes

| Package | Delivered behavior | Verification scope |
| --- | --- | --- |
| W1 | Lazy backend discovery; direct prepared/callable/native execution; solver-independent array records; selectable install; numeric file mapping | Actual FELUPE and text/NPZ imports; clean base wheel; retained native input-rejection contracts |
| W2 | Multi-history fit, independent holdout, DOE/search, stats/regression, UQ, RBF confirmation, matched SALib, epsilon/Pareto, curve/event comparison and identified exchange | Actual SciPy/FELUPE/SALib; explicit synthetic observations; cancellation/budget/process tests |
| W3 | One shared managed workspace through HTTP/CLI/MCP, idempotency, CPU reservations, owned cancellation, interrupted recovery; profile runtime removal | Actual official SDK stdio client queries HTTP-created job; real external process and spawned-candidate cancellation |
| W4 | Versioned original documents, BM25 retrieval, source reopening/revocation, Crossref discovery/read/import; configured experts and bounded consultation/tool loop; editable/executable numerical plans | Actual local retrieval and Haystack Agent with explicitly mocked model; live external connections remain unverified |
| W5 | Editable data/material/fit/DOE/search/UQ forms, actual results/curves/comparison/influence, jobs/cancel, sources/expert plans, fit/holdout HTML reports, optional deployment config | Actual owned Chromium workflow, reports with fit/holdout plots and masked gaps; base-wheel runtime check |

Existing parameterized native adapters join the new numerical path through
`NativeEvaluationFactory`, using the existing `model_parameters.bind` validation
and separate candidate outputs. The factory does not invent parameters for an
adapter lacking `describe_inputs`/`bind_inputs`. Runtime-unavailable single/native
studies still report their actual failure/refusal. Existing Lab/CAD workflows and
scientific reference checks remain available; the original interface uses its
retained Study records, while new workbench clients share the new job IDs.

External solver connection has three explicit modes: importing actual results,
identified candidate exchange, and registered real execution/extraction. Company
commands are operator configuration and stay local to their workspace. Unknown
values and absent returned candidates are not labeled completed. No LS-OPT
installation, LS-DYNA card, company solver execution or qualification is claimed.

## Actual example results

`examples/workbench_numerical.py` generated axial/shear/holdout histories with
FELUPE and recovered **E = 1500 MPa, ν = 0.29000000000000026**. Fit RMSE was
5.95e-15 (axial) and 7.82e-16 (shear); independent-history RMSE was 8.12e-15.
These are synthetic data generated by the same law, so they establish integration,
not identification from measured materials. The two-dimensional callable search
found x = 0.30000055, y = 0.70000237.

For the same 24 material candidates with stress and tangent output:

| Execution | Wall time | Scope |
| --- | ---: | --- |
| Direct FELUPE library | 0.00393 s | No metadata/recording |
| Prepared serial API | 0.03382 s | Metadata/response copies included |
| Two spawned workers | 1.20630 s | Process startup dominates this small workload |
| Serial record / reread | 0.02585 / 0.06954 s | Full selected response arrays; 338 files |

There is no demonstrated process speedup for this small material case. Parent
Python allocation measurements exclude native heaps and child-worker memory.
The measured JSON is retained in `examples/workbench-measured-result.json`;
full local outputs and fit/holdout PNG are under `/tmp/workbench-numerical-w2-final`.
Subsequent review fixes changed cancellation/scope handling, so these timings are
measurements of that example run, not a universal or release-build performance claim.

The reusable `scripts/verify_workbench_ui.py` also ran actual browser flows:
two different synthetic loading histories, fit plus holdout, 8-candidate DOE,
influence calculation, CSV import and downloadable reports. It recovered
E = 1499.999999999978 MPa from initial 900 MPa; the fit report contained both
actual fit and holdout figures. Browser errors: 0. Its own server stopped cleanly.
Evidence is at `/tmp/workbench-ui-reusable-check` in this task environment.

## Removed and replaced responsibilities

The generated OpenScience scenario runtime was retired: `openscience-research.ps1`,
`openscience-native-provider.ps1`, `openscience-server-local.ps1`,
`openscience-local.ps1`, `native_guard.mjs`, `apps/lab/research.py` and the
`lab-openscience.ps1` owner bridge. Dependent frozen-descriptor/source/live-launcher
checks were removed. `cae-research-local.ps1` and `lab-local.ps1` now pass ordinary
workspace/configuration arguments to the shared service. The old authentication
facade only reports migration guidance; no credential/configuration files were
read, rewritten or migrated.

Replacement checks cover current result/document scope, path containment,
request idempotency, controller ownership, actual owned subprocess cancellation,
process-worker cancellation, interrupted recovery, budget/resource limits and
SDK transport. Existing native mesh/domain/process guards remain in their
adapters and existing scientific suites. Generic Git identity code/tests remain.
CI now exercises current workbench behavior in the former source-driver job;
existing native/scientific jobs retain their reference checks.

Independent Astra High review found and integration fixed: cancellation propagation
to spawned evaluators; remote observation path bypass; expert result/status/analysis
scope and transmission; effective resource limits; native thread reservations;
masked-value JSON representation; scientific report omissions; partial-failure
job status; and independent DOE candidate-ID handling for surrogate confirmation.
A further workspace-isolation check prevents external backend configuration from
leaking into another workspace. No reviewer or test establishes live native/LLM
qualification that did not run.

## Validation and external prerequisites

- Full Python regression: **6,537 passed, 10 skipped**, with one existing CadQuery
  deprecation warning (538.57 seconds).
- Workbench targeted suites: **70 passed** after the final registered-callable
  dispatch fix; that fix and its regression test followed the full-suite run.
- A non-UTF-8 locale reproduced a Korean knowledge archive decoding failure.
  Explicit UTF-8 reads now cover document archives, literature caches and expert
  sessions; all **70 workbench tests passed** with Python UTF-8 mode and locale
  coercion disabled. Hosted Windows checks are tracked separately below.
- Node suites: **877 passed**, including 9 current workbench UI tests.
- Actual existing MCP smoke: **passed**, including CAD, DOE/search and native
  preflight refusal. The earlier `report_context` comparison mismatch was fixed
  without discarding checks on the shared result fields.
- Existing HTTP CAD/result/report/ZIP workflow: **passed**. This is distinct from
  the new actual Chromium workbench check, which also passed.
- Final wheel built; a clean base-only installation imported the service, read
  a CSV, saved/reopened its result and constructed/shut down a controller without
  importing or installing CAD, FELUPE, SciPy, Haystack or MCP.
- `pip check` and `git diff --check`: passed.

Live LLM calls, a real product MCP host, external literature access, Windows
PowerShell execution and this session's native FEniCSx/Code_Aster/MFront/OpenRadioss
runs are **unverified**. Mocked model tests use the real agent/retrieval/numerical
tool interfaces but are not live model evidence. The interface reports missing
configuration rather than returning a fabricated expert answer. PDF tables,
figures/OCR, arbitrary native formats, distributed/HPC recovery and additional
constitutive laws are outside this implemented first boundary.

Reviewed implementation was pushed to PR #1's existing branch without rewriting
its earlier commits. GitHub API requests initially returned `Forbidden`; access
became available after delivery, and hosted checks were confirmed running.
Their completion and merge are verified separately from the local results above.
The environment draft preserves package-manager presets and
adds `api.github.com` and `api.crossref.org`, plus updated tested install/start
instructions. Draft persistence is confirmed; application/publication and
fresh-task restoration are not. Review/save and publication are user actions in
environment settings. No branch protection is bypassed or force push used.
