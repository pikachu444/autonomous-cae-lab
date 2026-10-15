# 원문 근거와 읽기 한계

이번 기준은 첨부 REQUEST/API_MAP/ACCEPTANCE/OWNERSHIP/PRIMARY_SOURCES/PROTECTED_LATEST와 두 manifest다. 구현 시작 시 제품/의존 ZIP 크기·SHA256·CRC·필수 파일 해시 및 fixture 원문을 확인했다. 외부 현재 main을 overlay하거나 다른 대화의 구현을 사용하지 않았다.

## 계층 INP

공식 Abaqus 2025 문서를 읽었다. INSTANCE는 이동 1행 뒤 global 축의 두 점과 degree 회전 1행이며, 순수 회전도 0,0,0 이동 행을 요구한다. 이동이 먼저 적용된다. NSET은 선행 집합 참조와 assembly-level INSTANCE option, GENERATE의 정수 간격을 명시한다. 구현은 여기서 선언한 첫 subset만 지원한다. 2024 URL의 접근 실패를 원문 열람으로 바꾸지 않았다. 매뉴얼 본문은 배포하지 않는다.

- https://docs.software.vt.edu/abaqusv2025/English/SIMACAEKEYRefMap/simakey-r-instance.htm
- https://docs.software.vt.edu/abaqusv2025/English/SIMACAEKEYRefMap/simakey-r-nset.htm
- https://docs.software.vt.edu/abaqusv2025/English/SIMACAEKEYRefMap/simakey-r-assembly.htm
- https://docs.software.vt.edu/abaqusv2025/English/SIMACAEMODRefMap/simamod-c-partassy.htm

## Native pinned source

첨부 public_references/OpenCourant는 cb760c206e346eff12161a2268b134ef9d48a4ef의 원 CFG/reader 자료다. DEPENDENCY_MANIFEST의 bytes/SHA/blob을 근거로 읽었으며 원 저작권·license와 fixture를 수정하지 않았다. `INCLUDE/include.cfg` 및 cpp_get_include_files_list/cpp_get_number_of_include_files의 #include 형식을 사용했다. source named radioss51/110/2021은 CFG 계보이며 별도 구버전 runtime을 실행했다는 뜻이 아니다.

- https://github.com/OpenCourant/OpenCourant/tree/cb760c206e346eff12161a2268b134ef9d48a4ef
- 기존 release: https://github.com/OpenCourant/OpenCourant/releases/tag/latest-20261011
- runtime 구현: caelab/adapters/opencourant_runtime.py (이번 변경 없음)
- 기존 INP2RAD: third_party/inp2rad/CAELAB_NOTICE.md와 pinned inp2rad.py (변경 없음)

추가로 pinned `starter/source/constraints/general/rbody/hm_read_rbody.F`와 `inirby.F`의 일부를 GitHub connector로 읽었다. 이 원문에는 강체 초기화 COM/질량/관성 출력과 secondary velocity 보정이 있다. 그러나 이번 인도는 그 reader를 실행 admission에 완성하지 못했다. 따라서 `/RBODY`는 계속 차단하며 단순 card 이름 존재나 연속체 관성 계산을 native 강체 지원 근거로 쓰지 않는다.

binary/CFG identity는 기존 값과 동일하다. 소스 tag가 converter 개별 binary의 build provenance를 증명하지 않으므로 `converter_source_commit=NOT_PROVEN_BY_RELEASE`를 유지한다. Windows 실행·실제 active CFG postflight는 NOT_RUN이다. source 코드 읽기, 대역 테스트, 실제 native 실행을 서로 바꾸어 표시하지 않았다.
