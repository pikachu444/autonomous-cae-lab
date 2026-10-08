# Design Lab · 조작 가능한 설계 시안

Windows에서 `전처리.cmd`, `실행기.cmd`, `후처리.cmd`, `최적화.cmd`, `전문가.cmd`, `워크벤치.cmd` 중 원하는 프로그램을 실행한다. 각 명령은 공통 로컬 서비스를 필요할 때 시작하고 자기 앱 창을 연다. 개발자는 `python server.py --port 8791`로 서버를 직접 시작할 수 있다.

문서는 `user-data/`에 프로그램별 확장자(`.caeprep`, `.caerun`, `.caepost`, `.caestudy`, `.caechat`, `.caeproject`)의 UTF-8 JSON 파일로 저장된다. 이 폴더는 Git에서 제외한다. 문서 ID/버전으로 직접 열 수 있다: `/pre?id=<ID>&revision=<N>` 등. HTTP 서버는 `127.0.0.1`에만 바인딩한다.

이 폴더는 **설계 검토용 시안**이다. 서버 파일 저장, revision 충돌, 실제 CSV/ASCII/OBJ 입력은 작동한다. 시연 실행과 전문가 답변은 실제 solver/LLM이 아니다. 기존 제품 API와의 실제 계산 연결은 별도 검증 기록을 따른다.

관찰과 수정 근거는 `../../docs/WORKBENCH_PROGRESS.md`의 현재 절과 `evidence/` 이미지에 있다. 핵심 화면 명세는 `../../docs/PLANNING_SCREENS.md`, 본 구현 작업은 `PLANNING_HANDOFF.md`를 따른다. 메시/필드는 제한 시안이며 범용 native reader, 제품 문서 bundle, 실제 LLM은 후속 작업이다.

재현 스크립트는 `experiments/`에 둔다. `smoke_design_lab.py`는 별도 임시 저장소에서 저장·409·과거 버전·표시상태 지문·잘못된 경로를 확인한다. `code_reuse_smoke.py`는 기존 caelab 및 FELUPE 설치 환경에서 실제 CSV 읽기와 재료점 저장/재열람을 실행한다. `verify_ouroboros_mcp.py`는 별도 개발용 HTTP MCP의 도구 발견과 읽기 조회만 수행한다. 세 시험은 UI 시각 검토나 전체 solver 적격성 검증을 대체하지 않는다.
