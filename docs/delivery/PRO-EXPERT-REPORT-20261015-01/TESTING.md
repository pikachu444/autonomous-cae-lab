# 검사 기록과 증거 등급

## 실행한 검사

전용 suite: **107 passed, 1 skipped**. skip 1은 PySide6 미설치로 인해 Qt module 전체(5개 테스트)를
수집 단계에서 건너뛴 것이다. Qt/PDF가 통과했다는 의미가 아니다. 별도 기존 Report 회귀 suite는
**5 passed, 2 deselected**이다. 두 suite의 통과 합계는 **112개**다.

환경: Linux x86-64, Python 3.13.5, pytest 9.0.2, numpy 2.3.5, scipy 1.17.0, VTK 9.6.2.
PySide6는 설치되어 있지 않다. 제품의 pinned Windows/ParaView 환경에서 실행한 기록은 아니다.
전용 suite의 65개 warning은 주로 VTK 9.6의 GetCellTypesArray deprecation이다. 숨겨서 없어진 결함으로
취급하지 않는다. 새 API로 바꾸어 기존 ParaView VTK 호환성을 추정하지 않았다.

```text
PYTHONPATH=.:tests python -m pytest -q \
  tests/test_report_image_core.py tests/test_report_image_vtk.py \
  tests/test_report_image_native_contract.py tests/test_report_image_connection.py \
  tests/test_report_image_qt.py --disable-warnings

PYTHONPATH=.:tests python -m pytest -q tests/test_experiment_report.py \
  -k 'exact_absent_time or snapshot_numeric_scalars or exact_nested_candidate or saved_optimization_reduction' \
  --disable-warnings
```

Windows의 환경변수 경로 구분자는 `;`다. root의 기존 venv/테스트 실행기를 사용한다.
이 코드 때문에 새 유료 package/provider, 별도 VTK 설치나 WSL을 제품 필수로 추가하지 않는다.
VTK는 native ParaView에 들어 있는 버전을 사용하고, headless VTK 테스트는 별도 개발 검사다.

## 검사별 의미

| 검사 | 실제 실행한 것 | 증명하지 않는 것 |
|---|---|---|
| `test_report_image_core.py` | 실제 ReportDocuments owner의 asset 저장, update/Undo/Redo/save/cold reopen, 한글/공백 경로 복사, 출처 제거/변조, 저장 실패, image-only 손상 본문 보존, PNG CRC/압축/scanline/크기, 과거 Warp 개정 귀속 | native가 만든 PNG, 실제 solver 물리값, 공학 승인 |
| `test_report_image_vtk.py` | 실제 VTK로 analytic mesh/XML 쓰기·읽기, 8개 정적 dataset 종류와 5개 실제 시각 단일 dataset, 좌표/연결/배열/성분/dtype/NaN/Inf/time/파일 조각 대조 | ParaView GUI의 Render/SaveScreenshot, 병렬/분산 reader |
| `test_report_image_native_contract.py` | 실제 기존 Workspace.export 메서드를 격리하여 실행, 모의 owner/ParaView/SaveScreenshot, 실제 VTK saved tetra 비교, 캡처 중 변경과 native 부재 차단 | 실제 native process, Windows Qt, 종료 lifecycle |
| `test_report_image_connection.py` | 모의 transport의 같은 command 상태 확인, 응답 소실·미확인·실패·취소·늦은 응답·원문서 변경 보호 | 실제 HTTP/dispatch gateway, 계정/provider |
| 기존 `test_experiment_report.py` 일부 | 정확 시각 누락 거부, numpy/nonfinite 원값 유지, 선택 후보·축약값의 정확 identity | full Workbench bootstrap, 평가/solver 실행 |

`test_report_image_qt.py`에는 실제 QTextDocument/QImage resource, 크기·포함·순서, Study 판단 공존,
저장/재열기 후 실제 PDF 이미지 embedding와 Markdown PNG byte 동일성, atomic 출력 실패,
실제 ReportWindow local Undo/마지막 preview 보호 검사를 작성했다. 가짜 Qt 객체로 통과시키지 않았다.
현재 결과는 **NOT_RUN**이다. native 캡처와 Qt 출력은 각각 다른 증거이며 둘 다 root 수용 검사가 필요하다.

## 배포 재현 검사

배포본의 validation 디렉터리에 stdout, 환경 정보, compileall/AST, diff 검사 및 clean apply 기록이 있다.
새 폴더에 첨부 ZIP을 다시 풀고 additions.patch와 integration.patch를 실제로 적용한 후 같은 전용 suite와
기존 회귀 suite를 다시 실행했다. 작업 디렉터리의 미배포 파일을 참조한 검사가 아니다.

전체 앱 초기화는 선별 ZIP에 apps.desktop_pre/apps.lab 등이 없어 미실행이다. 해당 모듈을 가짜로
추가하지 않았다. 실제 native/provider/solver/실장비/Windows 설치 실행도 하지 않았다.

## 출처 및 변경 경계

실제 첨부 REQUEST(3).md/PRO_REQUEST(1).md, CURRENT_STATE.md의 FN05/29/30/32/35,
docs/PRODUCT_PLAN.md, docs/CODEX_WORKFLOW.md, docs/PRODUCT_UI_MCP_PLAN.md §6.6,
FUNCTION_SPEC의 해당 기능, SPEC-EXPERT-002/SPEC-EXPERIMENT-001을 기준으로 읽었다.
다른 대화의 파일이나 최신 Sol 미커밋 내용을 읽었다고 가정하지 않았다.

공개 API 확인 자료(검사 결과와 구분):
- ParaView simple SaveScreenshot는 지정 view를 받을 수 있다.
  https://www.paraview.org/paraview-docs/latest/python/paraview.simple.html
- vtkPVDataInformation의 GetHasTime/GetTime은 actual DATA_TIME_STEP에 관한 정보다.
  https://www.paraview.org/paraview-docs/latest/cxx/classvtkPVDataInformation.html
- VTK XML reader/writer 및 composite 데이터 설명은 Kitware/VTK 공식 API 문서를 참고했다.
  https://vtk.org/doc/nightly/html/classvtkXMLReader.html
  https://vtk.org/doc/nightly/html/classvtkXMLWriter.html

이 문서는 root의 통합/검사 인도 자료이지 provider/solver 응답 보고서가 아니다.
