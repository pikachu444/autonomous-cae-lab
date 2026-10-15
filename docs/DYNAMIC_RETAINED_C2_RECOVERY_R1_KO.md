# 구조·동해석 retained C2 — R1 기록 복원본

요청: PRO-NS2-N3-RETAINED-RESULT-C2-20261015-01-R1

## 상태와 회수 근거

**RECOVERED_RECORDED_SOURCE / DRAFT / NOT_A_COMPLETED_C2_DELIVERY.**

R1 첫 도구 호출은 정상 반환됐다. 원 첨부 두 ZIP과 Numerical 공식 ZIP들은 존재했지만, 이전 작업 경로 `/mnt/data/ns2c2` 및 구조 C2 최종 ZIP은 현재 runtime에 없었다. 대화 첨부 목록과 접근 가능한 작업 경로에서도 구조 C2 최종 patch/로그를 회수하지 못했다.

대신 이전 도구 호출 기록에 남은 세 파일의 작성 본문과 기존 파일 수정 명령을 회수했다. 이 명령을 첨부 baseline의 별도 복사본에 다시 적용해 마지막으로 기록된 소스 상태를 복원했다. 새 물리/통계 엔진, 수치 기준 변경, current main 추측 복원은 하지 않았다. 옛 최종 ZIP의 바이트 동일성을 주장하지 않는다. 원 작업파일 해시가 없으므로 이번 해시는 **R1에서 실제 복원·검사한 파일**의 해시다.

기준은 Git archive comment로 확인한 `35a91ed5d882d63e83118e79e55844083eb7f093`, submodule은 `3e48bf6138f495299f45b1af254bfb4aaff307b8`이다. `source-hashes.json`의 14개 값 중 11개는 baseline과 같고, `dynamic_restart.py`, `dynamic_results.py`, `calculix_dynamic.py` 3개는 다르다. 이 차이를 몰래 보정하지 않았다. 이 복원본과 patch의 기준은 Git archive baseline이다. 상세 해시는 BASE_AND_FILES.json에 있다.

## 복원한 소스와 연결

`dynamic_result_store.py`는 기존 attempt 안에 작은 `dynamic_result.json` index와 `dynamic-frames/topology.json`, 프레임별 JSON을 보관한다. `load_result(..., metadata_only=True)`는 index를, 일반 `load_result()`는 dict 호환 lazy frame reader를 반환한다. 프레임을 선택할 때 그 artifact의 byte/hash와 결과 identity를 확인한다. v1은 기존 bounded JSON 경로로 읽는다. 단일 파일 한계를 늘리지 않았다.

`dynamic_results.py`는 기존 DAT 문법을 순방향 `iter_energy_blocks`로 분리한다. 수치·raw token·행 번호·적분점 identity·결측 의미는 기존 코드를 재사용한다. `bundle()`은 v1 collector로 남아 있다. `read_attempt()`는 새 저장 reader에 위임한다. lazy 결과를 수정해서 비교할 필요가 있는 호출자는 `deepcopy()`로 명시 materialization을 해야 한다.

`dynamic_execution.py`와 `contact_fem.py` integration hunk는 owned command가 반환/종료한 직후 기존 `contact_execution.json`에 native terminal 정보를 저장한다. heavy FRD/Post 이전의 기록이다. `read_terminal(attempt)`는 solver를 실행하지 않는다. 실제 프로세스 종료와 분석 종료, 결과/후처리 상태는 별도 필드다.

`dynamic_recovery.py`의 `reprocess(attempt, output, expected_sources=...)`는 원 attempt 외부의 새 디렉터리에 pinned 입력·출력을 복사하고 읽는다. ccx 실행기는 호출하지 않는다. 기존 기록이 없는 legacy 출력은 명시 source pin을 요구하며 원 상태를 UNKNOWN으로 유지한다. 이 API가 있다는 것과 모든 취소/대용량/통합 경계 검증이 완료됐다는 것은 다르다.

`dynamic_locations.py`, `dynamic_post.py`, `adapters/dynamic_fem.py`에는 index/frame dependency와 기존 origin/clock 연결이 복원됐다. 공유 변경은 `adapters/contact_fem.py` 하나이며 전체 파일 대신 integration.patch로만 제공한다. GUI, Workbench, storage, registry, Numerical/Data/Expert/M4 코드는 수정하지 않았다. 공통 legacy Post 생성 경로는 여전히 남아 있다. 중복 생성·성능 요구 전체의 해결을 주장하지 않는다.

`dynamic_restart.py`에는 기록에 남은 Fortran INT형 해석 교정을 복원했다. 양/음 byte order, record 길이, 전체 payload 검사를 우회하지 않는다. `compare_continuation`과 `compare_saved_states` 함수 AST는 baseline과 같다. 비교 허용치·물리 수용 기준을 새로 선택하거나 완화하지 않았다.

## 적용 순서 — exact baseline의 독립 검토 폴더

이 ZIP은 전체 저장소가 아니다. baseline archive를 별도 폴더에 풀고 pinned submodule archive를 `plugins/fixture_design/upstream`에 배치한다. 복원본 `caelab/` 전체를 다른 팀 작업폴더에 덮지 않는다.

1. `product.patch` check/apply: 전용 소스 8개, 기존 테스트 수정 1개, 이 R1 설명 파일.
2. `integration.patch` check/apply: 공통 contact adapter 1개 파일의 hunk만 적용.
3. BASE_AND_FILES.json의 기준/결과 hash를 대조한다. 현재 root WIP에서는 Codex/root가 해당 hunk를 수동 통합한다.

예시(경로는 회수 위치에 맞춘다):

```text
git apply --check <R1_PACKAGE>/product.patch
git apply <R1_PACKAGE>/product.patch
git apply --check <R1_PACKAGE>/integration.patch
git apply <R1_PACKAGE>/integration.patch
```

두 patch를 적용하는 경로와 전용 파일을 직접 복사하는 경로를 중복 실행하지 않는다. 이 R1 patch는 Numerical C2에 적용하는 패치가 아니다.

## 실제 읽기 API

```python
from caelab.dynamic_result_store import load_result, frame_metadata
from caelab.dynamic_results import read_attempt
from caelab.dynamic_execution import read_terminal
from caelab.dynamic_recovery import reprocess

metadata = load_result(attempt / 'dynamic_result.json', metadata_only=True)
result = read_attempt(attempt)       # 원 attempt의 result/source/artifact pin 검증
locations = frame_metadata(result)   # 프레임 배열을 선택하지 않는 metadata
frame = result['frames'][frame_index]
terminal = read_terminal(attempt)    # native/후처리 상태 읽기; solver 호출 없음

# 명시 복구만 새 파생 디렉터리를 만든다. 원 입력/출력/job을 덮지 않는다.
receipt = reprocess(attempt, new_output_directory)
```

CLI는 `python -m caelab.dynamic_recovery --from-attempt <ORIGINAL> --output <NEW>`이다. legacy 원 기록이 없는 경우 `--expected-sources <JSON>`을 별도로 제공한다. 성공한 새 solve를 만드는 명령이 아니며 readback_status와 execution_status를 각각 확인한다. failed partial, 단계 양끝 derived A의 결측, native RF의 구속 DOF 의미와 에너지별 association을 기존처럼 유지한다.

## 실제 검사 / 실패 / 미회수

R1에서 복원한 Python 10개 문법 검사를 수행했다. 별도 새 baseline에 product/integration patch를 적용해 결과 파일 hash를 대조했다. 자세한 기계 판독 결과는 BASE_AND_FILES.json 및 r1_checks에 있다.

기존 `test_dynamic_results.py`, `test_dynamic_restart.py`, `test_dynamic_correction_post.py`의 소형 검사 결과는 **35 passed, 1 failed**, exit 1이다. solver 대역과 실제 기존 Python 저장/reader를 사용한 새 R1 검사다. Windows 결과나 이전 C2 검사로 재명명하지 않는다.

실패: `test_partial_result_keeps_failure_and_missing_boundary_acceleration`이 `dynamic-post/source/dynamic_result.json`을 직접 JSON으로 읽어 `frames[0]['acceleration']`을 찾다가 KeyError가 발생한다. v2 index에는 acceleration payload가 직접 들어 있지 않다. 회수 범위에서는 이 테스트나 consumer를 새로 고치지 않았다. 기존 small-cache와 모든 consumer 호환 완료라고 표시하지 않는다.

첨부 실제 `contact.rout` 2,010,796 bytes를 snapshot/STA와 함께 read-only 검사했다. 2개 checkpoint(0.002, 0.004)를 읽고 원본 hash 불변을 확인했다. 이것은 **설치 Windows binary로 새 WRITE/READ를 실행한 증거가 아니다.**

이전의 `first-tests.log`, `second-tests.log`, `regression-early.log`, 최종 패키징/400-frame/cold 로그의 실제 파일은 회수하지 못했다. 호출 기록의 일부 실패 출력은 별도 관측 메모로만 남겼다. 최종 C2 pass 수나 400-frame 합성 크기/성능 수치를 재구성하지 않았다.

NOT_RUN: Windows native, 실제 READ, 원 전체400프레임 읽기, 400프레임 synthetic size double, 전체 solver 캠페인, 물리 수용, 전체 GUI/HTTP/등록 인수. 새 coordinator/형식/engine을 작성하지 않았으며 C2 전용 전체 반례 테스트 묶음도 회수하지 못했다. 원 FN16/17, E3–E6/C1–C6, broader law/contact 물리 수용은 그대로 잔여다.

## Windows 통합 후 확인 — 복원 당시 검사와 구별

Codex가 현행 소스에 전용 파일과 root 공통 hunk를 통합하고, 위 partial-result 테스트의 직접 JSON 접근을 실제 `load_result()` 소비로 교정했다. 경계 A의 결측과 FAILED/UNKNOWN assertion은 유지했다. 결과창의 단계 표도 `frame_metadata()`로 연결해 이력 표시와 별도로 모든 프레임 JSON을 다시 읽지 않는다. 원 결과 선택·한글·두 창 크기의 키보드 선택은 기존 Qt 경로를 유지한다.

Windows의 설치 Python/VTK/PySide6로 기존36, 추가 작은 reader4, 관련 Qt5를 한 영향군집으로 실행해 **45 passed**를 확인했다. 프로세스는 owned Job에서 종료했고 `job_empty`를 확인했다. 계산 프로세스·FRD/DAT/STA/rout는 명시 합성 시험 자료이며 실제 ccx/WRITE/READ 실행은 0회다. Pro의 복원 당시35PASS1FAIL과 합산하지 않는다.

추가 검사는 v1/v2의 같은 원값·시각·결측·에너지, metadata-only와 선택 frame의 lazy JSON 읽기·변조 차단, native 종료 뒤 후처리 실패에도 원 rout 보존, 원 FAILED 상태와 파일을 바꾸지 않는 명시 재읽기를 확인한다. 큰 결과·전체 취소/등록·원400프레임/실제 READ 수용은 여전히 남는다. 특히 `read_attempt()`의 전체 frame hash 선조회와 Post dependency 전수 확인 I/O는 이번 연결 교정으로 해결하지 않았다. 원자료 무결성 검사를 제거해 빠르게 만드는 교정은 하지 않았다.
