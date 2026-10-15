# 여러 구동 관계식

요청: PRO-M1-GENERAL-RELATIONS-20261015-01. 첨부 기준은
`1e3025f565c2246c2746c8cedd300f95e21e0408`이다. B1.2 / FN-11-01 /
SPEC-PREFE-001 M1·AC-03의 일반 관계식 작성분이다. 기존 Post 종료 작성,
M3 닫힌 기구, M4 선택 자세 FEM, 다른 팀의 dynamic/report 작성분과 구분한다.

이 문서는 구현 계약과 사용법이다. 현재 지원 범위와 다음 개발은
[CURRENT_STATE](../CURRENT_STATE.md)에서 확인한다. 아래의 공개 예제 검사는
지원 범위의 확인이며 모든 기구나 공학적 품질의 승인을 뜻하지 않는다.

## 화면에서 수행하는 작업

기존 조립 운동 창의 **시간과 구동**에서 A와 B 구동을 먼저 만든다. 예제는
회전 A `30*time` deg, 회전 B `10*time` deg다. 출력 관절 C를 구동 표에 추가하고
선택한 뒤 **구동 방식 → 관계식**, 출력 단위 **deg**를 선택한다. 시간식과 관계식을
동시에 지정하지 않는다. 관계식으로 바꾸면 그 행의 직접 시간식 칸은 비운다.

**기준 추가**로 두 행을 추가한다. 각 행의 **다시 선택**에서 조립 계층/관절 이름,
회전·이동과 선언 단위를 보고 실제 구동을 고른다. 식 이름 칸을 A/B로 편집하고
관계식에 `0.5*A+B`를 입력한다. **구동 적용**은 기존 native Simulation/Motion을
구성하지만 계산하지 않는다. **운동 결과 → 다시 계산**이 실제 운동 계산이다.
결과 표/곡선은 선택, **자세 보기**는 명시 미리보기다.

비선형 관계는 상수 표에 이름 `amplitude`, 값 `30`, 단위 `deg`를 입력하고 식을
`amplitude*sin(A)+B`로 바꾼다. 0.5초의 기대 C는
12.764571353075622 deg다. 이 수치는 첨부 oracle의 독립 산술 기대값이며 native
실행 결과가 아니다. 끝 시각만 비교하면 선형 관계와 구별되지 않으므로 중간
출력 시각도 검사한다.

혼합 관계는 입력 L `5*time` mm와 출력 X의 관계식 `gain*A+L`, 상수 gain `2`
`mm/deg`를 사용한다. 기대 X는 0/0.5/1초에서 0/32.5/65 mm다. X는 여기서
**구동 좌표의 이름**이며 전역 X축 이동을 뜻하지 않는다. 공개 Slider rig의 이동
축은 관절의 로컬 Z축이다. 경로점은 해당 moving Link의 로컬 점으로 지정한다.

기준과 상수의 순서는 각 표의 위/아래 버튼으로 바꾼다. 별도 식 이름을 사용하므로
순서 변경만으로 관계 의미가 달라지지 않는다. source를 삭제하면 식의 그 이름은
자동 삭제되지 않으며 해당 출력 행에서 미선언 이름 오류를 고친다. 선언한 기준을
식에서 사용하지 않아도 오류다. 별도 계산 결과를 기준으로 선택하는 기능은 아니며,
**명시 구동 좌표**만 선택한다.

기준 표의 **식 값**은 입력 시작 시각의 시간식 평가값이다. 툴팁에 이 의미와 초를
표시하며 실제 계산 자세처럼 제시하지 않는다. 값의 전개/검사가 불가능하면
**미확인**이다. 이 표를 갱신해도 native 계산 명령을 보내지 않는다.

## 단위와 지원 식

| 항목 | 지원/동작 |
|---|---|
| 구동 좌표 | Revolute Angular, Slider Linear, Cylindrical의 Angular/Linear를 별도 좌표로 식별 |
| 출력 단위 | Angular rad/deg, Linear mm. native 최종 출력은 rad/mm |
| 식 이름 | 영문자로 시작하는 최대 32자 영문·숫자·밑줄. time/pi/함수명은 예약 |
| 변수 | 명시 source alias, typed constant 이름, time(s), 무차원 pi |
| 연산 | 덧셈·뺄셈·곱셈·나눗셈·단항 부호·괄호 |
| 함수 | sin/cos(각도 → 무차원), arctan(무차원 → 각도) |
| 상수 단위 | 1, rad, deg, mm, s 및 이들 사이 한 단계 비율. 예: mm/deg, deg/s, 1/s |
| 제한 | 관계 원문 256자, 전개 native 식 8192자, source 1–32개, 상수 0–32개 |
| 기존 전체 제한 | 구동 1–32개, 최대 2001frame, trace 8개, editor 128KiB 유지 |

숫자 literal은 **무차원**이다. `A+1`에서 A가 각도면 거절한다. 상수 offset을
`1 deg`로 정의하고 `A+offset`으로 입력한다. `sin(A)`는 A의 선언이 deg든 rad든
실제 각도를 canonical rad로 전달한다. `sin(A*pi/180)`은 이미 각도인 A를 추가로
축소하는 **다른 물리식**이므로 자동 보정하지 않는다.

작은 helper는 기존 motion_formula.UNITS의 deg/rad 값을 재사용한다. 새 범용
단위 프레임워크, evaluator, solver를 설치하지 않는다. 물리 차원은 각도/길이/시간의
정수 지수로 검사하고 상수 단위를 rad/mm/s로 내린다. `2 mm/deg × A`는 선언한
계수의 의미를 보존하여 전개한다. 출력 C의 표시 단위를 deg에서 rad로 바꾸는
것은 typed 관계의 물리량을 다시 해석하지 않는다.

반면 기준 A의 선언 단위를 deg에서 rad로 바꾸면 기존 binding의 `unit`과 달라진다.
**단위 확인**을 눌러 현재 기준을 검토하고 확인 체크를 선택하기 전에는 적용을
차단한다. 확인은 기준 단위 잠금만 갱신한다. gain의 **숫자와 mm/deg는 그대로**다.
예를 들어 `30*time deg`를 `30*time rad`로 바꾼 것은 실제 다른 운동이다. 같은
운동을 유지하려면 사용자가 A의 시간식도 명시적으로 환산해야 한다. 이때 C/X의
계수는 자동 재작성하지 않는다.

새 관계에서는 `eval`, `exec`, 속성/경로/첨자식, 임의 함수, 문자열, 비교/조건문을
허용하지 않는다. sin/cos/arctan은 고정된 native parser와 기존 관측값 검사기에서
확인한 함수다. exp/log/sqrt/tan/거듭제곱은 새 관계의 지원으로 추가하지 않는다.
기존 자유 시간식의 역사적 허용 목록과 한계가 없을 때의 처리도 바꾸지 않는다.
그런 기존 식을 새 relation의 source로 쓰려면 새 관계가 전체 구간과 native 의미를
검사할 수 있어야 하므로 미확인 연산을 포함한 source는 거절한다.

구간 검사는 기존 바깥쪽 반올림을 유지한다. sin/cos 범위는 기존대로 [-1,1]인
보수적인 범위여서 상관관계가 있는 식이나 좁은 실제 운동도 한계 충족을 증명하지
못할 수 있다. 이는 실패 원인으로 남긴다. 함수값 몇 점, clipping, 허용값 확대,
동일 변수의 임의 약분으로 통과시키지 않는다. 분모에 0이 가능하면 한계가 없어도
새 관계를 거절한다. 설정 종료와 native 규칙의 실제 마지막 출력 시각을 모두
포함하여 검사한다. 유한 한계를 가진 미구동 좌표의 기존 차단도 유지한다.

## 사라진 기준과 취소·저장

기준이 사라졌거나 억제되었거나 다중 소속이면 이름을 사용해 다른 Link로 바꾸지
않는다. 관절 ID, 종류, 고유 occurrence path와 이전 단위를 원문과 함께 보존한다.
해당 기준 행의 **다시 선택**은 임시 선택만 보여준다. **선택 확인**에서만 binding을
교체한다. 취소/Esc는 이전 alias·계수·식·선택을 그대로 둔다. 변경 대상의 단위가
다르면 별도 확인 체크가 필요하다.

재선택 dialog는 `QDialog.open()`의 window-modal 경로를 사용한다. 늦은 확인 시
문서/owner/조립/구동 행/편집 버전/기준 행과 원문을 다시 대조하고 현재 native
path/unit을 재검사한다. 다른 owner나 새 편집을 덮을 수 없다. 테이블 편집은
QLineEdit/편집 가능한 unit combo의 즉시 변경 신호를 기존 dirty 관문에 전달한다.
따라서 `1e`가 아직 포커스를 가진 상태라도 snapshot에는 그 문자열이 들어간다.
레이블·진단 갱신은 입력 위젯을 재생성하지 않으며 caret/selection을 보존한다.

기존 프로젝트 저장으로 유효 관계와 미완성 초안을 모두 `.caepre`에 저장한다.
원 definition과 draft는 별도다. 저장이 적용/계산을 뜻하지 않는다. 원 관계와 단위를
저장하지 않고 native 식만 저장하는 방식으로 대체하지 않았다. `relation_view`는
선택한 기준/상수 행만 저장하고 물리 definition hash에는 넣지 않는다.

잘못된 초안이 있으면 새 계산/프레임 보기/재생/자세 채택과 기존 후속 후보 관문이
차단된다. 이미 보존된 경로 읽기는 원 자료를 그대로 사용한다. `구동 편집 취소`는
기존 정책대로 마지막 적용 정의로 돌아간다. Undo/Redo의 기존 owner transaction,
전체 문서 저장/닫기/reconnect 정책은 복제하거나 교체하지 않았다. 보존 성공과
새 실패를 합성한 정상 곡선을 만들지 않는다.

## 개발자 계약과 최소 통합

적용 예: [definition.json](../examples/assembly_relations/definition.json).
raw 예: [editor-draft.json](../examples/assembly_relations/editor-draft.json).
이 예의 ID/path는 새 공개 rig의 고정 생성 이름이며 GUI에서 사용자가 입력할 값이
아니다. 사용자 모델에서는 `pre.motion.inspect`의 실제 선택을 사용한다.

`relation`은 기존 drive의 optional 필드다. 구조는
`{expression, sources:[{alias,joint_id,type,path,unit}], constants:[{name,value,unit}]}`다.
적용 상수 value는 유한 number이고 raw draft value는 원 문자열이다. raw source의
joint_id/type/path는 nullable이며 validation은 형태만 검사한다. formula는 관계식
행에서 빈 문자열이어야 한다. relation과 dependency를 동시에 적용할 수 없다.

`compile_drives(drives,time,joints)`의 반환은 그대로 `{row_index:native_formula}`와
`{row_index:[issue]}`다. 오류는 기존 MotionInputError.input_rows로 전달한다.
현재 hierarchy의 path/억제/고유성/한계와 원 definition, native definition hash의
분리를 유지한다. 단일 dependency도 기존 선언 단위 값 × ratio + offset 계약을
유지하며 새 relation을 source로 참조할 수 있다.

`product.patch`에는 compiler/helper, 전용 Qt 모듈, motion.py의 import/native compile/
raw serializer hunk, 전용 tests/examples와 문서만 있다. `integration.patch`는 product
적용 뒤의 diff이며 다음 세 공통 파일에만 닿는다.

| 위치 | 최소 연결과 이유 |
|---|---|
| motion.py `_inspect` | 관절 행에 이미 계산한 unique path를 읽기 전용으로 추가. 선택 binding 작성용 |
| motion_panel.py | 모드/전용 editor 생성, raw/apply 직렬화, snapshot/선택 복원, 기존 dirty·validation 연결 |
| motion_history.py `check_closed_motion` | 새 relation이 있는 개방 체인도 기존 관절/실제 구동 일치 검사를 사용. 저장 joint path와 실제 마지막 시각을 compile에 전달 |

history hunk가 없으면 기존 개방 체인의 NOT_APPLICABLE 조기 반환 때문에 새 관계가
native 반환코드만으로 통과할 수 있다. 그래서 이 hunk는 선택사항이 아니다. 새
constraint checker를 만든 것이 아니며 M3 폐합 식/관측식/native error tolerance를
변경하지 않는다. **relation 없는 기존 개방 체인 처리도 그대로**다. 과거 결과를
읽을 때 migration하거나 원본 metadata/파일을 몰래 다시 쓰지 않는다.

공통 Core/registry/native_commands/desktop, motion_occurrence와 FEM/다른 팀 폴더는
수정하지 않는다. 새 M4 후보 관문을 만들지 않고 기존 `_assert_editor_applied`와
accepted result를 사용하는 경계를 유지한다. 완전한 후속 Windows GUI→후속 후보
수용은 root의 실제 통합에서 확인해야 한다.

## UI 설계 선택과 미검증 상태

첨부 FC-PROPERTY에 따라 선택한 출력 구동의 속성으로 관계를 편집한다. 별도의
일반 JSON 편집창이나 새 앱을 만들지 않았다. FC-TASK에 따라 기준 재선택을 작고
취소 가능한 작업으로 두고, QT-PANELS에 따라 기존 scroll 영역과 행 선택을 유지한다.
표의 수평 스크롤/툴팁은 긴 계층 경로를 보존하고 한 줄로 ID를 노출하는 대안은
선택하지 않았다. 수식이 작업의 중심이고 긴 설명은 이 문서에만 둔다.

기존 native palette/font를 상속하고 8px 간격, 표의 교대 행, 명시적 focus/선택,
세 열로 감기는 짧은 버튼 그룹을 사용한다. Qt 테스트는 480/960px 너비에서 실제
QWidget을 띄우도록 작성했다. 통합 환경의 Qt 6.9.1에서 관계 편집기의 선택·취소,
미완성 `1e` 입력 저장·복원과 늦은 응답 보호를 확인했다. 기존 운동 창의 보통/좁은
너비 렌더에서 한글과 스크롤·선택을 확인했으며, 일반 관계식에는 단일 종속 구동의
비율·영점 입력을 숨긴다. 이 offscreen 확인은 OS 마우스 입력 검증과 구분한다.

FreeCAD 1.1.4에서는 공개 독립 체인의 선형·입력 변경·비선형 관계를 실제 계산하고,
joint 좌표와 world trace를 독립 기대값에 기존 허용값으로 대조했다. 정상 저장본과
미완성 관계 초안을 각각 새 프로세스에서 열어 원 결과·원 파일 보존, 실행 차단과
명시 수정 후 재저장을 확인했다. 중첩/폐기구 전체 native 검사를 반복한 것은 아니다.

## 무료 설치와 검증

새 C++ plugin/SDK/컴파일러는 필요하지 않다. 기존 FreeCAD 1.1.4의 Python native
Assembly/Simulation 모듈과 주입된 QtWidgets/QtCore를 그대로 사용한다. 새 유료 API,
provider, 구독, 서버, WSL, 다른 solver가 없다. Python core 검사는 저장소의 기존
pytest로 실행한다. 독립 Qt 검사에는 프로젝트의 기존 research-ui 선택 의존성인
PySide6 6.9.1을 사용한다. 이를 FreeCAD에 외부 주입하지 않는다.

```powershell
python -m pytest -q tests/test_pre_motion_general_relations.py tests/test_pre_motion_general_relation_owner.py tests/test_pre_motion_relation_examples.py
# 기존 research-ui 환경에서만. 미설치 시 skipped이며 GUI pass가 아니다.
$env:QT_QPA_PLATFORM = 'offscreen'
$env:CAELAB_M1_QT_CAPTURE_DIR = 'C:\CAE-checks\m1-qt'
python -m pytest -q tests/test_pre_motion_relation_qt.py
```

독립 Qt offscreen 통과는 FreeCAD/Windows 입력 검증이 아니다. Windows native 검사는
[공개 예제 README](../examples/assembly_relations/README_KO.md)의 owned runner로
실행한다. `--timeout`은 기존 runner의 상한이며 작업 성공 예상 시간이 아니다.
서로 다른 증거가 같은 pass로 합쳐지지 않도록 결과/프로세스 receipt를 같이 확인한다.

외부 코드/바이너리를 이 작성분에 새로 vendor하지 않았다. FreeCAD/Qt의 기존 설치와
배포 license 조건은 그대로이며 새 commercial SDK를 요구하지 않는다. helper의
함수 지원 근거는 아래 공식 pinned source다. 원 소스 본문을 새 배포 파일로 복사하지
않았다.

## 공식 소스와 출처 구분

첨부 api-map.md는 native Motion/Assembly 구현을 읽어 찾은 연결 계약이며 실행 결과가
아니다. 이번 작성에서도 다음 공식 source의 함수와 명령행을 확인했다.

- [FreeCAD 1.1.4 CommandCreateSimulation.py](https://github.com/FreeCAD/FreeCAD/blob/1.1.4/src/Mod/Assembly/CommandCreateSimulation.py): 기존 Simulation/Motion, native Joint/MotionType/Formula.
- [FreeCAD 1.1.4 AssemblyObject.cpp](https://github.com/FreeCAD/FreeCAD/blob/1.1.4/src/Mod/Assembly/App/AssemblyObject.cpp): 기존 motion/time/limit 전달 경계.
- [고정 Ondsel SymbolicParser.cpp](https://github.com/FreeCAD/OndselSolver/blob/4be80eef02a3486cda0d78f3ccbb308d207a9639/OndselSolver/SymbolicParser.cpp): sin/cos/arctan, 수치 literal과 native 함수 파싱.
- [FreeCAD 1.1.4 Application.cpp](https://github.com/FreeCAD/FreeCAD/blob/1.1.4/src/App/Application.cpp): 검사별 --user-cfg/--system-cfg, --single-instance를 쓰지 않는 실행.
- [Qt QDialog](https://doc.qt.io/qt-6/qdialog.html): 비중첩 open/finished와 취소 경로. rolling 문서는 설치 버전 실행을 대신하지 않는다.

첨부 reference-oracle.json은 Python math 독립 기대값이다. 구현의 arithmetic/API
대역 테스트와 Windows에서 생성되는 실제 native frame/path 자료는 다른 종류의 증거다.
