import { useEffect } from "react";
import {
  Play,
  Plus,
  CheckCheck,
  RotateCcw,
  Square,
  Search,
  FileText,
  Layers,
  Pin,
  GitCompareArrows,
  RefreshCw,
} from "lucide-react";
import {
  Workspace,
  Toolbar,
  Button,
  Badge,
  Field,
  Properties,
  DataGrid,
  Chart,
  useStored,
  Notice,
} from "./common";
import "./RunnerOptimization.css";

type Input = {
  name: string;
  backend: string;
  duration: number;
  cells: number;
  material: string;
};
type Draft = {
  id: string;
  input: Input;
  validation: "unchecked" | "invalid" | "ready";
  errors: string[];
  source?: string;
};
type Job = {
  id: string;
  requestId: string;
  documentId: string;
  input: Input;
  status: "running" | "completed" | "cancelled" | "failed";
  progress: number;
  created: string;
  log: string[];
};
type RunState = {
  jobs: Job[];
  documents: Record<string, Input>;
  selectedId: string;
  draft: Draft | null;
  view: "jobs" | "draft";
  pendingRequest: string | null;
};
const initialInput: Input = {
  name: "재료점 인장 응답",
  backend: "재료점 · 합성 실행기",
  duration: 1,
  cells: 1000,
  material: "Steel_sample",
};
const newId = (prefix: string) =>
  `${prefix}-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 6)}`;
const inputErrors = (input: Input) =>
  [
    !input.name.trim() && "실행 이름을 입력하세요.",
    !Number.isFinite(input.duration) || input.duration <= 0
      ? "종료 시간은 0보다 큰 수여야 합니다."
      : "",
    !Number.isInteger(input.cells) || input.cells < 1 || input.cells > 1000000
      ? "표본/요소 수는 1~1,000,000의 정수여야 합니다."
      : "",
    !input.material.trim() && "재료 또는 데이터 이름을 입력하세요.",
  ].filter(Boolean) as string[];
const runSeed = (): RunState => {
  const inputs: Input[] = [
    initialInput,
    {
      ...initialInput,
      name: "판 변위 기준 계산",
      backend: "구조 · 합성 실행기",
      cells: 4800,
    },
    {
      ...initialInput,
      name: "열 확산 메시 검사",
      backend: "PDE · 합성 실행기",
      cells: 22000,
    },
  ];
  const jobs: Job[] = inputs.map((input, i) => ({
    id: `JOB-${String(i + 1).padStart(4, "0")}`,
    requestId: `REQ-SEED-${i}`,
    documentId: `DOC-SEED-${i}`,
    input: { ...input },
    status: i === 2 ? "failed" : "completed",
    progress: i === 2 ? 15 : 100,
    created: `13:${10 + i}:00`,
    log: [
      "[시안] 제출 입력 스냅샷을 저장했습니다.",
      "[시안] 합성 실행 상태를 생성했습니다.",
      i === 2
        ? "[오류 예시] 경계 조건이 없어 진행하지 못했습니다."
        : "[시안] 합성 결과가 준비되었습니다. 실제 솔버 실행 없음.",
    ],
  }));
  return {
    jobs,
    documents: Object.fromEntries(jobs.map((j) => [j.documentId, j.input])),
    selectedId: jobs[0].id,
    draft: null,
    view: "jobs",
    pendingRequest: null,
  };
};
const statusLabel = {
  running: "실행 중",
  completed: "완료",
  cancelled: "취소됨",
  failed: "실패",
};
const statusTone = {
  running: "info",
  completed: "good",
  cancelled: "neutral",
  failed: "bad",
} as const;

export function Runner() {
  const [state, setState] = useStored<RunState>(
    "prototype-v1.runner",
    runSeed(),
  );
  const selected = state.jobs.find((j) => j.id === state.selectedId);
  const draft = state.draft;
  useEffect(() => {
    const timer = window.setInterval(
      () =>
        setState((current) => {
          if (!current.jobs.some((j) => j.status === "running")) return current;
          return {
            ...current,
            jobs: current.jobs.map((j) => {
              if (j.status !== "running") return j;
              const progress = Math.min(100, j.progress + 8);
              const complete = progress === 100;
              return {
                ...j,
                progress,
                status: complete ? "completed" : "running",
                log: complete
                  ? [
                      ...j.log,
                      "[시안] 합성 진행이 완료되었습니다. 실제 계산 결과가 아닙니다.",
                    ]
                  : [...j.log, `[시안] 합성 진행률 ${progress}%`],
              };
            }),
          };
        }),
      1500,
    );
    return () => window.clearInterval(timer);
  }, [setState]);
  const createDraft = (input = initialInput, source?: string) =>
    setState((current) =>
      current.pendingRequest
        ? current
        : {
            ...current,
            view: "draft",
            draft: {
              id: newId("DRAFT"),
              input: {
                ...input,
                name: source ? `${input.name} · 재실행` : input.name,
              },
              validation: "unchecked",
              errors: [],
              source,
            },
          },
    );
  const updateInput = (key: keyof Input, value: string | number) =>
    setState((current) =>
      current.draft
        ? {
            ...current,
            draft: {
              ...current.draft,
              input: { ...current.draft.input, [key]: value },
              validation: "unchecked",
              errors: [],
            },
          }
        : current,
    );
  const validate = () =>
    setState((current) => {
      if (!current.draft) return current;
      const errors = inputErrors(current.draft.input);
      return {
        ...current,
        draft: {
          ...current.draft,
          errors,
          validation: errors.length ? "invalid" : "ready",
        },
      };
    });
  const submit = (loseResponse = false) =>
    setState((current) => {
      if (
        !current.draft ||
        current.draft.validation !== "ready" ||
        inputErrors(current.draft.input).length ||
        current.pendingRequest
      )
        return current;
      // The draft ID is the idempotency key; a lost response never creates another job.
      const requestId = `REQ-${current.draft.id}`;
      const existing = current.jobs.find((j) => j.requestId === requestId);
      if (existing)
        return {
          ...current,
          selectedId: existing.id,
          view: "jobs",
          pendingRequest: null,
        };
      const input = { ...current.draft.input };
      const documentId = newId("DOC");
      const job: Job = {
        id: newId("JOB"),
        requestId,
        documentId,
        input,
        progress: 0,
        status: "running",
        created: new Date().toLocaleTimeString("ko-KR", { hour12: false }),
        log: [
          "[시안] 요청을 접수하고 제출 입력을 고정했습니다.",
          "[시안] 합성 실행 시작 · 네트워크 및 실제 솔버 연결 없음.",
        ],
      };
      return {
        ...current,
        jobs: [job, ...current.jobs],
        documents: { ...current.documents, [documentId]: input },
        pendingRequest: loseResponse ? requestId : null,
        selectedId: loseResponse ? current.selectedId : job.id,
        view: loseResponse ? "draft" : "jobs",
        draft: loseResponse ? current.draft : null,
      };
    });
  const recover = () =>
    setState((current) => {
      const job = current.jobs.find(
        (j) => j.requestId === current.pendingRequest,
      );
      return job
        ? {
            ...current,
            selectedId: job.id,
            view: "jobs",
            draft: null,
            pendingRequest: null,
          }
        : current;
    });
  const cancel = () =>
    setState((current) => ({
      ...current,
      jobs: current.jobs.map((j) =>
        j.id === current.selectedId && j.status === "running"
          ? {
              ...j,
              status: "cancelled",
              log: [...j.log, `[시안] 사용자가 ${j.id} 실행을 취소했습니다.`],
            }
          : j,
      ),
    }));
  const inputForm = (input: Input, editable: boolean) => (
    <div className="form-grid">
      <Field label="실행 이름">
        <input
          aria-label="실행 이름"
          value={input.name}
          readOnly={!editable}
          onChange={(e) => updateInput("name", e.target.value)}
        />
      </Field>
      <Field label="실행기">
        <select
          aria-label="실행기"
          value={input.backend}
          disabled={!editable}
          onChange={(e) => updateInput("backend", e.target.value)}
        >
          {[
            "재료점 · 합성 실행기",
            "구조 · 합성 실행기",
            "PDE · 합성 실행기",
            "외부 결과 · 합성 실행기",
          ].map((v) => (
            <option key={v}>{v}</option>
          ))}
        </select>
      </Field>
      <Field label="종료 시간 [s]">
        <input
          aria-label="종료 시간"
          type="number"
          value={Number.isNaN(input.duration) ? "" : input.duration}
          readOnly={!editable}
          onChange={(e) =>
            updateInput(
              "duration",
              e.target.value === "" ? 0 : Number(e.target.value),
            )
          }
        />
      </Field>
      <Field label="표본 / 요소 수">
        <input
          aria-label="표본 또는 요소 수"
          type="number"
          value={Number.isNaN(input.cells) ? "" : input.cells}
          readOnly={!editable}
          onChange={(e) =>
            updateInput(
              "cells",
              e.target.value === "" ? 0 : Number(e.target.value),
            )
          }
        />
      </Field>
      <Field label="재료 / 데이터">
        <input
          aria-label="재료 또는 데이터"
          value={input.material}
          readOnly={!editable}
          onChange={(e) => updateInput("material", e.target.value)}
        />
      </Field>
    </div>
  );
  const jobsPanel = (
    <div className="panel-stack">
      <div className="ro-strip spread">
        <span>{state.jobs.length}개 실행 · 선택은 ID로 유지</span>
        <span className="muted">다른 실행이 완료되어도 현재 선택 유지</span>
      </div>
      <div className="ro-grid-fill">
        <DataGrid
          rows={state.jobs.map((j) => ({
            ...j,
            name: j.input.name,
            backend: j.input.backend,
            statusText: statusLabel[j.status],
            progressText: `${j.progress}%`,
          }))}
          selectedId={state.selectedId}
          onSelect={(row: Job) =>
            setState((current) => ({ ...current, selectedId: row.id }))
          }
          columns={[
            { field: "id", headerName: "실행 ID", minWidth: 185, flex: 1.1 },
            { field: "name", headerName: "이름", minWidth: 180, flex: 1.4 },
            { field: "statusText", headerName: "상태", width: 100 },
            { field: "progressText", headerName: "진행", width: 85 },
            { field: "backend", headerName: "실행기", minWidth: 170, flex: 1 },
            { field: "created", headerName: "제출 시간", width: 105 },
          ]}
        />
      </div>
    </div>
  );
  const detailPanel = selected ? (
    <div className="panel-stack">
      <div className="panel-scroll">
        <div className="spread ro-heading">
          <strong className="mono">{selected.id}</strong>
          <Badge tone={statusTone[selected.status]}>
            {statusLabel[selected.status]}
          </Badge>
        </div>
        <div className="ro-progress">
          <span style={{ width: `${selected.progress}%` }} />
        </div>
        <Properties
          rows={[
            ["진행률", `${selected.progress}%`],
            [
              "요청 ID",
              <span className="mono ro-wrap">{selected.requestId}</span>,
            ],
            [
              "입력 문서",
              <span className="mono ro-wrap">{selected.documentId}</span>,
            ],
            ["제출 시간", selected.created],
          ]}
        />
        <h3 className="section-title">제출 입력 · 읽기 전용</h3>
        {inputForm(
          state.documents[selected.documentId] || selected.input,
          false,
        )}
        <Notice>
          이 실행의 입력은 제출 시 고정됩니다. 재실행은 별도 초안과 실행 ID를
          만듭니다.
        </Notice>
      </div>
      <div className="ro-footer">
        <Button
          icon={RotateCcw}
          disabled={!!state.pendingRequest}
          onClick={() => createDraft(selected.input, selected.id)}
        >
          이 입력으로 새 초안
        </Button>
        <Button
          icon={Square}
          danger
          disabled={selected.status !== "running"}
          onClick={cancel}
        >
          선택 실행 취소
        </Button>
      </div>
    </div>
  ) : (
    <div className="panel-scroll muted">실행을 선택하세요.</div>
  );
  const logPanel = (
    <div className="panel-stack">
      <div className="ro-strip">
        <span className="mono">{selected?.id || "—"}</span>
        <span className="muted"> · 선택 실행 로그</span>
      </div>
      <pre className="ro-log panel-scroll">
        {selected?.log.join("\n") || "로그 없음"}
      </pre>
    </div>
  );
  const draftPanel = draft ? (
    <div className="panel-stack">
      <div className="panel-scroll ro-draft-body">
        <div className="spread ro-heading">
          <strong>새 실행 초안</strong>
          <Badge
            tone={
              draft.validation === "ready"
                ? "good"
                : draft.validation === "invalid"
                  ? "bad"
                  : "neutral"
            }
          >
            {draft.validation === "ready"
              ? "제출 준비됨"
              : draft.validation === "invalid"
                ? "검사 실패"
                : "검사 전"}
          </Badge>
        </div>
        <div className="ro-run-steps">
          <span className="active">1 입력 편집</span>
          <span className={draft.validation !== "unchecked" ? "active" : ""}>
            2 입력 검사
          </span>
          <span className={draft.validation === "ready" ? "active" : ""}>
            3 제출
          </span>
        </div>
        <Properties
          rows={[
            ["초안 ID", <span className="mono">{draft.id}</span>],
            ["원본 실행", draft.source || "새 입력"],
            ["저장", "로컬 브라우저에 자동 저장"],
          ]}
        />
        <h3 className="section-title">실행 입력</h3>
        <fieldset disabled={!!state.pendingRequest} className="ro-fieldset">
          {inputForm(draft.input, true)}
        </fieldset>
        {draft.errors.length > 0 && (
          <Notice tone="bad">
            <strong>제출할 수 없습니다.</strong>
            <ul>
              {draft.errors.map((error) => (
                <li key={error}>{error}</li>
              ))}
            </ul>
          </Notice>
        )}
        {draft.validation === "ready" && !state.pendingRequest && (
          <Notice tone="good">
            입력 검사를 통과했습니다. 편집하면 다시 검사해야 합니다.
          </Notice>
        )}
        {state.pendingRequest && (
          <Notice tone="warn">
            <strong>제출 응답 유실 예시</strong>
            <p>
              요청은 접수되었지만 응답을 받지 못했습니다. 요청 ID로 이미 생성된
              실행을 조회하세요.
            </p>
            <p className="mono ro-wrap">{state.pendingRequest}</p>
            <Button icon={Search} primary onClick={recover}>
              요청 조회 · 같은 실행 복구
            </Button>
          </Notice>
        )}
        <Notice>
          로컬 상호작용 시안입니다. 제출과 실행 진행은 합성 상태이며 실제 솔버를
          호출하지 않습니다.
        </Notice>
      </div>
      <div className="ro-footer">
        <Button
          icon={CheckCheck}
          disabled={!!state.pendingRequest}
          onClick={validate}
        >
          입력 검사
        </Button>
        <Button
          icon={Play}
          primary
          disabled={draft.validation !== "ready" || !!state.pendingRequest}
          onClick={() => submit()}
        >
          제출
        </Button>
        <Button
          icon={RefreshCw}
          disabled={draft.validation !== "ready" || !!state.pendingRequest}
          onClick={() => submit(true)}
        >
          응답 유실 시험
        </Button>
      </div>
    </div>
  ) : (
    <div className="panel-scroll">초안 없음</div>
  );
  const guide = (
    <div className="panel-scroll">
      <h3 className="section-title">실행 흐름</h3>
      <ol className="ro-instructions">
        <li>입력을 편집한 뒤 입력 검사를 누릅니다.</li>
        <li>준비된 입력을 제출하면 새 실행이 만들어집니다.</li>
        <li>표에서 실행을 선택해 제출 입력과 로그를 확인합니다.</li>
        <li>응답 유실 시 요청 조회로 같은 실행을 복구합니다.</li>
      </ol>
      <h3 className="section-title">현재 보관</h3>
      <Properties
        rows={[
          ["실행", `${state.jobs.length}개`],
          ["제출 입력 문서", `${Object.keys(state.documents).length}개`],
          [
            "실행 중",
            `${state.jobs.filter((j) => j.status === "running").length}개`,
          ],
        ]}
      />
      <Notice>
        입력 오류와 실행 오류는 별도 상태입니다. 초기 실패 실행은 경계 조건
        오류를 보여 주는 합성 예시입니다.
      </Notice>
    </div>
  );
  return (
    <>
      <Toolbar>
        <Button
          icon={Plus}
          primary
          disabled={!!state.pendingRequest}
          onClick={() => createDraft()}
        >
          새 실행
        </Button>
        <Button
          icon={Layers}
          onClick={() => setState((current) => ({ ...current, view: "jobs" }))}
        >
          실행 목록
        </Button>
        {draft && (
          <Button
            icon={FileText}
            onClick={() =>
              setState((current) => ({ ...current, view: "draft" }))
            }
          >
            초안 열기
          </Button>
        )}
        <span className="ro-toolbar-context">
          Runner <span className="muted">/ 합성 실행 상태 · 로컬 저장</span>
        </span>
        {state.pendingRequest && (
          <Button icon={Search} onClick={recover}>
            미확인 요청 조회
          </Button>
        )}
      </Toolbar>
      {state.view === "draft" ? (
        <Workspace
          key="runner-draft"
          id="runner-draft"
          panels={{
            draft: { title: "새 실행 · 입력 편집", content: draftPanel },
            guide: { title: "검사 및 제출 안내", content: guide },
          }}
          setup={(api) => {
            api.addPanel({
              id: "draft",
              component: "content",
              title: "새 실행 · 입력 편집",
            });
            api.addPanel({
              id: "guide",
              component: "content",
              title: "검사 및 제출 안내",
              position: { referencePanel: "draft", direction: "right" },
              initialWidth: 350,
            });
          }}
        />
      ) : (
        <Workspace
          key="runner-jobs"
          id="runner-jobs"
          panels={{
            jobs: { title: "실행 목록", content: jobsPanel },
            detail: { title: "선택 실행 · 제출 입력", content: detailPanel },
            log: { title: "선택 실행 · 로그", content: logPanel },
          }}
          setup={(api) => {
            api.addPanel({
              id: "jobs",
              component: "content",
              title: "실행 목록",
            });
            api.addPanel({
              id: "detail",
              component: "content",
              title: "선택 실행 · 제출 입력",
              position: { referencePanel: "jobs", direction: "below" },
              initialHeight: 340,
            });
            api.addPanel({
              id: "log",
              component: "content",
              title: "선택 실행 · 로그",
              position: { referencePanel: "detail", direction: "right" },
            });
          }}
        />
      )}
    </>
  );
}

type Variable = {
  id: string;
  label: string;
  unit: string;
  min: number;
  max: number;
};
type Candidate = {
  id: string;
  iteration: number;
  state: "evaluated" | "predicted" | "failed" | "invalid";
  thickness: number;
  modulus: number;
  density: number;
  mass: number | null;
  response: number | null;
  rangeVersion: number;
  reason?: string;
};
type OptState = {
  ranges: Variable[];
  draftRanges: Variable[];
  rangeVersion: number;
  candidates: Candidate[];
  selectedId: string;
  baselineId: string;
  variableId: string;
  plotMode: "pareto" | "variable";
  error: string;
};
const rangeSeed: Variable[] = [
  { id: "thickness", label: "두께", unit: "mm", min: 1, max: 4 },
  { id: "modulus", label: "탄성 계수", unit: "GPa", min: 140, max: 220 },
  { id: "density", label: "밀도", unit: "kg/m³", min: 7000, max: 8000 },
];
const generateCandidates = (
  ranges: Variable[],
  rangeVersion: number,
  iteration: number,
  start: number,
): Candidate[] =>
  Array.from({ length: 24 }, (_, i) => {
    const value = (key: string, step: number) => {
      const range = ranges.find((r) => r.id === key)!;
      return Number(
        (
          range.min +
          (range.max - range.min) * (((i * step) % 23) / 23)
        ).toFixed(3),
      );
    };
    const thickness = value("thickness", 7),
      modulus = value("modulus", 11),
      density = value("density", 17);
    const state =
      i === 6
        ? "invalid"
        : i === 13
          ? "failed"
          : [8, 17, 20].includes(i)
            ? "predicted"
            : "evaluated";
    return {
      id: `C${String(start + i).padStart(3, "0")}`,
      iteration,
      state,
      thickness,
      modulus,
      density,
      mass:
        state === "failed" || state === "invalid"
          ? null
          : Number(((thickness * density) / 1000).toFixed(2)),
      response:
        state === "failed" || state === "invalid"
          ? null
          : Number(
              (
                8 / ((thickness ** 1.4 * modulus) / 180) +
                0.2 * Math.sin(i)
              ).toFixed(3),
            ),
      rangeVersion,
      reason:
        state === "invalid"
          ? "입력 검사 실패 예시 · 형상 제약 위반"
          : state === "failed"
            ? "합성 실행 실패 예시 · 응답 파일 없음"
            : undefined,
    };
  });
const optSeed = (): OptState => ({
  ranges: rangeSeed.map((r) => ({ ...r })),
  draftRanges: rangeSeed.map((r) => ({ ...r })),
  rangeVersion: 1,
  candidates: generateCandidates(rangeSeed, 1, 1, 1),
  selectedId: "C001",
  baselineId: "C004",
  variableId: "thickness",
  plotMode: "pareto",
  error: "",
});
const candidateLabel = {
  evaluated: "합성 평가",
  predicted: "예측",
  failed: "실패",
  invalid: "입력 오류",
};
const candidateTone = {
  evaluated: "good",
  predicted: "warn",
  failed: "bad",
  invalid: "bad",
} as const;
const numberText = (v: number | null, digits = 3) =>
  v === null ? "—" : v.toFixed(digits);
const curve = (candidate: Candidate) => {
  const x = Array.from({ length: 61 }, (_, i) => i / 60);
  const y = x.map((t) =>
    Number(
      (
        (candidate.response || 0) *
        (1 - Math.exp(-7 * t)) *
        (1 + 0.035 * Math.sin(t * 28))
      ).toFixed(4),
    ),
  );
  return { x, y };
};

export function Optimization() {
  const [state, setState] = useStored<OptState>(
    "prototype-v1.optimization",
    optSeed(),
  );
  const selected = state.candidates.find((c) => c.id === state.selectedId)!;
  const baseline = state.candidates.find((c) => c.id === state.baselineId);
  const activeVariable = state.ranges.find((r) => r.id === state.variableId)!;
  const rangesDirty =
    JSON.stringify(state.ranges) !== JSON.stringify(state.draftRanges);
  const select = (id: string) => {
    if (state.candidates.some((c) => c.id === id))
      setState((current) => ({ ...current, selectedId: id }));
  };
  const editRange = (edit: unknown) => {
    const event = edit as {
      data?: Variable;
      id?: string;
      min?: number;
      max?: number;
    };
    const row = event.data || (event as Variable);
    if (!row.id) return;
    setState((current) => ({
      ...current,
      draftRanges: current.draftRanges.map((r) =>
        r.id === row.id
          ? { ...r, min: Number(row.min), max: Number(row.max) }
          : r,
      ),
      error: "",
    }));
  };
  const applyRanges = () =>
    setState((current) => {
      const errors = current.draftRanges.filter(
        (r) =>
          !Number.isFinite(r.min) ||
          !Number.isFinite(r.max) ||
          r.min <= 0 ||
          r.max <= r.min,
      );
      if (errors.length)
        return {
          ...current,
          error: `${errors.map((r) => r.label).join(", ")}: 0 < 하한 < 상한이어야 합니다.`,
        };
      return {
        ...current,
        ranges: current.draftRanges.map((r) => ({ ...r })),
        rangeVersion: current.rangeVersion + 1,
        error: "",
      };
    });
  const generate = () =>
    setState((current) => ({
      ...current,
      candidates: [
        ...current.candidates,
        ...generateCandidates(
          current.ranges,
          current.rangeVersion,
          Math.max(...current.candidates.map((c) => c.iteration)) + 1,
          current.candidates.length + 1,
        ),
      ],
    }));
  const variablePlot = state.plotMode === "variable";
  const xValue = (candidate: Candidate) =>
    variablePlot
      ? candidate[activeVariable.id as "thickness" | "modulus" | "density"]
      : candidate.mass;
  const valid = state.candidates.filter(
    (c) => c.response !== null && c.mass !== null,
  );
  const scatterTrace = (kind: Candidate["state"]) => {
    const rows = valid.filter((c) => c.state === kind);
    return {
      x: rows.map(xValue),
      y: rows.map((c) => c.response),
      customdata: rows.map((c) => c.id),
      text: rows.map((c) => `${c.id} · ${candidateLabel[c.state]}`),
      type: "scatter",
      mode: "markers",
      name: kind === "evaluated" ? "합성 평가값" : "예측값",
      marker: {
        color: kind === "evaluated" ? "#4e79a7" : "#cb8b2b",
        size: 8,
        symbol: kind === "evaluated" ? "circle" : "diamond-open",
      },
      hovertemplate: variablePlot
        ? "%{text}<br>%{x}<br>최대 변위 %{y:.3f} mm<extra></extra>"
        : "%{text}<br>질량 %{x:.2f} kg<br>최대 변위 %{y:.3f} mm<extra></extra>",
    };
  };
  const selectedScatter =
    selected.response !== null
      ? [
          {
            x: [xValue(selected)],
            y: [selected.response],
            customdata: [selected.id],
            name: `선택 ${selected.id}`,
            type: "scatter",
            mode: "markers",
            marker: {
              color: "#1262b8",
              size: 15,
              symbol: "circle-open",
              line: { width: 3 },
            },
            hovertemplate: `${selected.id}<extra></extra>`,
          },
        ]
      : [];
  const baselineScatter =
    baseline?.response !== null && baseline
      ? [
          {
            x: [xValue(baseline)],
            y: [baseline.response],
            customdata: [baseline.id],
            name: `기준 ${baseline.id}`,
            type: "scatter",
            mode: "markers",
            marker: {
              color: "#637180",
              size: 12,
              symbol: "square-open",
              line: { width: 2 },
            },
          },
        ]
      : [];
  const pareto = (
    <div className="panel-stack">
      <div className="ro-strip spread">
        <div className="row">
          <Button
            primary={!variablePlot}
            onClick={() =>
              setState((current) => ({ ...current, plotMode: "pareto" }))
            }
          >
            목표 공간
          </Button>
          <Button
            primary={variablePlot}
            onClick={() =>
              setState((current) => ({ ...current, plotMode: "variable" }))
            }
          >
            변수–반응
          </Button>
        </div>
        <Badge tone="info">선택 {selected.id}</Badge>
      </div>
      <div className="ro-chart-fill">
        <Chart
          data={[
            scatterTrace("evaluated"),
            scatterTrace("predicted"),
            ...baselineScatter,
            ...selectedScatter,
          ]}
          layout={{
            xaxis: {
              title: {
                text: variablePlot
                  ? activeVariable.label + " [" + activeVariable.unit + "]"
                  : "질량 [kg] · 최소화",
              },
            },
            yaxis: { title: { text: "최대 변위 [mm]" } },
            showlegend: true,
            legend: { orientation: "h", x: 0, y: 1.12 },
            margin: { t: 40, l: 65, r: 20, b: 50 },
            hovermode: "closest",
          }}
          onSelect={(id: string) => select(String(id))}
        />
      </div>
      <div className="ro-strip muted">
        점을 클릭하면 후보표·상세·곡선이 같은 ID로 선택됩니다. 값이 없는
        실패/오류 후보는 그리지 않습니다.
      </div>
    </div>
  );
  const responseTraces: object[] = [];
  if (baseline && baseline.response !== null)
    responseTraces.push({
      ...curve(baseline),
      type: "scatter",
      mode: "lines",
      name: `기준 ${baseline.id}`,
      customdata: Array(61).fill(baseline.id),
      line: {
        color: "#8895a5",
        width: 2,
        dash: baseline.state === "predicted" ? "dash" : "solid",
      },
    });
  if (selected.response !== null)
    responseTraces.push({
      ...curve(selected),
      type: "scatter",
      mode: "lines",
      name: `선택 ${selected.id}${selected.state === "predicted" ? " · 예측" : ""}`,
      customdata: Array(61).fill(selected.id),
      line: {
        color: selected.state === "predicted" ? "#cb8b2b" : "#1262b8",
        width: 3,
        dash: selected.state === "predicted" ? "dash" : "solid",
      },
    });
  const responsePanel = (
    <div className="panel-stack">
      <div className="ro-strip spread">
        <span>
          변위–시간 응답 <span className="muted">/ 합성 곡선</span>
        </span>
        <Button
          icon={Pin}
          disabled={selected.state !== "evaluated"}
          onClick={() =>
            setState((current) => ({
              ...current,
              baselineId: current.selectedId,
            }))
          }
        >
          선택을 기준으로 고정
        </Button>
      </div>
      {selected.response === null ? (
        <div className="ro-empty">
          <strong>{selected.id} · 응답 없음</strong>
          <p>{selected.reason}</p>
          <span className="muted">
            측정값이나 곡선을 만들어 채우지 않습니다.
          </span>
        </div>
      ) : (
        <div className="ro-chart-fill">
          <Chart
            data={responseTraces}
            layout={{
              xaxis: { title: { text: "시간 [s]" } },
              yaxis: { title: { text: "변위 [mm]" } },
              showlegend: true,
              legend: { orientation: "h", y: 1.13 },
              margin: { t: 42, l: 65, r: 20, b: 50 },
            }}
            onSelect={(id: string) => select(String(id))}
          />
        </div>
      )}
      <div className="ro-strip">
        기준 <strong>{baseline?.id || "—"}</strong> ↔ 선택{" "}
        <strong>{selected.id}</strong>
        {selected.state === "predicted" && (
          <span className="ro-prediction">
            {" "}
            · 선택 곡선은 예측이며 평가 응답이 아닙니다.
          </span>
        )}
      </div>
    </div>
  );
  const process = (
    <div className="panel-stack">
      <div className="panel-scroll">
        <h3 className="section-title">평가 절차</h3>
        <ol className="ro-evaluation-steps">
          <li>
            <span>1</span>
            <div>
              <strong>변수 범위 설정</strong>
              <small>적용된 범위 v{state.rangeVersion}</small>
            </div>
          </li>
          <li>
            <span>2</span>
            <div>
              <strong>표본 생성</strong>
              <small>24개 / 묶음 · 결정적 합성 표본</small>
            </div>
          </li>
          <li>
            <span>3</span>
            <div>
              <strong>후보 평가</strong>
              <small>합성 평가·예측·실패 구분</small>
            </div>
          </li>
          <li>
            <span>4</span>
            <div>
              <strong>반응 비교</strong>
              <small>후보 ID로 표·점·곡선 연결</small>
            </div>
          </li>
        </ol>
        <h3 className="section-title">
          변수 범위 <span className="muted">/ 셀 편집</span>
        </h3>
        <div className="ro-range-grid">
          <DataGrid
            rows={state.draftRanges.map((r) => ({ ...r }))}
            selectedId={state.variableId}
            onSelect={(row: Variable) =>
              setState((current) => ({
                ...current,
                variableId: row.id,
                plotMode: "variable",
              }))
            }
            onEdit={editRange}
            columns={[
              { field: "label", headerName: "변수", minWidth: 84, flex: 1 },
              {
                field: "min",
                headerName: "하한",
                width: 68,
                minWidth: 60,
                editable: true,
                cellDataType: "number",
              },
              {
                field: "max",
                headerName: "상한",
                width: 68,
                minWidth: 60,
                editable: true,
                cellDataType: "number",
              },
              { field: "unit", headerName: "단위", width: 65, minWidth: 60 },
            ]}
          />
        </div>
        <p className="muted">
          {rangesDirty
            ? "미적용 편집이 있습니다. 새 표본은 적용된 범위를 사용합니다."
            : "범위가 적용되었습니다. 기존 후보의 변수값과 평가값은 보존됩니다."}
        </p>
        <h3 className="section-title">선택 변수 탐색</h3>
        <select
          aria-label="비교 변수"
          className="ro-full"
          value={state.variableId}
          onChange={(e) =>
            setState((current) => ({
              ...current,
              variableId: e.target.value,
              plotMode: "variable",
            }))
          }
        >
          {state.ranges.map((r) => (
            <option key={r.id} value={r.id}>
              {r.label} [{r.unit}]
            </option>
          ))}
        </select>
        <p>
          {activeVariable.label}: 기준{" "}
          <strong>
            {baseline
              ? baseline[
                  activeVariable.id as "thickness" | "modulus" | "density"
                ]
              : "—"}
          </strong>{" "}
          → 선택{" "}
          <strong>
            {selected[activeVariable.id as "thickness" | "modulus" | "density"]}
          </strong>{" "}
          {activeVariable.unit}
        </p>
        <Notice>
          이 화면의 값과 곡선은 설계 검토용 합성 데이터입니다. 수치
          라이브러리·실제 솔버·LLM에 연결하지 않습니다.
        </Notice>
      </div>
      <div className="ro-footer ro-range-footer">
        <div className="spread">
          <span className="muted">변수 범위 · 적용 v{state.rangeVersion}</span>
          <Badge tone={rangesDirty ? "warn" : "neutral"}>
            {rangesDirty ? "미적용 편집" : "적용됨"}
          </Badge>
        </div>
        {state.error && (
          <div role="alert" className="ro-range-error">
            {state.error}
          </div>
        )}
        <div className="ro-range-actions">
          <Button primary disabled={!rangesDirty} onClick={applyRanges}>
            범위 적용
          </Button>
          <Button
            disabled={!rangesDirty}
            onClick={() =>
              setState((current) => ({
                ...current,
                draftRanges: current.ranges.map((r) => ({ ...r })),
                error: "",
              }))
            }
          >
            편집 취소
          </Button>
        </div>
        <Button icon={Play} primary onClick={generate}>
          적용 범위로 합성 표본 추가
        </Button>
      </div>
    </div>
  );
  const candidates = (
    <div className="panel-stack">
      <div className="ro-strip spread">
        <span>
          {state.candidates.length}개 후보 · 선택 <strong>{selected.id}</strong>
        </span>
        <span className="muted">평가값 없는 행: — / 예측: 별도 표시</span>
      </div>
      <div className="ro-grid-fill">
        <DataGrid
          rows={state.candidates.map((c) => ({
            ...c,
            stateText: candidateLabel[c.state],
            massText: numberText(c.mass, 2),
            responseText: numberText(c.response),
            rangeText: `v${c.rangeVersion}`,
          }))}
          selectedId={state.selectedId}
          onSelect={(row: Candidate) => select(row.id)}
          columns={[
            { field: "id", headerName: "후보 ID", width: 95, pinned: "left" },
            {
              field: "stateText",
              headerName: "평가 상태",
              width: 115,
              cellClassRules: {
                "ro-cell-predicted": (params) =>
                  params.data.state === "predicted",
                "ro-cell-error": (params) =>
                  ["failed", "invalid"].includes(params.data.state),
              },
            },
            { field: "thickness", headerName: "두께 [mm]", width: 115 },
            { field: "modulus", headerName: "E [GPa]", width: 115 },
            { field: "density", headerName: "밀도 [kg/m³]", width: 135 },
            { field: "massText", headerName: "질량 [kg]", width: 115 },
            { field: "responseText", headerName: "최대 변위 [mm]", width: 145 },
            { field: "iteration", headerName: "묶음", width: 85 },
            { field: "rangeText", headerName: "범위 버전", width: 110 },
            { field: "reason", headerName: "사유", minWidth: 200, flex: 1 },
          ]}
        />
      </div>
    </div>
  );
  const detail = (
    <div className="panel-scroll">
      <div className="spread ro-heading">
        <strong className="mono">{selected.id}</strong>
        <Badge tone={candidateTone[selected.state]}>
          {candidateLabel[selected.state]}
        </Badge>
      </div>
      <Properties
        rows={[
          ["평가 묶음", selected.iteration],
          ["생성 범위", `v${selected.rangeVersion}`],
          ["두께", `${selected.thickness} mm`],
          ["탄성 계수", `${selected.modulus} GPa`],
          ["밀도", `${selected.density} kg/m³`],
          [
            "질량",
            selected.mass === null ? "알 수 없음" : `${selected.mass} kg`,
          ],
          [
            "최대 변위",
            selected.response === null
              ? "알 수 없음"
              : `${selected.response} mm`,
          ],
        ]}
      />
      {selected.reason && <Notice tone="bad">{selected.reason}</Notice>}
      {selected.state === "predicted" && (
        <Notice tone="warn">
          예측값입니다. 실측 또는 실제 평가 결과로 사용하지 않습니다.
        </Notice>
      )}
      <h3 className="section-title">
        <GitCompareArrows size={14} /> 기준 후보 {state.baselineId}와 비교
      </h3>
      <Properties
        rows={[
          [
            "질량 차이",
            selected.mass !== null && baseline?.mass != null
              ? `${(selected.mass - baseline.mass).toFixed(2)} kg`
              : "비교할 평가값 없음",
          ],
          [
            "최대 변위 차이",
            selected.response !== null && baseline?.response != null
              ? `${(selected.response - baseline.response).toFixed(3)} mm`
              : "비교할 평가값 없음",
          ],
        ]}
      />
      <Button
        icon={Pin}
        disabled={selected.state !== "evaluated"}
        onClick={() =>
          setState((current) => ({
            ...current,
            baselineId: current.selectedId,
          }))
        }
      >
        선택 후보를 기준으로 고정
      </Button>
      <p className="muted">
        고정된 기준은 다른 후보를 선택해도 유지됩니다. 모든 값은 합성
        예시입니다.
      </p>
    </div>
  );
  return (
    <>
      <Toolbar>
        <Button icon={Play} primary onClick={generate}>
          합성 표본 추가
        </Button>
        <span className="ro-toolbar-context">
          Optimization{" "}
          <span className="muted">/ 경량화–응답 비교 · 로컬 저장</span>
        </span>
        <Badge tone="neutral">범위 v{state.rangeVersion}</Badge>
        <Badge tone="info">선택 {selected.id}</Badge>
        {rangesDirty && <Badge tone="warn">미적용 범위 편집</Badge>}
      </Toolbar>
      <Workspace
        id="optimization"
        panels={{
          process: { title: "평가 절차 · 변수", content: process },
          pareto: { title: "Pareto · 질량 / 최대 변위", content: pareto },
          response: { title: "반응 곡선 · 기준 비교", content: responsePanel },
          candidates: { title: "후보표", content: candidates },
          detail: { title: "선택 후보 · 상세", content: detail },
        }}
        setup={(api) => {
          api.addPanel({
            id: "process",
            component: "content",
            title: "평가 절차 · 변수",
            initialWidth: 350,
          });
          api.addPanel({
            id: "candidates",
            component: "content",
            title: "후보표",
            position: { referencePanel: "process", direction: "right" },
          });
          api.addPanel({
            id: "pareto",
            component: "content",
            title: "Pareto · 질량 / 최대 변위",
            position: { referencePanel: "candidates", direction: "above" },
            initialHeight: 390,
          });
          api.addPanel({
            id: "response",
            component: "content",
            title: "반응 곡선 · 기준 비교",
            position: { referencePanel: "pareto", direction: "right" },
          });
          api.addPanel({
            id: "detail",
            component: "content",
            title: "선택 후보 · 상세",
            position: { referencePanel: "candidates", direction: "right" },
            initialWidth: 310,
          });
          api.getPanel("process")?.api.setSize({ width: 330 });
          api.getPanel("detail")?.api.setSize({ width: 285 });
          api.getPanel("pareto")?.api.setSize({ height: 370 });
        }}
      />
    </>
  );
}
