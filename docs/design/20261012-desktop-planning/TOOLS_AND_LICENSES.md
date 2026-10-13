# 무료 도구·사용 범위·라이선스 확인

확인일 2026-10-12. 이번 기획/시제품 추가 지출은 0원이다. 이미 보유한 Codex/Pro와
무료/오픈소스 도구만 사용한다. 구매·trial·결제수단·hosting·유료 API fallback은 없다.
제품 배포물의 실제 dependency/build와 notice/source obligations는 승인 후 패키징 항목에서
다시 exact version으로 확인한다. 아래 license facts는 공학적 release나 회사 배포 승인과 다르다.

| 도구/구성 | 실제 선택 범위·무료 경로 | 원본/라이선스와 확인 한계 |
|---|---|---|
| ChatGPT Pro | 개발 설계 주 작성. 실제 Edge 대화의 Pro power5/5 선택과 문서 전송 확인. 기존 사용권 | 신규 API 호출/구독 변경 없음. 제품 Expert의 API 사용권을 뜻하지 않음 |
| Codex 모델 | 사용자가 지정한 Sol/xhigh, Astra/xhigh, bounded Sol/high, Luna/high. 현재 사용권 도구로 배정 | 모델 설정과 활성 host는 구별. 지정 모델의 결과를 다른 모델 결과로 대신 표시하지 않음 |
| MoAI | installed official source `2aab5f7`, local CLI/MCP/SPEC/수동 skill 읽기. user assets/resources와 기존 설정 보존 | [공식 source](https://github.com/modu-ai/moai-adk/tree/2aab5f797b75983e132af451da68f69e3426557b), Apache-2.0 원 LICENSE 확인. 프로덕션 dependency 아님 |
| draw.io Desktop | 공식 v32.4.1 Windows portable ZIP, local `.drawio` 편집/내보내기. 서버/유료 AI 없음 | [공식 release](https://github.com/jgraph/drawio-desktop/releases/tag/v32.4.1), [해당 버전 GPLv3 원문](https://github.com/jgraph/drawio-desktop/blob/v32.4.1/LICENSE). 앞선 Apache-2.0 표기를 실제 Desktop 태그의 라이선스로 교정했다. 기획 도구로 사용하며 제품에 번들하지 않는다. 실제 앱 열기/export는 도면별 실행 기록을 따른다 |
| Penpot | 최초 Professional 무료안 조사/로그인 화면 확인 뒤 **사용자 지시로 제외**, 탭 닫음. 계정/결제/trial 없음 | [공식 pricing](https://penpot.app/pricing)의 Professional $0를 확인했으나 편집/export는 하지 않음. editable SVG/.drawio/.ui/native interaction으로 대체 |
| Qt/PySide6 | 이미 있는 user Python3.13/PySide6 **6.9.1**. 새 전체 Qt 시제품은 Core/Gui/Widgets, 화면 내보내기는 QtSvg를 사용한다. 앞선 Designer spike는 UiTools도 사용했다. native FreeCAD/ParaView는 별도 runtime | [Qt for Python licenses](https://doc.qt.io/qtforpython-6/licenses.html), [LGPL obligations](https://www.qt.io/development/open-source-lgpl-obligations). notice와 교체 가능한 라이브러리·수정 source 조건 등을 배포 시 반영. GPL-only module을 LGPL로 가정하지 않음 |
| Qt SVG / SVG Widgets | 같은 기존 PySide6 **6.9.1**의 `QSvgRenderer`/`QSvgWidget`과 `QSvgGenerator`를 사용한다. 실제 전체 Qt 시제품의 편집 SVG를 렌더·내보내기했으며 패키지 설치 없음 | [Qt 6.9 계열 공식 라이선스](https://doc.qt.io/archives/qt-6.9/qtsvg-index.html#licenses-and-attributions)는 LGPLv3/GPLv2 또는 commercial을 명시. 추가 지출 없는 LGPL 경로와 배포 시 notice/교체 조건을 적용 |
| Qt Designer | 기존 PySide6 bundled `designer.exe`와 editable `.ui`, 새 유료 Qt account 설치 없음 | `.ui` 원본은 repository에 남긴다. Designer 사용과 Qt library 배포 의무는 별도 |
| Matplotlib | 이미 있는 **3.10.1**의 QtAgg 그래프·plot selection. repo optional dependency pin3.10.8과 구별 | [공식 license](https://matplotlib.org/stable/project/license.html): PSF 기반/BSD-compatible, notice 보존. installed package license 원문과 version은 runtime evidence에 귀속 |
| Python/Numpy | 이미 설치된 interpreter/수치 자료 처리. demo는 stdlib+Qt+Matplotlib, 새 numerical engine 없음 | dependency license/notice는 package exact version inventory로 추적. mock data/고정 계수는 SIMULATED UI |
| pypdf | 2026-10-13 소유한 Windows 개발 runtime에 기존 `assist-pdf` pin **6.10.0**을 설치해 PDF reader import 확인. 기존 KnowledgeStore의 로컬 PDF 텍스트 추출에 사용 | [해당 태그의 BSD 3-Clause 원문](https://github.com/py-pdf/pypdf/blob/6.10.0/LICENSE). 소스/바이너리 배포 시 저작권·조건·면책 고지 보존. OCR이나 표·수식·그림의 정확성 보증은 없음. 유료 서비스/API 연결 없음 |
| FreeCAD | 2026-10-13 과거 작업 폴더에서 기존 1.1.4 portable 실행 파일 확인. native Sketcher/PartDesign/Assembly/FEM·FCStd 경로 재사용 | [공식 LGPL 안내](https://github.com/FreeCAD/FreeCAD/blob/main/LICENSE). bundled OCCT/Qt 등 별도 notices·version 필요. 이번 확인에서 FreeCAD 실행·CAD 변경·solver 계산 없음 |
| ParaView | 같은 폴더의 기존6.2.0 pvpython을 재사용해 공개 합성 PVD의 실제 native 시간 측정과 저장 실행. 새 다운로드·설치 없음 | [공식 BSD license](https://www.paraview.org/license/). VTK/Qt bundled notices 필요. 연결용 합성 자료이며 solver/공학 검증·OS 조작·전체 format 지원을 뜻하지 않음 |
| SALib | 2026-10-14 기존 `sensitivity` pin **1.5.2**를 공식 Windows 설치 스크립트의 `-Sensitivity`로 추가. Sobol 표본/분석 import와 기존 작은 실제 수학 평가기 검사를 실행. 새 D6 GUI 완료 근거는 아님 | [1.5.2 MIT 원문](https://github.com/SALib/SALib/blob/v1.5.2/LICENSE.md), [배포판 정보](https://pypi.org/project/SALib/1.5.2/). 재배포 시 저작권·허가·면책 고지를 보존. 함께 설치한 pandas/dill/multiprocess/tzdata의 개별 고지도 배포 대상에 포함한다. 유료 서비스/API 없음 |
| 글꼴 | 로컬 설치된 Malgun Gothic/Segoe UI를 참조해 Windows/Qt 텍스트 렌더링. 폰트 파일은 배포하지 않음 | font binary를 저장소/ZIP에 복사하지 않음. 다른 OS에서는 이용 가능한 font로 명시 대체 |
| Qt 보고서 출력 | 기존 QtGui의 QPdfWriter/QPainter로 검토용 PDF를 출력한다. QtPdf·QtWebEngine·유료 보고서 엔진을 추가하지 않음 | 기존 PySide6/QtGui 오픈소스 사용 범위를 따른다. 실제 제품 보고서·근거 연결은 관련 구현 완료 뒤 검증하며, 시안 출력은 합성 자료 |
| Poppler pdftoppm | Codex bundled **26.07.0**을 PDF 출력의 읽기 전용 시각 검사에 사용. 추가 설치·제품 번들링 없음 | [공식 해당 소스](https://poppler.freedesktop.org/poppler-26.07.0.tar.xz)의 COPYING에서 GPLv2 원문을 확인했다. 검토 도구이며 제품 실행 의존성에 넣지 않음 |
| SVG/JSON/CSV 원본 | Pro가 작성하는 local editable screens/flows/fixture, repository내 보존 | viewer·diagram tool은 기획 도구, 제품 web front-end가 아님. 회사 자료 대신 합성 시안 사용 |

제품 Expert는 provider 미설정/limit 상태에서도 질문 draft·기존 발언·근거 읽기·Plan 초안을
저장할 수 있게 설계한다. 현재 subscription 기반 무료 연결의 실제 지원 범위를 명시하며,
새 유료 provider를 연결하지 않는다. local supported backend가 없는 요구는 scope에 남기고
capability/installation/numerical qualification을 별도로 표시한다.

MoAI 확인 경계: stdio initialize/tools/list와 `spec_progress`를 실제 호출했고 SPEC strict lint를
수행했다. user skill catalog에 `moai`, `moai-plan/sync`, `moai-workflow-spec/project`가 나타났다.
현재 host MCP 노출은 별도다. installed Codex CLI0.146.1은 기존 global
`features.context_management` map을 boolean schema로 읽다 실패한다. global bytes는 바꾸지
않았으며 **read-only `mcp get moai` 확인 한 번에만** `-c features.context_management=false`
임시 override를 사용했다. 모델 호출/권한 변경/설정 저장은 없었다. 호스트 hook trust와 일반
CLI 실행 호환성이 이 검사로 완료된 것은 아니다.
