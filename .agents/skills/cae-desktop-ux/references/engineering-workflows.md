# 공학 데스크톱 작업 관례

확인일: 2026-10-14. 공식 문서 네 페이지를 무료로 읽어 요약했다.
이 파일은 검색해서 필요한 문단을 가져오는 참고자료다. 임베딩이나 벡터 DB,
새 유료 서비스는 사용하지 않는다. 제품 구현이나 GUI 수용 완료의 근거가 아니다.
출처마다 사실, 우리 제품에 적용할 추론, 비적용 범위를 구분한다.

## FC-TASK — 선택한 객체와 필요한 작업 패널

출처: [FreeCAD 공식 Task panel 문서](https://github.com/FreeCAD/FreeCAD-documentation/blob/main/wiki/Task_panel.md).
읽은 원문: [공식 저장소 원문](https://raw.githubusercontent.com/FreeCAD/FreeCAD-documentation/main/wiki/Task_panel.md).
확인일: 2026-10-14. Wiki URL은 접근 거부되어 공식 저장소 원문을 읽었다.
검색 키워드: `FreeCAD Task panel Tree view selection 작업 패널 상시 폼 객체 선택`.

**원문 사실:** Task panel은 현재 도구에 따라 내용이 바뀌는 독립 도킹 패널이다.
사용자 입력이 필요한 도구를 시작하면 보통 열리고, 입력 없이 끝나는 도구는 패널을
띄우지 않는다. 객체 선택이 필요한 작업은 트리나 3D 화면에서 선택을 기다린다.
작업 패널을 열어 둔 채 트리에서 객체를 선택하고 작업으로 돌아올 수 있다.
일반적인 종료 동작은 OK, Close이며 Esc는 작업 중단에 쓰인다.

**제품 적용 추론:** Pre는 native 객체 선택과 해당 도구의 편집 패널을 재사용한다.
Study 메모와 판단도 작성 동작을 누를 때 필요한 편집부를 열고 중앙 근거를 유지한다.
Expert의 자료 추가나 연결 설정을 상시 빈 양식으로 펼치지 않는다.
선택을 요구할 때는 트리에서 실제 대상을 고르게 하고 내부 ID 입력을 요구하지 않는다.

**비적용 범위:** FreeCAD의 Esc 처리나 OK를 Study 저장 의미로 그대로 옮기지 않는다.
미저장 편집 보존과 문서 저장은 우리 owner 계약을 따른다. 패널의 색상이나 아이콘은
복제 대상이 아니며, 이 문서는 모든 도구의 구체 입력 형식을 정하지 않는다.

## FC-PROPERTY — 선택 대상에 귀속된 속성

출처: [FreeCAD 공식 Property editor 문서](https://github.com/FreeCAD/FreeCAD-documentation/blob/main/wiki/Property_editor.md).
읽은 원문: [공식 저장소 원문](https://raw.githubusercontent.com/FreeCAD/FreeCAD-documentation/main/wiki/Property_editor.md).
확인일: 2026-10-14.
검색 키워드: `FreeCAD Property editor selected object Data View 선택 대상 속성 읽기 전용`.

**원문 사실:** 속성 편집기는 Model 패널 아래 또는 독립 패널에 놓일 수 있다.
통상 하나의 선택 객체를 다루며 표시값은 그 객체의 값이다. 선택이 없으면 비어 있다.
일부 색 속성은 여러 객체에 설정할 수 있고 읽기 전용 속성도 있다.
Data는 객체의 물리적 정의, View는 화면 표현을 다룬다.

**제품 적용 추론:** Pre 속성은 선택한 피처나 접촉 등 실제 객체에 귀속되어야 한다.
Study 편집부에는 메모 또는 판단의 대상 이름을 표시해 중앙 읽기 대상과 혼동을 막는다.
선택이 없을 때 무관한 객체의 폼을 남기지 않는다. 물리적 값과 화면 표시 변경의
뜻을 구분하되 필요한 물리 용어와 단위는 유지한다.

**비적용 범위:** Data/View 탭의 존재는 Study에 자료와 결과, 메모와 판단을 합친
탭을 만들 근거가 아니다. FreeCAD의 View 변경 undo 예외를 우리 문서에 적용하지 않는다.
물리적 정의와 화면 표현의 분리는 모든 연구 작업을 두 범주로 줄인다는 뜻이 아니다.

## PV-PIPELINE — 선택 객체에서 조작과 결과까지

출처: [ParaView 6.2 Basic Usage](https://docs.paraview.org/en/latest/Tutorials/SelfDirectedTutorial/basicUsage.html),
§2.1, §2.4, §2.6, §2.14.
확인일: 2026-10-14. 조회된 latest 문서는 6.2.0이다.
검색 키워드: `ParaView Pipeline Browser Properties Apply selection active object 필터 결과 선택 연결`.

**원문 사실:** Pipeline Browser는 객체와 연결 구조를 보여주며 객체 선택에 쓴다.
Properties는 현재 객체의 매개변수를 보여 주고 고급 항목을 숨기거나 펼칠 수 있다.
필터를 추가하면 새 객체가 입력 아래에 놓이고 속성 패널도 새 필터로 바뀐다.
일반적인 처리 흐름은 매개변수를 정한 뒤 Apply로 실행하는 두 단계다.
데이터 형식에 맞지 않는 필터는 비활성화된다. 데이터 일부의 선택은 같은 객체를
보여 주는 다른 뷰에도 연결된다. 공간 조건의 선택과 고정 요소 선택은 시간 변화에서
다르게 움직이며 Freeze Selection은 당시 요소를 고정한다.

**제품 적용 추론:** Post는 입력 결과 선택, 지원되는 측정 조작, 실행, 결과 확인을
한 흐름으로 유지한다. 시각·위치·성분 선택을 후속 전달에서도 보존한다.
Study의 자료 목록도 선택 객체를 명확히 하고 그 객체에 가능한 작업만 가까이 둔다.
Expert의 계산 계획 편집과 계산 실행을 구별한다. 주 작업은 찾을 수 있게 남기고
고급 진단은 필요할 때 펼친다.

**비적용 범위:** 일시적 화면 선택을 저장된 연구 근거나 수치 검증 판정으로 보지 않는다.
Freeze Selection이라는 이름만으로 우리 saved revision을 구현했다고 주장하지 않는다.
Auto Apply 가능성이 AI 호출이나 solver의 자동 실행을 허용하지 않는다.

## PV-VIEW — 활성 화면과 적용이 필요한 변경 구분

출처: [ParaView 6.2 Displaying data](https://docs.paraview.org/en/latest/UsersGuide/displayingData.html),
§5.1.1, §5.2.1, §5.3.1.
확인일: 2026-10-14. 조회된 latest 문서는 6.2.0이다.
검색 키워드: `ParaView active source active view Display View Apply 미리보기 저장된 근거 성분`.

**원문 사실:** 활성 데이터 객체와 활성 뷰는 서로 다른 개념이다. 한 번에 하나의
뷰가 활성이고 테두리로 표시된다. 일부 패널과 조작은 활성 뷰에 맞춰 바뀐다.
Display 속성은 활성 객체가 활성 뷰에서 어떻게 보이는지 다룬다.
View와 Display 변경은 Apply 없이 표시된다. reader와 filter의 처리는 비용이 클 수
있어 중간 매개변수마다 실행하지 않고 Apply로 준비된 입력을 처리한다.

**제품 적용 추론:** 화면 선택, 표시 방법, 저장된 근거, 새 실행을 같은 상태로
취급하지 않는다. Study의 결과 성분 미리보기는 곧 저장 참조 변경이 아니다.
보는 성분과 연구에 연결한 성분이 다르면 실제 이름으로 차이를 보여 주고 기존
연결 동작을 가까이 둔다. Post의 화면 스타일 변경에 불필요한 실행 확인을 붙이지 않는다.

**비적용 범위:** ParaView의 속성 그룹 이름이나 파란 테두리를 그대로 복제하지 않는다.
이 문서로 Study 저장, 계산 실행, engineering release를 한 Apply에 묶지 않는다.
뷰를 바꾸는 것만으로 원 계산이나 근거의 개정을 갱신하지 않는다.

## 현재 Study 배치 A의 보완점: 미리보기와 저장된 근거

검색 키워드: `Study 배치 A 미리보기 저장된 근거 성분 후속 질문 Keep`.

**제품 소스 사실:** `apps/research/study_window.py`의 `read_response`는 중앙 읽기의
`_content_reference`를 바꾼다. `keep_response_selection`이 선택 자료의
`reference`를 바꾼다. 후속 질문과 계산은 `_navigation_context`의 저장 자료 항목을
전달한다. 따라서 다른 성분을 미리보기만 한 상태에서 화면 성분과 전달 성분이
달라질 수 있다. 현재 화면에는 성분 선택과 “선택한 결과로 바꾸기”가 따로 있다.
이를 소스 결함으로 단정하지 않으며 의도된 보존 경계로 읽는다.

**관찰 범위:** `runs/product-development/20261013/costorm-ui-actions/study-result.png`를
직접 보았고, 배치 후보는 같은 폴더의 `gui-design-debate.md`에서 대조했다.
A는 아직 렌더된 새 화면이 아니라 합의안이다.

**적용 추론:** A의 왼쪽 탐색과 중앙 객체 읽기를 유지하되, 객체 이름만으로는 부족하다.
현재 보는 성분과 연구에 연결된 성분을 구별한다. 기존 Keep 동작의 제목을
“이 성분을 연구에 연결”처럼 실제 뜻에 맞추고, 연결 전 후속 작업이 어떤 성분을
쓰는지 읽기 제목 가까이에서 알 수 있게 한다. 내부 참조 JSON이나 상시 확인 폼을
추가하지 않는다. 자동으로 근거를 덮어쓰거나 새 승인 단계를 만들지 않는다.

## 검색하고 적용하는 순서

증상이 상시 빈 폼이면 `FC-TASK`, 대상이 모호하면 `FC-PROPERTY`,
선택에서 실행까지 끊기면 `PV-PIPELINE`, 미리보기와 저장 혼동이면 `PV-VIEW`를 찾는다.
해당 문단의 원문 사실과 적용 추론을 따로 읽고 현재 소스와 실제 화면을 비교한다.
공식 도구의 관례가 최신 사용자 요구인 합친 탭 제거, 내부 용어 감춤,
필요할 때만 편집하기를 뒤집는 근거가 되지 않게 한다.
이 참고조사는 기존 구현을 계속하기 위한 자료이며 개발의 새 선행 검사가 아니다.

검색 예시:

```powershell
rg -n -A 9 '## PV-VIEW|Study 배치 A' .agents/skills/cae-desktop-ux/references/engineering-workflows.md
```
