"use strict";

// Presentation and request validation only. The server owns research admission.
(function (root, factory) {
  const controls = factory();
  if (typeof module === "object" && module.exports) module.exports = controls;
  if (root) root.researchControls = controls;
})(typeof window === "undefined" ? null : window, function () {
  const MODEL = "openai-codex/gpt-5.6-sol";
  const SESSION = /^ses_[A-Za-z0-9]+$/;
  const EXPERIMENT = /^[A-Za-z][A-Za-z0-9_-]{0,79}$/;
  function fullMatch(pattern, value) { return typeof value === "string" && pattern.exec(value)?.[0] === value; }
  const operationLabels = Object.freeze({
    study_create: "연구 기록 저장", parameter_discover: "CAD 변수 확인", parameter_register: "연구 변수 등록",
    registry_refresh: "원본 모델 변경 확인", cad_run: "CAD 생성·검사", native_create: "편집 가능한 CAD 생성",
    native_inspect: "원본 CAD 확인", native_final: "해석할 형상 선택", analysis_run: "CAD 구조 해석",
    pde_run: "편미분방정식 해석", model_analysis_run: "선언된 모델 해석", model_parameters_discover: "해석 모델 입력 확인",
    model_parameters_register: "해석 입력 등록", doe_plan: "설계 후보 계획", doe_run: "수치 후보 탐색",
    optimization_plan: "최적화 계획", optimization_run: "수치 최적화", model_optimization_plan: "모델 최적화 계획",
    experiment_inspect: "실험 결과 확인", study_inspect: "연구 기록 확인", capabilities: "지원 범위 확인",
    parameter_list: "등록된 연구 변수 확인", experiment_summary: "실험 결과 요약", experiment_compare: "실험 결과 비교",
    optimization_inspect: "최적화 실행 기록 확인",
  });
  const wireAliases = Object.freeze({ parameters_discover: "parameter_discover", parameters_register: "parameter_register",
    parameters_list: "parameter_list", experiment_run: "cad_run" });
  function operationLabel(value, fallback) {
    const wireName = value.replace(/^.*[.:/]/, "").replace(/^caelab_/, "");
    const name = Object.hasOwn(wireAliases, wireName) ? wireAliases[wireName] : wireName;
    return Object.hasOwn(operationLabels, name) ? operationLabels[name] : fallback;
  }
  const backendLabels = Object.freeze({
    "fixture.cadquery": "편집 가능한 CAD와 설계 변수", "fixture.freecad": "FreeCAD 원본 모델",
    "fixture.calculix": "CAD 구조 해석", "fixture.assembly": "전체 조립체 CAD",
    "structural.code_aster.contact_patch": "두 판의 마찰 없는 접촉",
    "pde.fenicsx": "편미분방정식 모델", "pde.fenicsx.imported": "가져온 메시의 편미분방정식",
  });
  const toolStatuses = Object.freeze({
    completed: "도구 응답 받음", running: "실행 중", pending: "대기 중", error: "도구 실패",
    COMPLETED: "도구 응답 받음", COMPLETED_REVIEW_REQUIRED: "응답 받음 · 검토 필요",
    RUNNING: "실행 중", FAILED: "도구 실패", FAILED_EXECUTION: "실행 실패", REJECTED: "조건 미충족",
    CANCELLED: "취소 완료", FAIL: "조건 미충족", PASS: "해당 검사 통과", UNKNOWN: "미확인", NOT_RELEASED: "공학적 사용 미승인",
  });
  function request(question, sessionId) {
    if (typeof question !== "string" || !question.trim()) throw new Error("연구하고 싶은 질문을 입력하세요.");
    // A lone surrogate would be replaced during UTF8 encoding, losing the input.
    for (let i = 0; i < question.length; i++) {
      const code = question.charCodeAt(i);
      if (code >= 0xd800 && code <= 0xdbff) {
        const next = question.charCodeAt(++i);
        if (!(next >= 0xdc00 && next <= 0xdfff)) throw new Error("질문의 문자 형식을 확인하세요.");
      } else if (code >= 0xdc00 && code <= 0xdfff) throw new Error("질문의 문자 형식을 확인하세요.");
    }
    if (new TextEncoder().encode(question).length > 16384) throw new Error("질문을 16 KiB 이내로 줄여 주세요.");
    const args = { question };
    if (sessionId !== undefined && sessionId !== null) {
      if (!fullMatch(SESSION, sessionId)) throw new Error("확인된 대화에서만 계속 질문할 수 있습니다.");
      args.session_id = sessionId;
    }
    return args;
  }
  function workspace(value) {
    try {
      const url = new URL(value);
      return ["http:", "https:"].includes(url.protocol) && ["127.0.0.1", "localhost", "[::1]"].includes(url.hostname)
        && !url.username && !url.password ? url.href : null;
    } catch { return null; }
  }
  function safeMessage(value, fallback = "AI 연구 연결을 확인할 수 없습니다. 연결 상태를 새로고침해 주세요.") {
    if (typeof value !== "string" || !value.trim() || value.length > 400 || !/[가-힣]/.test(value)
      || /[\\/`{}\u0000-\u0008\u000b\u000c\u000e-\u001f]|[A-Za-z]:|\b[A-Z][A-Z0-9]*_[A-Z0-9_]+\b/.test(value)) return fallback;
    return value;
  }
  function statusView(data) {
    const capabilities = Array.isArray(data?.capabilities) ? data.capabilities : [];
    const validCapabilities = capabilities.every(item => item && typeof item.backend === "string" && item.backend.length > 0
      && Array.isArray(item.operations) && item.operations.every(op => typeof op === "string" && op.length > 0));
    const ready = data?.configured === true && data.available === true && data.state === "READY" && data.model === MODEL
      && typeof data.profile === "string" && data.profile.length > 0 && workspace(data.workspace_url) !== null && validCapabilities;
    const recovery = data?.state === "RECOVERY_REQUIRED";
    return { ready, recovery, modelLabel: recovery ? "실행 상태 확인 필요" : data?.model === MODEL ? "GPT-5.6 Sol · ChatGPT" : "승인 모델 확인 필요",
      workspaceUrl: ready ? workspace(data.workspace_url) : null,
      reason: ready ? "승인된 모델에 연결됐습니다. 질문을 보내면 실제 AI 답변과 실행 기록이 여기에 나타납니다."
        : recovery ? "이전 작업의 완료·중단 여부가 확인되지 않았습니다. 새 실행은 차단되며 보존된 답변과 결과는 볼 수 있습니다."
          : safeMessage(data?.reason, data?.configured === false ? "AI 연구 연결이 준비되지 않았습니다." : undefined),
      scopes: ready ? capabilities.map(item => ({ label: backendLabels[item.backend] ?? "등록된 연구 모델",
        operations: item.operations.map(operation => operationLabel(operation, "등록된 도구")) })) : [] };
  }
  function canRun(status, context) {
    return statusView(status).ready && context?.local === true && context.writable === true && context.busy === false;
  }
  function toolView(item) {
    if (!item || typeof item.tool !== "string" || typeof item.status !== "string") return null;
    return { label: operationLabel(item.tool, "도구 실행"), status: item.status,
      statusLabel: Object.hasOwn(toolStatuses, item.status) ? toolStatuses[item.status] : "상태 확인 필요",
      experimentId: fullMatch(EXPERIMENT, item.experiment_id) ? item.experiment_id : null,
      raw: item };
  }
  function responseView(data, context = {}) {
    const valid = data?.kind === "openscience_research" && ["COMPLETED", "FAILED", "CANCELLED"].includes(data.status)
      && data.model === MODEL && typeof data.profile === "string" && typeof data.question === "string"
      && typeof data.answer === "string" && Array.isArray(data.tools) && data.completion_is_engineering_approval === false
      && data.decision === "NOT_RELEASED" && (context.question === undefined || data.question === context.question);
    if (!valid) return { valid: false, confirmed: false, answer: "", tools: [], reason: "AI 응답 형식을 확인할 수 없습니다. 작업 기록에서 원본 응답을 확인하세요." };
    const sessionValid = fullMatch(SESSION, data.session_id);
    const sourceValid = fullMatch(/^[0-9a-f]{40}$/, data.source_commit);
    const confirmed = data.status === "COMPLETED" && sessionValid && sourceValid && workspace(data.workspace_url) !== null
      && data.profile.length > 0;
    return { valid: true, confirmed, answer: data.answer, question: data.question, status: data.status,
      sessionId: sessionValid ? data.session_id : null, tools: data.tools.map(toolView),
      reason: typeof data.error === "string" && data.error.trim() ? safeMessage(data.error, data.status === "COMPLETED"
        ? "AI 연구 중 오류가 발생했습니다. 도구 상태와 원본 작업 기록을 확인하세요."
        : "AI 연구가 완료되지 않았습니다. 남은 답변과 작업 기록을 확인하세요.") : null };
  }
  function canContinue(result, status, context) {
    const view = responseView(result);
    return view.confirmed && statusView(status).ready && context?.local === true && context.writable === true
      && typeof context.resultStore === "string" && context.resultStore === context.activeStore
      && result.model === status.model && result.profile === status.profile && result.workspace_url === status.workspace_url;
  }
  function progressView(data) {
    const valid = data?.model === MODEL && typeof data.answer === "string" && Array.isArray(data.tools)
      && typeof data.cleanup_pending === "boolean" && data.completion_is_engineering_approval === false && data.decision === "NOT_RELEASED"
      && (data.session_id === null || fullMatch(SESSION, data.session_id));
    return valid ? { valid: true, confirmed: false, answer: data.answer, tools: data.tools.map(toolView), cleanupPending: data.cleanup_pending }
      : { valid: false, confirmed: false, answer: "", tools: [], cleanupPending: false, reason: "진행 기록을 확인할 수 없습니다. 작업 원본 기록을 확인하세요." };
  }
  // Small presentation subset. No HTML, link resolution or numeric conversion.
  // The exact raw string remains available even when syntax is formatted.
  function mathRanges(value) {
    const spans = new Map(); let opening = null, closing = null;
    for (const token of value.matchAll(/\\[()[\]]/g)) {
      let slashes = 0;
      for (let index = token.index - 1; index >= 0 && value[index] === "\\"; index--) slashes++;
      if (slashes % 2) continue;
      const delimiter = token[0][1];
      if (opening === null && (delimiter === "(" || delimiter === "[")) {
        opening = token.index; closing = delimiter === "(" ? ")" : "]";
      } else if (opening !== null && delimiter === closing) {
        spans.set(opening, { end: token.index + 2, display: closing === "]" });
        opening = closing = null;
      }
    }
    return spans;
  }
  function answerInline(value, depth = 0) {
    const parts = [], math = mathRanges(value); let start = 0, position = 0;
    while (position < value.length) {
      const expression = math.get(position);
      if (expression) {
        if (start < position) parts.push({ type: "text", text: value.slice(start, position) });
        parts.push({ type: "math", text: value.slice(position + 2, expression.end - 2), display: expression.display });
        position = start = expression.end; continue;
      }
      const marker = value[position] === "`" && value[position - 1] !== "`" && value[position + 1] !== "`" ? "`"
        : value.startsWith("**", position) ? "**" : value[position] === "*" ? "*" : null;
      if (!marker || (marker !== "`" && position > 0 && !/[\s([{]/.test(value[position - 1]))) { position++; continue; }
      const close = value.indexOf(marker, position + marker.length), content = close < 0 ? "" : value.slice(position + marker.length, close);
      const codeEnd = marker !== "`" || (value[close - 1] !== "`" && value[close + 1] !== "`");
      const emphasisEnd = marker !== "*" || close + 1 === value.length || /[\s.,;:!?)\]}]/.test(value[close + 1]);
      if (close < 0 || !content.trim() || !codeEnd || !emphasisEnd) { position += marker.length; continue; }
      if (start < position) parts.push({ type: "text", text: value.slice(start, position) });
      if (marker === "`") parts.push({ type: "code", text: content });
      else parts.push({ type: marker === "**" ? "strong" : "em", parts: depth < 2 ? answerInline(content, depth + 1) : [{ type: "text", text: content }] });
      position = close + marker.length; start = position;
    }
    if (start < value.length) parts.push({ type: "text", text: value.slice(start) });
    return parts;
  }
  function answerBlocks(raw) {
    if (typeof raw !== "string") throw new TypeError("답변 원문은 문자열이어야 합니다.");
    const lines = raw.split(/\r\n|\n|\r/), starts = [0], blocks = []; let index = 0;
    for (const ending of raw.matchAll(/\r\n|\n|\r/g)) starts.push(ending.index + ending[0].length);
    const marker = line => /^\s*([-+*]|\d+[.)])[ \t]+(.*)$/.exec(line);
    const fenced = line => /^\s*(`{3,}|~{3,})([^`]*)$/.exec(line);
    const cells = line => {
      if (!line.includes("|")) return null;
      const body = line.trim(), math = mathRanges(body), ticks = [...body.matchAll(/`+/g)], closes = new Map(), next = new Map();
      // Exact backtick-run matches, prepared once, keep each row linear-time.
      // Unmatched or escaped opening runs are literal, not a guessed code span.
      for (let index = ticks.length - 1; index >= 0; index--) {
        const tick = ticks[index], length = tick[0].length;
        if (next.has(length)) closes.set(tick.index, next.get(length));
        next.set(length, tick.index + length);
      }
      const values = []; let value = [], slashes = 0, firstSeparator = -1, lastSeparator = -1;
      for (let position = 0; position < body.length;) {
        const character = body[position], close = closes.get(position);
        const expression = math.get(position);
        if (expression && slashes % 2 === 0) {
          value.push(body.slice(position, expression.end)); position = expression.end; slashes = 0; continue;
        }
        if (character === "`" && slashes % 2 === 0 && close !== undefined) {
          value.push(body.slice(position, close)); position = close; slashes = 0; continue;
        }
        if (character === "|") {
          if (slashes % 2 === 1) { value.pop(); value.push("|"); } // Remove only the delimiter escape for display.
          else {
            if (firstSeparator < 0) firstSeparator = position;
            lastSeparator = position; values.push(value.join("").trim()); value = [];
          }
        } else value.push(character);
        slashes = character === "\\" ? slashes + 1 : 0; position++;
      }
      values.push(value.join("").trim());
      if (firstSeparator === 0) values.shift();
      if (lastSeparator === body.length - 1) values.pop();
      return values.length >= 2 ? values : null;
    };
    const tableAt = position => {
      const header = cells(lines[position] ?? ""), rule = cells(lines[position + 1] ?? "");
      return header && rule?.length === header.length && rule.every(value => /^:?-{3,}:?$/.test(value)) ? header : null;
    };
    while (index < lines.length) {
      if (!lines[index].trim()) { index++; continue; }
      const fence = fenced(lines[index]);
      if (fence) {
        const start = index++; const closing = fence[1];
        while (index < lines.length && lines[index].trim() !== closing) index++;
        if (index < lines.length) index++;
        blocks.push({ type: "technical", text: raw.slice(starts[start], starts[index] ?? raw.length) }); continue;
      }
      const header = tableAt(index);
      if (header) {
        const start = index, rows = []; index += 2; let valid = true;
        while (index < lines.length && lines[index].trim() && lines[index].includes("|")) {
          const row = cells(lines[index]); if (!row || row.length !== header.length) valid = false;
          rows.push(row); index++;
        }
        blocks.push(valid ? { type: "table", header: header.map(value => answerInline(value)), rows: rows.map(row => row.map(value => answerInline(value))) }
          : { type: "paragraph", parts: answerInline(lines.slice(start, index).join("\n")) }); continue;
      }
      const first = marker(lines[index]);
      if (first) {
        const ordered = /^\d/.test(first[1]), items = [];
        while (index < lines.length) {
          const match = marker(lines[index]); if (!match || /^\d/.test(match[1]) !== ordered) break;
          const label = match[1], content = [match[2]]; index++;
          while (index < lines.length && lines[index].trim() && !marker(lines[index]) && !fenced(lines[index]) && !tableAt(index)) content.push(lines[index++]);
          items.push({ marker: label, parts: answerInline(content.join("\n")) });
        }
        blocks.push({ type: "list", ordered, items }); continue;
      }
      const content = [lines[index++]];
      while (index < lines.length && lines[index].trim() && !marker(lines[index]) && !fenced(lines[index]) && !tableAt(index)) content.push(lines[index++]);
      blocks.push({ type: "paragraph", parts: answerInline(content.join("\n")) });
    }
    return { raw, blocks };
  }
  function jobWorkflow(job) {
    if (job.status === "RECOVERY_REQUIRED") return { tone: "unknown", stage: "실행 상태 확인 필요 · 새 작업 차단", next: "이전 작업의 완료·중단 여부가 확인되지 않았습니다. 보존된 답변과 결과는 볼 수 있으며, 실행 상태가 확인되기 전에는 새 작업을 시작하지 않습니다." };
    const progress = progressView(job.progress);
    if (job.status === "CLEANUP_PENDING" || (job.status === "CANCEL_REQUESTED" && progress.cleanupPending)) return { tone: "pending", stage: "AI 연구 종료 확인 중", next: "종료를 확인할 때까지 다음 작업은 시작할 수 없습니다. 받은 답변과 작업 기록은 보존됩니다." };
    if (job.status === "CANCEL_REQUESTED") return { tone: "pending", stage: "AI 연구 취소 처리 중", next: "실제 실행의 종료를 확인하고 있습니다. 부분 답변과 실행 기록은 보존됩니다." };
    if (job.status === "RUNNING") return { tone: "pending", stage: "AI 연구 실행 중", next: progress.valid && (progress.answer || progress.tools.length)
      ? "지금까지 받은 실제 답변과 도구 상태를 표시합니다. 최종 종료를 확인한 뒤 다음 질문을 보낼 수 있습니다."
      : "연결된 AI가 질문을 처리하고 있습니다. 실제 답변과 도구 기록은 반환되면 표시됩니다." };
    const response = responseView(job.result);
    if (job.status === "FAILED" || job.result?.status === "FAILED") return { tone: "failed", stage: "AI 연구 실패", next: response.answer ? "남은 부분 답변과 도구 기록을 확인하세요. 새 질문으로 다시 시작할 수 있습니다." : "연구를 완료하지 못했습니다. 연결 상태와 작업 기록을 확인하세요." };
    if (job.status === "CANCELLED" || job.result?.status === "CANCELLED") return { tone: "cancelled", stage: "AI 연구 취소 완료", next: "부분 답변과 실행 기록은 보존됩니다. 다음 질문은 새 대화로 시작하세요." };
    if (job.status === "COMPLETED" && response.valid && typeof job.result.error === "string" && job.result.error.trim()) return {
      tone: "failed", stage: "AI 연구 중 오류 발생", next: "받은 답변과 실패한 도구 기록을 확인하세요. AI 응답 수신과 실제 해석·검증 판정은 별개입니다." };
    if (job.status === "COMPLETED" && response.valid) return { tone: "recorded", stage: "AI 응답 받음 · 결과 검토 필요", next: "답변과 연결된 실험을 확인하세요. 수치 검증과 공학적 사용 승인은 각 실험의 판정을 따릅니다." };
    return { tone: "unknown", stage: "AI 연구 상태 미확인", next: "작업 기록에서 실제 응답과 종료 상태를 확인하세요." };
  }
  function phaseLabel(value, data) {
    const phases = { RUNTIME_VERIFY: "AI 연구 실행 환경을 확인하고 있습니다.", RESIDENT_VERIFY: "연결된 AI 실행기의 준비 상태를 확인하고 있습니다.",
      CLI_PREFLIGHT: "질문을 보내기 전에 대화와 실행 조건을 확인하고 있습니다.", END_VERIFY: "답변과 도구 실행의 종료 상태를 확인하고 있습니다." };
    if (typeof value !== "string" || !Object.hasOwn(phases, value)) return null;
    const progress = progressView(data);
    const received = progress.valid && (progress.answer.trim() || progress.tools.some(tool => tool && tool.status.trim()));
    return value !== "END_VERIFY" && received ? null : phases[value];
  }
  return Object.freeze({ MODEL, request, workspace, safeMessage, statusView, canRun, toolView, responseView, canContinue, progressView, answerBlocks, phaseLabel, jobWorkflow });
});
