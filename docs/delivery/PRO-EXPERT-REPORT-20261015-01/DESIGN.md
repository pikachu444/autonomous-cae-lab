# FN32: Post의 정확한 3D 이미지와 Study 판단을 보존하는 보고서

요청: PRO-EXPERT-REPORT-20261015-01. 기준은 첨부 public-source-4ac2e2a.zip이다.
ZIP comment와 사용자 지정 기준: `4ac2e2afa4a63557524749b384209fe587b6daa5`.
ZIP SHA-256: `5fe88990a1315d9fac8f9a53fb0200df0fa1040912ca82001317c5ddf222a64a`.

## 인도 범위와 완료 표현

이 인도는 FN32의 캡처-자산-보고서 편집/보존/출력 연결 코드다. FN05, FN30, FN35를 완료로 바꾸지 않는다.
추가 provider/solver 실행, 계정 인증, 모델 fallback, 새 장비 driver, 새 capture backend/store는 없다.
개발 대화의 권한은 제품 Expert provider 권한을 증명하지 않는다.

핵심 저장/검사와 native 계약을 실제 실행한 테스트로 확인했다. native 계약 테스트는 명시적인 모의
ParaView/SaveScreenshot이며 실제 렌더 증거가 아니다. 별도의 VTK 테스트는 설치된 VTK로 실제 XML을
쓰고 다시 읽는다. Qt/PDF/Windows native 수용 검사는 작성했지만 이 환경에서는 실행하지 않았다.
따라서 '구현물 인도'와 'Windows native 사용자 수용 완료'를 구분한다.

## 재사용 가정의 검토와 선택한 설계

1. 기존 Workspace.export의 `file/sha256/revision/analysis_saved=False`만으로는 저장 결과와 현재
   렌더 프레임이 같다는 증거가 되지 않는다. 특히 저장 후 time을 바꾸어도 PNG export는 성공할 수 있다.
   기존 `_bundle`의 적용 입력/그래프 확인과 결과 파일 해시를 재사용하되, 표시 데이터 전체를 저장된
   단일 프레임과 읽기 전용으로 대조한다. 중심·범위·절점 수만 비교하거나 허용치를 완화하지 않는다.
2. `report_image_data`는 ParaView에 포함된 VTK reader를 쓸 뿐, 계산 solver·새 렌더·새 view·새 자산
   저장소를 만들지 않는다. 좌표, 연결 순서, 셀 종류, polyhedron face, 점/셀/field 배열, 성분 이름,
   dtype, 복합 블록/이름, 실제 DATA_TIME_STEP을 비교한다. NaN은 NaN으로 유지하며 payload 비트만
   정규화한다. Inf와 부호 있는 0은 보존한다. 이것은 파일/표시 대응 확인이지 수치해석의 정확성 증명이 아니다.
3. 캡처는 기존 Post owner thread에서 수행한다. 기존 retained view에 Render를 요청하고 실제 표시를
   읽은 뒤 기존 Workspace.export를 딱 한 번 호출한다. 캡처 전후 scene, source pin, 저장 결과 및
   실제 VTK 데이터가 달라지면 새 binding을 만들지 않는다. 창 종료 gate/timer/observer는 수정하지 않는다.
4. PNG·snapshot은 기존 `ReportDocuments`의 8 MiB 자산 경로에 들어간다. `id/sha256/reference` 계약,
   잠금, append-only 저장 개정, Undo/Redo 자산 보관을 재사용한다. Co-STORM/Study/문헌 owner는 안 만든다.
5. 기존 report_pages의 semantic blocks → QTextDocument → preview/PDF와 Markdown 분기만 확장한다.
   Report의 이미지 읽기는 native/solver를 호출하지 않고, mutable Post 선택을 다시 따르지 않는다.

## 같은 순간에 고정하는 항목

`caelab.post-report-image/1` snapshot에는 다음이 함께 들어간다.

- 기존 broker가 완료한 Post command와 해당 원문서/세션, 저장 Post project/PVSM 파일 pin.
- 선택 object의 정확한 적용 개정, recipe/graph, 원입력 파일 pin 및 물리 선언, 결과 파일 pin.
- 사용된 모든 upstream 개정의 lineage. upstream의 현재 UI position이 아니라 downstream binding과
  dependencies가 지시한 과거 개정을 따라간다. Warp 종류/배율/속성도 그 개정에 귀속된다.
- 실제 데이터 field, POINTS/CELLS association, scalar/component/magnitude, component index/name,
  선언된 단위 또는 UNKNOWN. 없는 단위를 추정하거나 단위 없는 값을 무차원이라고 바꾸지 않는다.
- 실제 DATA_TIME_STEP, view time, animation time, 시간의 단위/의미 선언 및 frozen_clock.
  실제 데이터 시각과 view 시각은 정확히 일치해야 한다. 인접 프레임이나 보간으로 통과시키지 않는다.
  DATA_TIME_STEP 없는 정적 자료는 NO_DATA_TIME/null이며 0초가 아니다.
- camera, view 속성, representation, lookup table, 연결된 scalar bar/범례, Warp 및 view generation.
- 실제 PNG bytes의 SHA-256/크기/pixel size, 데이터 대조 fingerprint, 캡처 시각과 실행/판정 상태.

캡처 성공, 원계산 실행 성공, 수치/물리 판정, 공학 승인은 다른 주장이다. 캡처가 FAILED/UNKNOWN이면
적용하지 않는다. 캡처 자체가 성공해도 기존 결과의 execution/qualification이 UNKNOWN인 경우 그대로
미확인으로 표시한다. 공학 승인은 언제나 NOT_RELEASED이며 표시 변형 배율은 물리값이 아니다.

## 파일과 연결 API

| 신규 파일 | 책임 |
|---|---|
| `caelab/report_image.py` | trusted receipt, 저장 출처, PNG/조건 무결성, 불변 asset, 명시 편집, 검증 실패 시 본문 보존 |
| `apps/desktop_post/report_image_data.py` | VTK 저장 파일과 실제 표시 데이터의 읽기 전용 exact comparison |
| `apps/desktop_post/report_image_native.py` | 기존 owner와 export의 동일 시점 snapshot 조정 |
| `apps/research/report_image_connection.py` | 한 번 dispatch한 요청의 같은 command 상태 재조회, 취소/늦은 응답 보호 |
| `apps/research/report_image_dialog.py` | 결과 선택, 캡처, 미리보기, 명시 적용/취소, 크기·표시, 출처 진단 |
| `apps/research/report_image_pages.py` | 기존 preview/PDF 이미지 resource와 self-contained Markdown |

공통 API는 기존 경로 안에서만 확장한다.

```python
# 기존 document_command: 실제 Post owner만 실행한다.
client.document_command(post_id, 'post.export',
    {'object_ref': applied_object, 'format': 'png', 'report_snapshot': True},
    session_id=post_session, expected_generation=generation, command_id=command_id)

# 새 endpoint/PNG-upload API 아님. 서버가 저장된 broker receipt를 직접 조회한다.
binding = client.report_capture(report_id,
    {'kind': 'post_image_command', 'command_id': command_id})
asset = client.report_content(report_id, [binding])['assets'][0]

# 캡처/retain만으로 draft를 변경하지 않는다. 사용자 적용 시 기존 Undo owner에 전달한다.
new_draft = apply_binding(draft, binding, asset['content'],
    section_id=target_id, expected_section=section_before_dialog)
```

최종 reference는 `{kind:'post_image', command_id, snapshot_sha256}`이다. 파일 경로나 receipt를 client가
임의로 올려 등록하지 못한다. image 참조는 Report의 local reference 검사만 확장한다. Study의 기존
reference schema를 변경하지 않는다. HTTP/client/native broker 공통 schema 및 registry 변경도 없다.

`section.image = {show: true, width_percent: 100}`은 선택 필드다. 기존 문서에는 필수화하지 않는다.
제목/설명/포함/순서/표/곡선은 기존 section 명령을 그대로 사용하며 명시 교체는 section의 해당 asset만
교체한다. 새 capture UI에서 적용을 누르기 전에는 본문·판단·이전 asset이 바뀌지 않는다.

## 실패, 취소와 손상 처리

- 전송 응답을 잃어도 자동 재전송하지 않는다. 같은 command_id의 상태만 다시 읽는다.
  UNKNOWN을 성공으로 재해석하거나 새 native 실행으로 가리지 않는다.
- 취소는 '보고서 적용 취소'다. 이미 시작한 동기 SaveScreenshot의 물리적 중단 확인이라고 말하지 않는다.
  닫힌 dialog에 온 늦은 응답은 무시한다. 이미 만들어진 미채택 자산/PNG를 자동 삭제하지 않는다.
- 출처 파일 누락/변경은 새 채택을 차단한다. 이미 저장한 Report의 PNG/조건/본문은 그 파일이 없어도
  읽으며, source_status=UNAVAILABLE 경고를 붙인다. 기존 방식대로 명시 동의하면 경고가 포함된 초안 출력이 가능하다.
- 보존 asset이 손상되면 SNAPSHOT_UNAVAILABLE이다. 이미 화면에 있는 마지막 검증 사본은 '검증된
  화면 사본/초안' 경고와 함께 유지한다. 새 capture 성공이나 완전한 저장 성공으로 바꾸지 않는다.
- cold reopen에서 이미지 사본만 손상된 경우에도 기존 publication hash, revision 목록, 본문 hash,
  모든 비이미지 파일을 확인한 뒤 본문과 판단을 읽는다. 없는 픽셀을 재구성하지 않는다.
  본문/다른 종류 자산 손상까지 허용하는 완화는 없다. 새로 저장하는 미게시 revision에는 이 예외를 적용하지 않는다.
- 이미지의 모든 사본이 소실되면 새 저장은 해당 자산의 정확한 복구 전까지 실패할 수 있다. 기존 Undo에
  포함된 자산도 보존해야 하므로 단순 이미지 삭제/교체가 소실 사실을 지우는 복구가 되지 않는다.
  기존 publication과 편집 중 본문은 유지된다. 이 인도는 새 blob 복구/garbage collection 시스템을 만들지 않는다.
- preview 새 구성이 실패하면 이전 page를 유지하되 stale 표시로 새 출력은 차단한다. 다른 문서를 열 때
  이전 문서의 page/cache는 초기화한다. 기존 atomic_export를 써서 출력 실패가 기존 파일을 덮지 않는다.

## 지원 범위와 의도적으로 차단한 경우

이번 경로는 저장하고 적용한 **filter 또는 공간 comparison의 단일 RenderView**다. 원source를 임의로
PNG 등록하거나 외부 PNG를 불러오는 경로가 아니다. 결과를 표시하고 저장한 후 카메라와 색상 조건을
조절할 수 있다. 데이터 frame/처리 결과를 바꿨다면 다시 정확한 결과를 저장해야 한다.

색상으로 지정한 점/셀 배열과 해당 범례만 허용한다. 다른 dataset, 독립 Text 주석, 다른 field scalar bar,
미적용 속성, 단색/direct RGB/texture, XYChartView 및 배열 없는 그림은 차단한다. 이는 일반 ParaView의
모든 화면을 지원한다는 주장을 하지 않고, 정확한 물리 출처를 가진 첫 3D 경로를 한정하기 위한 것이다.
원결과 열기는 보존 PNG와 출처/조건을 보여주며, 과거 ParaView 카메라를 원프로세스에 자동 재구성하지 않는다.

VTK XML: `.vtu/.vtp/.vti/.vtr/.vts/.vtm/.vtpd/.vtpc`의 serial 단일 프레임. 데이터 종류는 unstructured,
polydata, image, structured, rectilinear, multiblock, partitioned, partitioned collection이다.
병렬 `pvtu`, AMR/HyperTreeGrid, vtkTable, 다중 시각 XML 및 애매한 복합 시간 메타데이터는 이 경로에서
지원하지 않거나 exact check가 보수적으로 거부한다. 병렬/FETCH merge 재번호화도 수용을 주장하지 않는다.

PNG 최대 5 MiB, 한 변 8192, 총 16,000,000 pixels, metadata 256 KiB, Post manifest 16 MiB,
저장 VTK 파일 및 단일 비교 데이터 각각 512 MiB, 복합 파일 4096개/중첩 16 이하다.
검사는 UI owner thread에서 실행되므로 큰 데이터의 반응성/메모리·Windows 비용은 아직 계측하지 않았다.
숫자 및 topology 정확 비교를 일부 샘플 비교로 바꾸어 이 한계를 숨기지 않는다.

Markdown은 기존 방식에 맞춰 PNG 원바이트를 data URI로 넣은 단일 파일이다. data URI를 차단하는
외부 Markdown viewer의 표시까지 보장하지 않는다. PDF는 Qt가 이미지를 임베드하므로 PNG 파일의
압축 바이트가 PDF 안에서도 동일하다는 뜻이 아니다. 이미지 resource/시각 내용 보존을 검사한다.
