# 작은 B1.3 native 확인 입력

원 Pro 작성 환경에서는 아래 FreeCAD/CalculiX/Windows 실행이 **미실행**이었다. Windows 통합에서는
`--kind shell`의 생성·속성 적용·입력 준비만 확인했고 솔버는 실행하지 않았다. 실제 저장 member의
새 owner 읽기는 영역/적용 기록을 복원하지만 binding 변경 관문에서 차단된다. 이 왕복을 완료로
세지 않는다. 기존 예제 로그나 합성 fixture를 신규 native 증거로 복사하지 않는다.

`models.create_shell`은 R=400 mm, 축 길이=100 mm, 각도=30°의 원통 곡면과 S8 8개, 두 영역 2/3 mm 및 offset 0/0.25를 만든다. 두 번째 영역 법선 반전은 offset/압력 부호도 함께 반전한다. 원통 실제 native Face1/Face2와 요소 선택을 기존 ShellEditor/Owner에 연결한다. 곡면 형상/확장 좌표 자체를 기준면 좌표로 대체하지 않는다.

`models.create_beam`은 기존 `examples/beam/beam_example.py`의 실제 editable 1000 mm·10×20 mm·10 Seg3 요소 예제를 재사용한다. 독립 `moment_1`, `moment_2`, `end_force` 중 하나와 0°/90°를 선택한다. `--regional-axes`는 요소 절반씩 0°/90°로 나눈 직선 빔 입력이며 균일 빔 해석해와 수치 일치한다고 주장하지 않는다.

## Windows에서 기존 owned Job으로 하나씩 실행

저장소 root에서 실행한다. `--output`은 **존재하지 않는 새 폴더**다. 자동 campaign은 없다. `--run`이 없으면 native 생성·Apply·freeze·저장·새 Owner 읽기만 수행한다. `--run`은 선택한 하나의 solver job을 명시 실행한다. 실제 설치 FreeCAD 경로를 사용한다.

```powershell
python examples/b13/run_native_check.py --freecad "C:\Program Files\FreeCAD 1.1\bin\FreeCAD.exe" --output "C:\CAEChecks\b13-shell-r01" --timeout 180 --kind shell
python examples/b13/run_native_check.py --freecad "C:\Program Files\FreeCAD 1.1\bin\FreeCAD.exe" --output "C:\CAEChecks\b13-shell-reverse-r01" --timeout 180 --kind shell --reverse-second --run
python examples/b13/run_native_check.py --freecad "C:\Program Files\FreeCAD 1.1\bin\FreeCAD.exe" --output "C:\CAEChecks\b13-beam-raw-0-r01" --timeout 180 --kind beam --case moment_1 --angle 0 --output-mode raw_stress --run
python examples/b13/run_native_check.py --freecad "C:\Program Files\FreeCAD 1.1\bin\FreeCAD.exe" --output "C:\CAEChecks\b13-beam-raw-90-r01" --timeout 180 --kind beam --case moment_1 --angle 90 --output-mode raw_stress --run
```

명령의 timeout은 사용자가 지정하는 실행 제한이지 소요 시간 예측이 아니다. `scripts/native_check.run_native_check`가 원 프로세스를 suspended 생성 → 전용 Windows Job에 할당 → resume하며 성공·실패·timeout의 finally에서 그 Job만 닫는다. 새 checker가 전체 이름으로 FreeCAD/CalculiX를 일괄 종료하지 않는다. 내부 macro는 자신이 만든 문서/owner만 정리한다. 기존 사용 중인 FreeCAD GUI에서 이 확인 macro를 직접 실행하지 않는다.

표준 `section_forces`와 `raw_stress`는 서로 다른 output 폴더에서 **별도의 명시적 실행**으로 수행한다. 기존 whole model mechanical 카드가 동일한지는 beam_output.compare_runs로 대조하며 run/input/result ID를 합치지 않는다.

## 사전 기준과 관측

beam_reference는 E=210000 MPa의 균일 Euler–Bernoulli 해석해와 허용값을 **계산 전** `reference-before-run.json`에 기록한다. tip U는 단일 확장 corner U가 아니라 실제 tip 단면의 centroid translation과 비교한다. 0→90°의 moment_1 굽힘 처짐 비는 4다. 독립 moment_2와 end_force도 정의되어 있다. 비영 U 상대 2%, 기대 0 U 절대 1e-5 mm, 복원 stress-traction 비영 합력/모멘트 상대 5%, 기대 0 force 1e-4 N/moment 0.1 Nmm를 사전 기준으로 둔다. 실패 후 낮추지 않는다. 강체-fit의 native DOF 대체 수용 기준은 없다.

현재 checker는 생성/입력/실행/새 owner 관측을 JSON에 남긴다. 이 해석해와의 수치 수용을 자동 완료로 표시하지 않는다. regional axes/곡면 셸을 균일 직선 빔 해석해와 비교해서 통과시키지 않는다. 곡면 두 영역의 실제 `.12d`/FRD/DAT 좌표·coverage와 물리적 동일성은 native 관측에서 별도 검토한다. `native_engineering_acceptance`와 `windows_acceptance`는 이 증거 묶음을 단순 생성했다고 true로 변하지 않는다.

지지 모멘트 기준점은 GUI에서 변경하거나 초안 output.reference_mm으로 명시한다. 같은 native 관측을 재조회해 `M(r1)=M(r0)-(r1-r0)×F`를 확인한다. 중복 끝/집합과 반대 법선/누락 관측 반례는 test_b13_support_response.py와 test_b13_beam_raw.py에 있다. 이들은 math/format 회귀이며 native 계산 성공 증거가 아니다.

## 중요한 미검증 경로

B32R RECT는 내부 50점이다. 공식 ccx2.22 COORD 소스의 배열/분기 위험은 `docs/b13/PRIMARY_SOURCES.md`에 기록했다. 설치 바이너리의 정상 COORD를 가정하지 않는다. 이 때문에 새 native raw run이 실패하거나 reader가 거절할 수 있다. 그때 원 출력/로그를 보존하고 미수용으로 남긴다. generated COORD나 8점 부분 데이터로 성공을 만들지 않는다. 새 solver를 설치하거나 원 solver 소스를 바꾸는 해결책은 이 인도 범위가 아니다.

확인 산출물은 `options.json`, `process/` stdout/stderr/Job receipt, `model/`의 native 문서·동결 입력, 선택 시 `run/`의 기존 execution/result/Post 보존 묶음, `b13-native-observation.json`이다. wrapper 종료코드 0은 해당 명령의 준비/실행 경로 성공만 뜻하며 공학 수용/전체 기능 완료가 아니다. 실패·cancel·timeout·cleanup 오류는 nonzero로 반환한다.

checker는 `owner.project.path`의 저장 `.caepre`를 기존 검증/복원 함수로 읽고 새 owner의
정확한 draft·applied와 실행 준비 상태를 대조한다. 문서의 `FileName`은 편집 기록을 넣기 전
FCStd일 수 있으므로 저장 프로젝트의 대체 경로로 사용하지 않는다. `read_saved_project`는
이미 저장한 프로젝트의 읽기만 수행하며 새 형상·Apply·솔버를 실행하지 않는다.

원 FreeCAD Python writer 함수 대조 검사에는 `CAELAB_FREECAD_REFERENCE_FEM`으로 설치된
FreeCAD1.1.4의 `Mod/Fem` 경로를 명시할 수 있다. 제품에 원문을 복사할 필요는 없으며,
세 writer의 SHA256이 원 공개 참조와 같아야 검사한다. 다른 버전·없는 참조를 통과로 세지 않는다.
