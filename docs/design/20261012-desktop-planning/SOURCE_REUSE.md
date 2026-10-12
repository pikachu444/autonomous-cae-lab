# 현재 소스 재사용과 화면 개발의 경계

기준 `9a6e3083037630b45694b812b135dc1cd63cf95a`, upstream
`3e48bf6138f495299f45b1af254bfb4aaff307b8`. Luna/high의 읽기 전용 조사와
Codex 대조다. source가 있는 것과 실제 사용자 작업이 수용된 것은 구별한다.
이전 실행 사실은 CURRENT_STATE가 가리키는 source/run 기록의 범위에만 적용한다.

| 독립 작업 | 기존 구현·명령 | 추가/수정해야 하는 사용자 작업 |
|---|---|---|
| 직접 실행·파일 열기 | `scripts/start_cae_research.ps1`, `apps/research/desktop.py`, existing Client; Data/Material/PDE/Numerical/Runner/Expert/Study/Simulation/Evaluation dispatch | ID/URL를 사용자에게 입력시키지 않는 최근 파일/열기·동일 문서 활성화·분기/휴대 저장, 종료 뒤 새 프로세스 재개. root 시작기의 옛 웹 기본값 수정은 승인 후 |
| Data | `apps/research/data_window.py`, `caelab/data_document.py`, `data_comparison.py`; `data.update/import`, `document.save/undo/redo`, preview/registration | 열 역할·단위의 지정/수치 변환 구별, 실제 표–곡선 연동 구간/mask 편집, processing recipe·large data. 기존 mapping/retained 결과 보존 재사용 |
| Material | `material_window.py`, `native_material_window.py`, `material_document.py`, FELUPE/MFront evaluators; `material.update/evaluate` | 관측 불러오기→매핑/척도/횡조건→protocol→direct/fit→원본/예측/잔차/holdout→대상 개정 채택→재개. 기존 계수/history/retained curves/Plan/adoption 재사용 |
| PDE | `pde_window.py`, `pde_document.py`, `pde.py`, `pde_results.py`, registered adapters; `pde.update/evaluate` | 모델 노드별 식/약형식·field/space·domain/BC/IC와 selection, solver 설정/기준 비교. 기존 등록 모델 밖 일반 방정식 지원은 별도 adapter 확장 |
| Simulation | `simulation_window.py`, existing Simulation owner and native requests; `simulation.update/run` | FE 모델·frozen deck/native refs, 지원 조건/response 설정, Pre/Runner/Post의 exact revision 이동. CAD가 필요하지 않은 external model도 보존 |
| Numerical | `numerical_window.py`, `request_plan_window.py`, `numerical_document.py`, `numerical.py`, DOE/optimization engines; `numerical.update/run` + candidate adoption | typed 변수/응답·관측·가중치/정규화·method budget, 실패/holdout/순위, sensitivity/UQ/surrogate/MOO의 각 분석과 재개. raw key/object 폼 개선, 기존 engine 교체 금지 |
| Evaluation | **이미 존재**하는 `caelab/evaluation_definition.py`, `apps/research/evaluation_window.py`, Workbench registration; `evaluation.update/run`, `evaluation.coupled` | 기존 단계/전달/반복 editor 보완. 현재 1–32 saved Material/PDE/Simulation stages, exact_same_mesh/명시 metadata, 지원 scalar binding. 열→구조/상태·mapping 일반화는 검증 필요. 새 owner를 다시 만들지 않음 |
| Runner | `runner_window.py`, `jobs.py`, `research_execution.py`; status/cancel/result/navigation | selected attempt의 입력/log/진단, 취소 요청→실제 terminal, 실패 수정→새 attempt, service restart/remote reconnection/long run UX. 창 닫기는 job 취소와 별도 |
| Expert | `expert_window.py`, `discussion_document.py`, `caelab/assist`; `expert.update/ask/intervene/pause/resume/advance` | 논점/자료/역할→actual reply→user 반론→editable Plan→actual retained result→후속 논의. 실제 새 Qt 전체 provider 흐름 미수용. 구독과 유료 API 권한은 동일하지 않음 |
| Study | `study_window.py`, `study_document.py`, `research_context.py`; `study.update`, generic document lifecycle | 독립 질문/경쟁 가설/지지·반박 근거/명시 판단/다음 연구 화면, precise ref·변경 영향. Discussion 발언/Plan 결과가 판단을 자동 채택하지 않음 |
| Workbench 선택 보기 | existing Study/links/service and previous view | optional document connection graph, port/revision/stale/repair, owner 열기. 새 scheduler/optimizer 불필요 |
| CAD/FE Pre | `apps/desktop_pre/*`, native FreeCAD Sketcher/PartDesign/Assembly/FEM, upstream adapters, managed FCStd/save and typed bridge | 자신의 모델 선택·일반 변수·조립/pose·mesh/conditions·contact·참조 복구·저장/재개 전체 흐름. 현재 narrow native 지원을 일반 FE로 과장하지 않음 |
| ParaView Post | `apps/desktop_post/{bridge,commands,workspace,analysis,measurements,source_repair,external}.py`; native pipeline/Apply/Undo, registered source and managed save | reader/field/time/location, native 표/3D selection, filters/curves/measurements, valid mapping/diff, moved dependencies, save/cold reopen. Ctrl+S Save Data와 관리 project 저장 충돌 설계 |

사용자 Python 3.13의 PySide6 `6.9.1`, Matplotlib과 bundled Designer는 실제 확인했다.
`%LOCALAPPDATA%/AutonomousCAELab/windows-runtime/venv`의 Python에는 PySide6가 없다.
제품 runtime에 설치됐다고 보고하지 않는다. FreeCAD/ParaView bundled Qt/Python은 별도다.
새 기술 시제품은 첫 환경만 사용하고 기존 실행 중인 native 문서를 건드리지 않는다.

이 조사는 owner를 다시 작성하는 구현 과제로 옮기지 않는다. 데이터/단위·지원 law·port·
session/generation 의미는 현재 코드를 Pro에게 전달해 상세 UI와 일치시켜야 한다.
이전 계획 §10/§11의 신규 분류는 작성 시점의 계획이고 위 기준 코드에서는 재사용/확장으로 읽는다.

## Expert의 비용 없는 연결과 추가 설계

Luna/high의 제한된 재조사(2026-10-13)에서 관련 Expert 소스는 위 제품 기준과 같았다.
`caelab/assist/experts.py`의 RuntimeConfig와 `openscience_host.ps1`은 명시한
`openscience` / `openai-codex/<model>`을 기존 로그인 프로필의 구독 인증 경로로 전달한다.
실제 계정·모델 사용권은 따로 확인해야 하며 구독을 API 사용권으로 설명하지 않는다.
기본 `OPENAI_API_KEY`를 요구하는 원격 OpenAI-compatible 경로는 이번 비용0 범위에서 제외한다.
명시한 local endpoint와 빈 credential_env를 쓰는 일반 adapter는 있으나 특정 로컬 모델의
도구 호출·설치·서버 수명·사용성 검증은 없다. 검증된 로컬 제품 기능으로 표시하지 않는다.

새 Expert 화면은 역할과 모델을 분리하고, 설정된 구독 인증/기존 무료 local endpoint와
미설정을 구별해 선택하도록 설계한다. 선택 가능한 모델의 실제 사용권 확인과
연결 상태를 보여주되 질문·사용자 발언·계획 편집을 막지 않는다. 실제 실행은 기존
Discussion 명령과 managed ask JobManager로 이어진다. 새 provider 호출·인증 변경은
이번 읽기 전용 조사에서 수행하지 않았다. 유료 API fallback을 추가하지 않는다.
