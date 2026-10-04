"use strict";

// Display names only. Stored values, units, verdicts and identities stay intact.
(function (root) {
  const backendNames = {
    "fixture.assembly": "굽힘 시험 치구", "fixture.cadquery": "치구 부품",
    "fixture.freecad": "편집 가능한 CAD 모델", "fixture.calculix": "치구 구조 해석",
  };
  const metricNames = {
    cad_component_count: "부품 수", cad_bounds: "전체 크기", cad_volume: "형상 체적",
    maximum_displacement: "최대 변위", max_displacement: "최대 변위",
    maximum_von_mises: "최대 등가 응력", max_von_mises: "최대 등가 응력",
  };
  const parameterNames = {
    "specimen.length": "시편 길이", "specimen.width": "시편 폭",
    "specimen.thickness": "시편 두께", "test.span_ratio": "지지 간격 / 두께 비",
  };
  const validationNames = {
    physical_qualification: "실제 사용 조건에 대한 적합성",
    printed_material_allowables: "출력 재료의 허용 강도",
    print_anisotropy_process: "출력 방향과 제작 공정의 영향",
    contact_friction_bearing: "접촉·마찰·받침 조건",
    fastener_grade_joint_preload: "볼트 등급·체결·조임 조건",
    roller_retention: "롤러 이탈 방지", machine_interface: "시험기 장착 조건",
    static_strength: "정적 강도", physical_load_test: "실물 하중 시험",
    fatigue_durability: "피로와 내구성", corporate_license_security: "회사 사용·보안 승인",
  };
  const componentNames = {
    printed_base: "바닥판", printed_support_left: "왼쪽 받침", printed_support_right: "오른쪽 받침",
    metal_roller_left: "왼쪽 롤러", metal_roller_right: "오른쪽 롤러",
    metal_loading_nose: "가압부", specimen: "시편",
  };
  const array = value => Array.isArray(value) ? value : [];
  const lookup = (map, name, fallback) => Object.hasOwn(map, name) ? map[name] : fallback;

  function title(backend) { return lookup(backendNames, backend, "해석·모델 실험"); }
  function metricName(name, index = 0) { return lookup(metricNames, name, `결과값 ${index + 1}`); }
  function validationName(name, index = 0) { return lookup(validationNames, name, `확인 항목 ${index + 1}`); }
  function inputs(record) {
    const entries = array(record.registry_snapshot?.entries);
    return Object.entries(record.result?.input_parameters ?? {}).map(([id, value], index) => {
      const entry = entries.find(item => item.parameter_id === id);
      const path = entry?.native?.path;
      return { id, name: lookup(parameterNames, path, entry?.display_name ?? `입력 ${index + 1}`),
        value, unit: entry?.unit ?? null };
    });
  }
  function checks(result) {
    const items = array(result.validations), counts = { PASS: 0, FAIL: 0, UNKNOWN: 0, WARNING: 0, other: 0 };
    items.forEach(item => { counts[Object.hasOwn(counts, item.status) && item.status !== "other" ? item.status : "other"]++; });
    return { counts, total: items.length, unresolved: items.filter(item => item.status !== "PASS") };
  }
  function faceDescription(face) {
    if (!face) return "면을 클릭하면 부품과 면 종류를 확인할 수 있습니다.";
    const component = lookup(componentNames, face.component_id,
      /^metal_bolt_left_/.test(face.component_id ?? "") ? "왼쪽 볼트"
        : /^metal_bolt_right_/.test(face.component_id ?? "") ? "오른쪽 볼트" : "선택한 부품");
    const kind = lookup({ PLANE: "평면", CYLINDER: "원통면", CONE: "원뿔면", SPHERE: "구면" },
      String(face.type ?? face.surface).toUpperCase(), "곡면 / 기타 면");
    const ordinal = /:face:(\d+):/.exec(face.catalog_face_id ?? "")?.[1];
    return `${component} · ${kind}${ordinal ? ` · 원본 면 ${ordinal}` : ""}`;
  }
  const api = { title, metricName, validationName, inputs, checks, faceDescription };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.resultPresentation = api;
})(typeof window !== "undefined" ? window : globalThis);
