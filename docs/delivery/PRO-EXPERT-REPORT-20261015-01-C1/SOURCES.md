# 사용한 정확한 원자료와 외부 계약

## 요청/제품 기준

첨부 CORRECTION.md, PUBLIC_CONTRACTS.txt, 첫 인도 ZIP, public-source-4ac2e2a.zip을 기준으로 했다.
CURRENT_STATE의 FN-05-01/02, FN-32-01, FN-35-01, FN-30-01/02와 원 FUNCTION_SPEC/SPEC 경계를
유지했다. public CURRENT_STATE 2277행에는 실제 설치 대상 ParaView 6.2.0이 기록되어 있다.
사용자 전달의 최신 main 5f6aede 검사와 Sol gui-fit.patch는 외부 수행 보고이며 이 작업에서 읽고
적용한 최신 main/로컬 작업 사본으로 간주하지 않았다.

공개 제품의 external.py validate_metadata(241-270), post_comparison.time_plan(283-319),
post_curves(160-181), desktop.launch_tool 및 _post/CLI 발췌가 PUBLIC_CONTRACTS.txt에 있다.
실제 전체 해당 파일과 첫 인도의 report_image/native/dialog/Report owner/preview 연결도 대조했다.

## ParaView 원문 확인

다음은 Kitware의 태그가 고정된 1차 자료다. 다른 버전의 property 이름을 추정하지 않았다.
public API 문서와 C++/XML은 source review이며 실제 설치된 native 수용 증거는 아니다.

```text
https://www.paraview.org/paraview-docs/v5.13.2/python/_modules/paraview/simple.html#ColorBlocksBy
https://github.com/Kitware/ParaView/blob/v5.13.2/Remoting/Views/vtkSMColorMapEditorHelper.cxx
https://github.com/Kitware/ParaView/blob/v5.13.2/Remoting/Views/Resources/views_and_representations.xml
https://github.com/Kitware/ParaView/blob/v6.2.0/Remoting/Views/vtkSMColorMapEditorHelper.cxx
https://github.com/Kitware/ParaView/blob/v6.2.0/Remoting/Views/Resources/representationsinternal_remotingviews.xml
```

| 원문 | 확인한 계약 | Git blob SHA |
|---|---|---|
| v5.13.2 helper cxx 1290-1500 | ColorBlocksBy(None) 제거, 실제 component는 LUT에 설정됨 | 1e10abcd1f22ec81a404c3585d7087b8ea57f80c |
| v5.13.2 helper cxx 1880-2040 / 2800-3020 | selector/association/array triples 및 LUT index 대응 | 동일 |
| v5.13.2 XML 4700-5000 | block property의 representation 노출 | c7e6441d23a4cd50d90e6199d6223ee28b52afc2 |
| v6.2.0 helper cxx 2790-2950 | 같은 triple-LUT index 대응 | 663dd27b2405e87194286f1e5a4254f11efb9515 |
| v6.2.0 internal XML 2540-2820 | block property 이름/type/command width/MapScalars 의미 | 197249bcf633551fe74e81d6ceac77ae8fd1707c |

6.2.0에서는 XML이 representationsinternal_remotingviews.xml로 분리되어 있다. 과거 경로의 404를
속성 부재로 오인하지 않고 디렉터리와 실제 파일을 확인했다. mock은 위 raw SM API의 계약을
시험용으로 구현한 것이며 native proxy를 실행한 것으로 계산하지 않는다.
