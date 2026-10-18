# 계층 INP 가져오기와 기존 해석 연결

기존 Simulation 도구에서 `PART`·`ASSEMBLY`·`INSTANCE`와 중첩 `INCLUDE`가 있는
INP를 가져올 수 있다. 원파일을 보존하고 별도 flat 입력을 생성한 뒤, 기존
INP2RAD 변환기와 OpenCourant 실행·결과 reader를 이용한다. 별도의 parser나
solver를 선택할 필요가 없다.

## 지원 입력과 물리 범위

- 하나의 ASSEMBLY, 미리 메시한 PART와 반복되는 dependent INSTANCE.
- C3D4·C3D10·C3D8·C3D8R 솔리드의 기존 등방 탄성 및 기존 flat 단일 곡선
  PLASTIC 입력, COH3D8의 COHESIVE SECTION·TRACTION 재료.
- 모델 전역 MATERIAL/DENSITY/ELASTIC/PLASTIC와 PART의 명시 section 배정.
  재료명은 기존 flat 경로와 같은 영문 시작·영숫자/밑줄 64자 이하이며,
  PART별 재료 이름공간이나 이름 자동 교정은 추가하지 않는다.
- local/instance/assembly NSET·ELSET 및 ELEMENT surface. Tetra는 S1–S4,
  hex/cohesive는 S1–S6이며 혼합 ELSET의 모든 요소에 유효해야 한다.
- 원 source의 고정 병진 BOUNDARY와 settings.motions의 초기 운동.
  원 INP의 `*INITIAL CONDITIONS`를 직접 읽는 기능은 추가하지 않았다.
  미지원 카드나 옵션을 버리고 해석을 계속하지 않는다.

이 연결은 Abaqus와 native 요소의 적분·재료 응답이 같다는 보증이 아니다.
현재 변환기는 C3D8/R에 같은 native HEPH Isolid24/1 IP를 사용하고,
C3D10은 Itetra10=2/4 IP를 사용한다. 실제 Starter의 resolved property 기록도
확인한다. C3D4 전용 보정이나 시간증분 규칙을 다른 요소로 확대하지 않는다.
단일 PLASTIC 곡선은 기존 PLAS_TAB/LAW36으로 연결하며, 별도 INIEVO 손상은
기존 명시 설정과 C3D8/R 제한을 따른다. COH3D8은 기존 LAW59 선행 검사를 거쳐
명시 설정의 LAW117로 연결한다. 새로운 손상 법칙이나 보정값은 생성하지 않는다.

재사용 경계는 [flat 모델과 renderer](../caelab/impact_model.py),
[변환 후 물리 검사](../caelab/adapters/impact_admission.py),
[기존 INP2RAD 고지](../third_party/inp2rad/CAELAB_NOTICE.md)에 있다.

## 원 대상 선택과 편집

원파일·행·include occurrence·PART·INSTANCE·local ID를 유지한다. 화면의
원 집합과 요소를 선택하면 별도 effective ID/집합 키로 정확히 대응한다.
좌표가 같아도 서로 다른 instance의 절점을 합치지 않는다. C3D10의 열 절점
순서는 유지하며, native 순서 변환은 기존 converter에서 한 번만 수행한다.
재료 속성의 원행과 각 section의 원 ELSET·instance·effective 요소 배정도
`source_lineage.json`에 보존된다.

같은 include 파일을 여러 PART가 참조하면 원 bytes 범위 편집은 각 occurrence에
적용된다. 원 bundle은 보존하며 변경은 기존 source edit hunk로 기록한다.
집합 키나 effective 번호가 재사용돼도 이전 운동·접촉·응답·재료 배정을
다른 대상으로 조용히 바꾸지 않는다. 기존 원 대상 검토에서 변경 전후를
확인하고 명시적으로 다시 선택·적용해야 한다. 잘못된 중간 초안은 저장할 수
있지만 실행은 유효성 검사와 원 대상 검토를 통과해야 한다.

## 초기 운동

INSTANCE의 배치는 선언된 이동 후 전역 축 회전 순서로 적용한다. 이후
settings.motions의 자세·이동·속도·각속도는 remapped NSET을 대상으로 별도로
적용한다. MODEL_GLOBAL/INITIAL_BODY를 명시하고, 일부 절점만 움직여 요소를
찢는 자세 변환이나 겹치는 운동·고정 자유도와 충돌하는 속도는 거절한다.

release_height는 물체를 높이에 놓고 비행을 계산한다. impact_height는 생략한
비행의 높이를 초기 속도로 바꾸며, 같은 구간에 측정 속도를 중복 적용하지
않는다. 속도장을 부여했다고 물체를 강체로 간주하지 않는다.
C3D10·hex·cohesive의 입력 유래 질량·중심·관성 적분은 기존대로 UNKNOWN이다.
Native 관측과 입력 유래 적분을 서로 바꿔 표시하지 않는다.

## 확인한 실제 범위

모델·converter 검사는 반복 instance, 중첩 include, 이름/ID 충돌, 열 절점
순서, 혼합 요소의 잘못된 surface side, 누락·중복·오배정 section/재료,
원 occurrence의 물리 오류, stale 원문·재활용 ID와 초기 운동을 포함한다.
동일한 compiled flat 경로의 canonical 입력·초기조건과 정확히 비교하고,
기존 converter의 mesh·PROP·재료·IP·IC admission을 통과시킨다.

실제 native 입력은 기존 공개 응집 시편과 기존 flat formulation fixture의
물리값을 그대로 사용한다. 원 flat과 단일 instance 계층 입력을 각각 독립된
작은 Job으로 실행하고, 원 결과·실패 기록을 덮지 않는다. 원 scalar/vector,
시간축, ID·active 상태와 derived opening의 보존 표본을 그대로 비교한다.
입력 직렬화 tolerance를 응답 tolerance로 전용하거나 시간축을 보간해
동일성을 만들지 않는다.

2026-10-18의 실제 조합은 C3D10 탄성, C3D8·C3D8R 단일 PLASTIC,
COH3D8 TRACTION/LAW117이다. 각 flat/assembly 쌍의 Starter는 오류·경고 0,
Engine은 정상 종료했고, 실제 frame은 각각 11·10·10·21개다. 응력·변위의
선택 응답은 AVAILABLE/NATIVE이며 시간축과 값이 비어 있지 않음을 확인했다.
무하중 fixture의 0값도 누락과 구별했다. C3D10 소성이나 요소 간 물리 응답의
동등성을 이 실행으로 확인한 것은 아니다.

현재 실행 근거와 각 case의 `pair.json`·`cold-reopen.json`은
`runs/impact-assembly-20261018/native-pairs-01/`에 있다. Simulation 저장 후
다른 Python 프로세스에서 같은 settings/result를 읽으며 재실행이나 runtime
재탐색을 하지 않는다. OpenCourant의 기존 고정 Windows runtime과 owned Job
runner를 사용한다. 최초 cold child의 import 경로와 후속 세 case의 작업 폴더
충돌은 원 실패 로그에 보존하고 해당 읽기 단계만 교정·재개했다. 네 쌍의
physics를 재계산하지 않았다.

대표 COH3D8 계층 결과는 저장된 Simulation의 `Post에서 열기`에서 실제
ParaView로 열었다. 16절점·3요소·21시각, 마지막 시각의 변위 크기(mm)를
읽고 Post project를 저장한 뒤 기존 원 모델 복귀 명령으로 같은 Simulation을
열었다. 문서·입력·결과 hash는 그대로이며 새 Job은 0개다. 실행 자식은
Windows Job으로 소유하고 종료 후 `job_empty`를 확인했다. 근거는
`_workspace/continuation-prep-20261018/assembly-post-02/`의 `result.json`,
`post.json`, `return.json`과 창·렌더 PNG다. 검사는 실제 앱과 기존 진입 API를
사용했으며, 테스트용 자식 경로를 주입했다. 사용자의 물리 키보드·마우스
입력이나 전체 Post 기능의 UI 검증을 뜻하지 않는다.

명시적인 재현 실행은 새 출력 폴더를 지정한다. 기존 실행을 덮지 않는다.

```powershell
python -m pytest tests/impact_input_a/test_assembly_physics.py tests/impact_input_a/test_assembly_conversion.py -q
$env:CAELAB_RUN_ASSEMBLY_IMPACT = '1'
$env:CAELAB_ASSEMBLY_RUN_ROOT = 'C:/path/to/new/assembly-check'
python -m pytest tests/impact_input_a/test_assembly_native.py -q
```

위 실행 성공은 제품의 입력·실행·저장 연결 확인이다. 재료 보정, 소성 하중
응답, 손상·삭제 campaign, C3D10 곡면 Jacobian 품질이나 공학 적합성 승인을
뜻하지 않는다. 설치·pin·provider를 바꾸지 않았고 유료 서비스가 필요하지 않다.
