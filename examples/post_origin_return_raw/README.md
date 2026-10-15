# 공개 원결과 — 저장 참조로 가장하지 않음

`public-comparison/`은 첨부한 exact public `examples/post_comparison.py`의 표준 라이브러리 create만 실행해
생성한 4점/1tet VTU와 PVD다. a.pvd는 0.5, b.pvd는 0와 1의 원 frame이다. NativeNodeId 101–104는
VTK point index 0–3과 다르고 quality 1,1,0,1도 보존된다. 원 field/time/양쪽 bracket 점검용이다.
`comparison.json`은 그 예제의 명시 선언 recipe이며 source_ref의 두 번째 입력은 GUI 등록 후 정한다.
VTU/PVD 파일 자체에 단위/물리시각 선언이 있다고 가정하면 안 된다. 직접 열기는 UNKNOWN을 유지하고
기존 검증을 거친 명시 선언으로만 비교한다. 새 수학/solver 검증 증거가 아니다.

`public-trial/load-cell.csv`는 exact public `examples/post_curves.py:27`의 bytes literal만 복사했다.
elapsed_ms의 실제 두 원행은 100/1100, force_kN는 0/0.004다. 해당 script의 Data upload/import/Workbench
함수는 실행하지 않았다. retained Data reference/job/result SHA/fullpin을 만들지 않았다.
Pro는 기존 Data import/save/read API를 사용해 진짜 영수증을 얻는 테스트를 작성해야 한다.

이 폴더는 사용자의 saved project/PVSM, source path, token, PID를 담지 않는다. raw 원결과이므로
closed/fullpin 통과 fixture로 직접 쓰지 말 것. saved 프로젝트 테스트는 기존 measurement/report fixtures와
실제 owner API를 재사용하며 hash를 caller가 꾸며 넣는 우회 코드를 제품에 넣지 않는다.
생성 원문/SHA/검사는 `배포 evidence/public-fixture-validation.json`에 있다.

이 경로는 원패킷의 raw fixture 복사본이다. 실제 retained Data 확인 예제는 `python -m examples.post_origin_return <새 디렉터리>`이며 새 native SDK를 실행하지 않는다.
