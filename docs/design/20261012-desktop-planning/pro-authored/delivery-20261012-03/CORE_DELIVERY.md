# D1 핵심 명세와 Qt 소스 먼저 회수

요청 PRO-DESKTOP-DESIGN-20261012-03의 우선 게시본이다. 원 D1을 다시 작성하지 않고 기존 파일을 그대로 제공한다. ZIP·PNG 전체 전송을 기다리지 않고 아래 내용으로 기획·Qt 검토를 시작한다.

- [전체 기능 명세와 C01–C09 계약](../FUNCTION_SPEC.md)
- [C01–C09 상세 계약 원본](../spec_sections/WORKFLOW_CONTRACTS.md)
- [전체 화면 명세](../SCREEN_SPEC.md)
- [구현 작업표](../IMPLEMENTATION_BACKLOG.csv)
- [대표 작업 시나리오](../PROTOTYPE_SCENARIOS.md)
- [Material Qt 소스·실행 방법](../prototype/README.md)
- [합성 CSV와 fixture](../data/README.md)
- [최신 Penpot 제외 결정](DECISIONS.md)
- [Codex 인계](CODEX_HANDOFF.md)

먼저 Material의 두 CSV 매핑·표/곡선·owner draft·채택/저장·재열기, 접촉의 면 선택/법선/형상변경 복구 계약, Study/Evaluation 독립 작업을 검토한다. `prototype/Start-PlanningPrototype.ps1 -PythonPath <기존 python.exe> -MaterialOnly`는 핵심 소스만으로 실행을 시도할 수 있는 별도 Material harness다. 전체 gallery는 뒤따라 게시하는 `screens/screens.json`과 PNG를 사용한다.

Penpot 계정·편집·export는 최신 사용자 지시로 완료 관문에서 제외한다. SVG/JSON/.drawio/.ui와 로컬 Qt를 사용한다. product source/settings/threshold/main/CURRENT_STATE는 변경하지 않는다. 본구현 시작은 사용자의 별도 지시 이후다.

전체 원 D1 ZIP·화면 자산은 같은 브랜치의 후속 커밋으로 이어 게시한다. 원본은 보존하며, 이 우선 회수본을 새 설계 또는 실제 Windows 실행 통과로 표시하지 않는다.
