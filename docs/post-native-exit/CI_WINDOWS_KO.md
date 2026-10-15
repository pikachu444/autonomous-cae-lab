# 공개 Windows CI에서 SDK와 plugin 확인

이 경로는 로컬 메모리 부족으로 전체 SDK 빌드를 반복 중단하는 상황을 위한 수동
검사다. 원격 실행은 아래 단계에서 실패했으며 SDK/plugin 전체 완료가 아니다. 실제
ParaView File > Exit/X/Ctrl+Q/Alt+F4, 저장 취소 후 재시도와 한글 화면 수용은
[실창 검수표](ACCEPTANCE_KO.md)의 별도 미완료 항목이다.

## 비용과 실행 경계

2026-10-15 `gh repo view`에서 `pikachu444/autonomous-cae-lab`의 `isPrivate=false`를
직접 확인했다. GitHub는 공개 저장소의 standard Windows runner에 무료 compute와
4 CPU/16GB RAM을 명시한다. 이 workflow는 `windows-2022`만 사용하고 저장소가
비공개이면 job을 실행하지 않는다. larger/self-hosted runner, secrets, 외부 VM은
사용하지 않는다. [공식 runner 사양](https://docs.github.com/en/actions/reference/runners/github-hosted-runners),
[Actions 비용 조건](https://docs.github.com/en/billing/concepts/product-billing/github-actions).

`workflow_dispatch`만 있고 push/PR/schedule 자동 실행은 없다. root가 diff를 검토해
통합한 뒤 수동으로 한 번 실행한다. 기존 workflow는 교체하지 않는다. 권한은
`contents: read`다. Actions cache, `upload-artifact`, release 생성·업로드, pip cache는
없다. 결과는 job log/summary에만 남는다. 이 workflow가 계정의 다른 CI 보관 비용까지
제어한다는 뜻은 아니다.

공식 standard runner의 저장 공간 사양은 14GB다. 전체 SDK 빌드와 설치가 이 안에
든다는 측정은 아직 없다. 첫 실행에서 C:·작업 폴더·임시 폴더의 실제 가용 공간을
기록하고 각 build/install/check 명령 전후에도 가용 bytes를 남긴다. 공간 부족으로
실패하면 원래 오류와 종료 코드를 보존하며 더 큰 유료 runner로 전환하지 않는다.

build glue는 GitHub-hosted CI 환경인지도 확인하여 로컬의 기존 Python 환경에
패키지를 설치하는 실수를 막는다. 로컬에서는 기존 `Build-PostExit.ps1`를 사용한다.

첫 standard run은 SDK 입력을 풀기 전에 실패했다. runner의 Windows·Git에 각각 있는
`tar.exe` 경로들이 한 명령으로 결합된 연결 오류였으며, 실행 경로를 읽는 곳에서
첫 실행 파일 하나만 선택하도록 교정했다. SDK 컴파일이나 native 검사는 아직 시작되지 않았다.

두 번째 실행은 runner의 기본 `tar.exe`에 LZMA 코덱이 없어 같은 단계에서 멈췄다.
이미 필수 도구인 CMake의 `-E tar`를 사용해 고정된 7zip/XZ 입력을 푼다.
압축을 풀기 전 경로·link 검사와 SHA256 검증은 유지하며 새 도구를 설치하지 않는다.

세 번째 [실행38670920927](https://github.com/pikachu444/autonomous-cae-lab/actions/runs/38670920927)은
소스 `75c991960b40145ed8b6bd6545a35c20aafe0844`에서 실패했다. `pqComponents` 의존
빌드는 완료했지만 plugin configure가 SDK의 `vtk-find-package-helpers.cmake:2`를
읽다가 Python 실행 경로 `C:\hostedtoolcache\…`의 `\h`를 잘못된 CMake escape로
판정했다. 원 로그·실패 상태는 보존한다. plugin 빌드·native backend·실창 종료는
모두 `NOT_RUN`이며 의존 빌드 성공을 이들의 성공으로 세지 않는다.

CI build glue에서 SDK configure의 `Python3_ROOT_DIR`·`Python3_EXECUTABLE` 인수만
`/` 구분자로 정규화했다. VTK가 값을 따옴표로 감싼 CMake 소스로 내보내기 때문이다
([CMake 문자열 규칙](https://cmake.org/cmake/help/latest/manual/cmake-language.7.html#quoted-argument)).
고정 archive의 원 VTK 생성 함수를 쓴 작은 CMake 생성→재포함 검사에서 원 경로의
`\h` 실패와 교정 경로·공백 포함 경로의 값 보존을 확인했다. 소유 Job은 `job_empty`로
종료했다. SDK 재빌드나 새 CI 실행은 하지 않았다. 다음은 root가 교정 소스를 검토·게시한
뒤 새 수동 CI에서 plugin configure 이후 단계까지 확인하는 일이다.

## 입력과 실제로 검사할 범위

- 공식 ParaView6.2.0 source archive와 공식 공개 Qt6.9.0/MSVC2022 네 archive를
  고정 SHA256으로 검증한다. Qt hash는 exact ParaView superbuild v6.2.0 CI와 대조한
  값이다. archive 경로와 link 여부도 확인한 뒤 새 임시 디렉터리에 푼다.
- Python은 official `actions/setup-python`의 commit과 Windows x64 버전3.12.10을
  고정한다. 공식 actions/python-versions manifest에서3.12.14는 Windows binary가
  없었다. 같은 CI 실행의 Python3.12.10 개발 파일로 SDK/runtime을 함께 빌드하며
  로컬3.12.14 또는 기존 stock runtime에 이 DLL을 덮지 않는다.
- Python 패키지는 현재 프로젝트의 NumPy2.3.5 Windows CPython3.12 wheel 한 개다.
  공식 PyPI SHA256을 확인하고 `--no-index --no-deps --no-cache-dir`로 설치한다.
  추가 패키지를 자동 탐색·다운로드하지 않는다.
- runner에 설치된 MSVC/WindowsSDK를 `vswhere`로 찾고 실제 compiler/Python/CRT를
  기록한다. Qt 입력보다 오래된 toolset 또는 selected toolset보다 오래된 시스템
  CRT는 거절한다. ABI/최적화/수치 기준은 변경하지 않는다.

새 임시 root에서 VS2022/Release/x64, exact Qt6.9.0/Python3.12로 configure한다.
MSBuild의 공식 파일별 scheduler를 최대2개로 제한한다. 먼저 `pqComponents` 의존
closure와 기존 `Build-PostExit.ps1`로 plugin을 빌드한다. 기존 transaction/C→Python
callback 검사 두 개는 기존 `native_check.py` Job에서 실행하고 Qt event harness는
컴파일만 한다.

CI의 새 설정은 공식 `PARAVIEW_PLUGINS_DEFAULT=OFF`로 선택적 기본 plugin군을 빼며,
필수 VTU/PVD reader와 GUI core는 유지한다. 로컬의 기존 ON cache를 바꾸지 않는다.
이어서 같은 SDK build의 `paraview`, `pvpython`, Python wrapper와 install이 내보내는
나머지 configured target을 완료하고 runtime/development/python install을 만든다.
선택적 기본 plugin까지 포함한 stock bundle과 동일한 기능 범위를 주장하지 않는다.
누락 산출물이나 install 오류를 stock 파일 복사로
감추지 않는다. Qt 배포 도구는 오래된 VC redist를 복사하지 않도록
`--no-compiler-runtime`을 사용한다. existing artifact pin script로 동일 build 관계와
실제 DLL hash를 기록한다.

native backend 확인은 plugin load와 기존 공개 제조장 comparison의 생성→저장→별도
프로세스 cold reopen이다. 모든 테스트와 compiler는 기존 Job runner 아래에 있으며
각 nested check도 `job_empty`를 확인한다. solver, 새 reader/비교 엔진, GUI 입력을
추가하지 않는다. headless plugin load는 GUI auto-start 등록/close filter 설치 증거가
아니다. CI runtime은 그 실행의 Python prefix를 사용하며 portable 배포 완료로 세지
않는다.

## 원격 결과를 로컬 실창 검사로 잇는 선택

현재 workflow에는 output 보관·다운로드 경로가 없다. SDK 빌드가 성공해도 이 실행만으로
로컬에서 사용할 runtime을 받지는 못한다. Actions artifact 보관은 계정의 공유 용량과
별도 과금 조건이 있어, 무료 compute와 무제한 SDK 보관을 같은 조건으로 취급하지 않는다.

다음 배포 단위로는 root가 내용과 라이선스를 검토한 뒤 별도의 수동 package/release
경로를 추가하는 방식을 제안한다. GitHub의 release 문서는 파일당2GiB 미만, 전체
release 크기/대역폭 제한 없음이라고 명시한다. 현재 자동 release 생성이나 공개
배포는 하지 않는다. [공식 release 조건](https://docs.github.com/en/repositories/releasing-projects-on-github/about-releases).

검토할 패키지는 같은 build의 runtime+plugin+manifest와 별도 ParaView development
install이다. CI Python3.12.10의 필요한 stdlib/DLLs와 pinned NumPy, Qt runtime/platform
의존성도 포함해야 한다. Qt 개발 SDK 전체는 제품 ZIP에 넣지 않고 공식 fetch 경로를
사용한다. Qt/ParaView/VTK/Python/NumPy와 실제 third-party의 license·notice·SBOM,
exact source 제공 방식과 LGPL의 재링크/교체 조건을 함께 충족해야 한다. 자체 source와
pin 생성 도구를 통해 수정 Qt로 재빌드·재pin할 수 있는 경계도 유지한다.

원격 archive를 회수할 때 경로/CRC/hash와 exact build 관계를 다시 확인하고 새로운 로컬
prefix에 푼다. 로컬 최종 수용은 그 runtime으로 자신의 새 ParaView 창을 열고 official
computer-use 입력을 관찰해 수행한다. CI의 compiler/reader/backend 결과를 실창 종료
수용으로 바꾸지 않는다. 현재 이 package/release 후속 경로도 구현·실행 전이다.
