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
    applied_force_per_support: "지지대별 하중", displacement_mesh_change_ratio: "마지막 두 메시의 변위 변화율 (상대비)",
    peak_stress: "절점 평균 응력 (진단용)", reaction_balance_ratio: "반력 상대 불평형 (상대비)",
    reaction_force: "지지대 반력 (X, Y, Z)",
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
    joint_and_contact: "체결·접촉", material_qualification: "재료 물성 검증", stress_convergence: "응력 수렴",
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
  // These captions describe persisted steps; they do not admit a new operation
  // or turn service completion, solver execution or file integrity into approval.
  const object = value => value !== null && typeof value === "object" && !Array.isArray(value);
  const own = (value, key) => object(value) && Object.hasOwn(value, key) ? value[key] : undefined;
  const named = value => typeof value === "string" && value.trim().length > 0;
  const step = (stage, next, tone = "unknown") => ({ stage, next, tone });
  const uncertain = () => step("현재 단계 미확인", "실행 기록과 원본을 확인하세요. 다음 단계를 판단할 정보가 부족합니다.");
  function stopped(status) {
    if (status === "CLEANUP_PENDING") return step("종료 확인 중 · 다음 작업 차단", "실행 프로세스의 종료가 확인되지 않았습니다. 종료 재시도로 같은 작업의 정리를 확인하세요.", "pending");
    if (status === "CANCEL_REQUESTED") return step("취소 처리 중", "중단 요청이 처리되는 동안 기다리세요. 종료가 확인되기 전에는 다음 작업을 시작할 수 없습니다.", "pending");
    if (status === "CANCELLED") return step("작업 취소됨", "남아 있는 부분 로그와 결과 기록을 확인하세요. 취소는 수치 검증이나 사용 승인이 아닙니다.");
    if (status === "RUNNING") return step("작업 실행 중", "현재 작업의 종료 상태를 확인하세요. 실행 중에는 다음 작업을 시작할 수 없습니다.", "pending");
    if (status === "REJECTED" || status === "NO_FEASIBLE_DESIGN") return step(status === "REJECTED" ? "조건 미충족 · 다음 단계 차단" : "유효한 후보 없음 · 검토 필요", "미충족 검사와 입력 조건을 확인하세요. 원인을 확인하기 전에는 후속 해석을 진행할 수 없습니다.", "failed");
    if (status === "FAILED" || status === "FAILED_EXECUTION") return step("실행 실패 · 기록 확인 필요", "실패 원인과 남아 있는 부분 기록을 확인하세요. 성공한 해석이나 검증 결과로 사용할 수 없습니다.", "failed");
    return null;
  }
  function cadNext(context, backend) {
    if (context.eligibleParent !== true) return backend === "fixture.assembly"
      ? "모델 형상과 입력 조건을 확인하세요. 이 조립 모델의 해석 기능은 아직 준비되지 않았습니다."
      : "모델 형상과 입력 조건을 확인하세요. 현재 선택한 해석과 호환되는 부모 모델인지 확인이 필요합니다.";
    if (context.integrity !== "VERIFIED") return "결과를 열어 기록·원본 일치를 먼저 확인하세요. 확인 후 연결된 해석 조건을 검토할 수 있습니다.";
    if (context.busy === true) return "현재 작업의 종료를 먼저 확인하세요. 이후 연결된 해석의 재료·하중·메시 조건을 검토하세요.";
    if (context.writable !== true) return "읽기 전용 기록입니다. 모델·입력을 확인하고 새 해석은 작업 저장소에서 준비하세요.";
    if (context.analysisAvailable !== true) return "연결된 해석 기능을 현재 실행할 수 없습니다. 모델 형상과 입력 조건을 확인하세요.";
    return "연결된 해석의 재료·하중·메시 조건을 확인한 뒤, 해석 화면에서 새 실험을 실행하세요.";
  }
  function recordedOperation(operation, result) {
    if (!["doe_plan", "optimization_plan", "model_optimization_plan", "doe_run", "optimization_run"].includes(operation) && own(result, "status") !== undefined) return null;
    const native = own(result, "native");
    if (["parameter_discover", "model_parameters_discover"].includes(operation) && Array.isArray(result) && result.every(item =>
      object(own(item, "native")) && ["backend", "document", "object", "path"].every(key => named(own(item.native, key)))))
      return step(result.length ? "변수 목록 확인됨" : "발견된 변수 없음", result.length ? "변수의 단위·범위와 모델 연결을 확인해 연구 변수로 등록하세요. 조회만으로 실험이 실행되지는 않습니다." : "선택한 모델과 입력 변수 지원을 확인하세요. 조회 결과에는 등록할 변수가 없습니다.", "recorded");
    if (operation === "study_create" && ["id", "research_question", "hypothesis", "objective"].every(key => named(own(result, key))))
      return step("연구 질문 저장됨", "연구 변수와 입력 조건을 준비하세요. 기록 저장만으로 해석이나 인공지능 연구가 시작되지는 않습니다.", "recorded");
    if (["parameter_register", "model_parameters_register"].includes(operation) && named(own(result, "parameter_id")) && object(native) &&
      ["backend", "document", "object", "path"].every(key => named(own(native, key))))
      return step("연구 변수 등록됨", "등록된 변수의 단위·범위와 입력 조건을 확인한 뒤 실험을 준비하세요. 등록은 해석 실행이나 사용 승인이 아닙니다.", "recorded");
    if (operation === "registry_refresh" && Number.isInteger(own(result, "revision")) && result.revision >= 0 && Array.isArray(own(result, "entries")))
      return step("CAD 등록부 갱신됨", "갱신된 변수와 모델 입력 조건을 확인하세요. 기존 실험은 새로 실행된 결과가 아닙니다.", "recorded");
    if (["doe_plan", "optimization_plan", "model_optimization_plan"].includes(operation) && named(own(result, "campaign_id")) && own(result, "status") === "PLANNED")
      return step("수치 탐색 계획 저장됨", "계획의 변수·목적·제약 조건을 검토하세요. 후보 실험은 아직 실행되지 않았습니다.", "recorded");
    if (["native_create", "native_inspect", "native_final"].includes(operation) && named(own(result, "design")) &&
      Array.isArray(own(result, "parameters")) && Array.isArray(own(result, "candidates")) && Array.isArray(own(result, "final_candidates")) &&
      (operation !== "native_final" || named(own(result, "final"))))
      return step(operation === "native_create" ? "편집 모델 생성됨 · 해석 안 함" : operation === "native_final" ? "최종 솔리드 선택 저장됨" : "네이티브 모델 조회됨",
        "모델과 최종 솔리드·변수를 확인하세요. 새 CAD 실험을 만들어야 같은 기록에서 형상과 입력을 확인할 수 있습니다.", "recorded");
    if (["doe_run", "optimization_run"].includes(operation) && named(own(result, "campaign_id")) && own(result, "status") === "COMPLETED_REVIEW_REQUIRED" &&
      Array.isArray(own(result, operation === "doe_run" ? "samples" : "evaluations")) && result[operation === "doe_run" ? "samples" : "evaluations"].length > 0)
      return step("후보 탐색 실행됨 · 결과 검토 필요", "후보별 결과와 미충족·미확인 검사를 비교하세요. 탐색 실행은 최적해 보증이나 강도·사용 승인이 아닙니다.", "review");
    return null;
  }
  function workflow(value, context = {}) {
    const job = context.kind === "job", status = own(value, "status");
    if (job) {
      const lifecycle = stopped(own(value, "cleanup_pending") === true ? "CLEANUP_PENDING" : status);
      if (lifecycle) return lifecycle;
      if (status !== "COMPLETED") return uncertain();
    }
    const result = job ? own(value, "result") : value;
    const failure = stopped(own(result, "status")) || stopped(own(result, "solver_status")) || stopped(own(result, "decision"));
    if (failure) return failure;
    if (context.stale === true) return step("기록의 재확인 필요", "선택한 기록이 바뀌었습니다. 결과를 다시 열어 원본 일치를 확인하세요.");
    if (job) {
      const operation = own(value, "operation"), metadata = recordedOperation(operation, result);
      if (metadata) return metadata;
      if (!["cad_run", "analysis_run", "pde_run", "model_analysis_run"].includes(operation) || !named(own(result, "experiment_id"))) return uncertain();
    }
    if (own(result, "status") !== "COMPLETED_REVIEW_REQUIRED") return uncertain();
    const solver = own(result, "solver_status"), backend = own(own(result, "provenance"), "adapter") ?? own(result, "backend");
    if (solver === "NOT_RUN") {
      if (["fixture.cadquery", "fixture.assembly", "fixture.freecad"].includes(backend) && named(own(result, "cad_revision")))
        return step("모델 준비됨 · 해석 안 함", cadNext(context, backend), "review");
      return step("해석 안 함", "모델과 입력 조건·실행 기록을 확인하세요. 사용할 수 있는 해석 결과는 아직 없습니다.");
    }
    if (["COMPLETED", "CONVERGED"].includes(solver)) {
      const convergence = own(result, "converged") === false ? "미수렴으로 기록됐습니다. " : own(result, "converged") === true ? "" : "수렴 여부는 미확인입니다. ";
      return step("해석 실행됨 · 결과 검토 필요", `${convergence}결과값과 검사 근거·남은 확인 사항을 확인하세요. 해석 실행만으로 강도나 사용 승인을 확정할 수 없습니다.`, "review");
    }
    return uncertain();
  }
  const api = { title, metricName, validationName, inputs, checks, faceDescription, workflow };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.resultPresentation = api;
})(typeof window !== "undefined" ? window : globalThis);
