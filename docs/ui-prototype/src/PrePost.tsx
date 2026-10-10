import React, { useState } from "react";
import {
  Save,
  FolderOpen,
  Box,
  FileSpreadsheet,
  Layers,
  Beaker,
  Sigma,
  MousePointer2,
  Settings2,
  Check,
  RotateCcw,
  Scissors,
  Crosshair,
  Waypoints,
  Columns2,
  AlertTriangle,
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
  useStorageHealth,
  persistStored,
  Notice,
} from "./common";
import { Viewport } from "./Viewport";
import "./PrePost.css";

const parts: Record<string, string> = {
  body: "Base plate",
  support: "Support block",
  arm: "Clamp arm",
  pin: "Pivot pin",
};
const initialPre = {
  revision: 7,
  width: 40,
  dimensions: { body: 68, support: 12, arm: 40, pin: 5 } as Record<
    string,
    number
  >,
  young: 210000,
  poisson: 0.3,
  pdeK: 1,
  pdeSource: 0,
  mesh: 2,
};
export function Pre() {
  const [doc, setDoc] = useStored("pre-document", initialPre);
  const [saved, setSaved] = useStored("pre-saved", initialPre);
  const [history, setHistory] = useStored("pre-history", [initialPre]);
  const [mode, setMode] = useStored("pre-mode", "cad");
  const [host, setHost] = useStored("pre-host", "FreeCAD");
  const [selected, setSelected] = useStored("pre-selected", "arm");
  const [condition, setCondition] = useStored("pre-condition", "fixed");
  const storageHealthy = useStorageHealth();
  const [command, setCommand] = useStored<{
    target: string;
    width: string;
  } | null>("pre-command", null);
  const [saveFail, setSaveFail] = useState(false);
  const [message, setMessage] = useState(
    `준비 문서 r${doc.revision} · 합성 조립 모델`,
  );
  const [dataRow, setDataRow] = useStored("pre-row", "row-8");
  const [meshFixed, setMeshFixed] = useStored("pre-mesh-fixed", false);
  const [sampleScale, setSampleScale] = useStored("pre-data-scale", "1");
  const [strainRegion, setStrainRegion] = useStored(
    "pre-strain-region",
    "0.02–0.08",
  );
  const dirty =
    JSON.stringify(doc) !== JSON.stringify(saved) || command !== null;
  function save() {
    if (saveFail) {
      setMessage(
        "저장 실패 · 쓰기 경로에 접근할 수 없습니다. 입력과 편집 초안을 유지했습니다.",
      );
      setSaveFail(false);
      return;
    }
    if (command) {
      setMessage("편집 중인 치수를 적용하거나 취소한 다음 문서를 저장하세요.");
      return;
    }
    if (!persistStored("pre-document", doc)) {
      setMessage(
        "브라우저 저장 실패 · 현재 편집값과 revision을 유지했습니다. 하단에서 저장을 재시도하세요.",
      );
      return;
    }
    const next = { ...doc, revision: doc.revision + 1 };
    setDoc(next);
    setSaved(next);
    setHistory([...history, next]);
    setMessage(`준비 문서 r${next.revision} 저장 완료 · 이전 revision 보존`);
  }
  const scale = Number(sampleScale);
  const scaleValid =
    sampleScale.trim() !== "" && Number.isFinite(scale) && scale > 0;
  const bounds =
    strainRegion === "0.02–0.08"
      ? [0.02, 0.08]
      : strainRegion === "0.00–0.05"
        ? [0, 0.05]
        : [0, Infinity];
  const points = Array.from({ length: 36 }, (_, i) => ({
    id: `row-${i + 1}`,
    index: i + 1,
    strain: +(i * 0.003).toFixed(3),
    rawStress: +(235 * (1 - Math.exp(-i / 8)) + i * 1.8).toFixed(2),
    stress: scaleValid
      ? +(
          Number((235 * (1 - Math.exp(-i / 8)) + i * 1.8).toFixed(2)) * scale
        ).toFixed(2)
      : null,
    channel: "Axial stress",
    mask:
      i === 31
        ? "원본 제외"
        : i * 0.003 < bounds[0] || i * 0.003 > bounds[1]
          ? "구간 밖"
          : "사용",
  }));
  const selectedPoint = points.find((p) => p.id === dataRow) ?? points[0];
  const contextTitle =
    mode === "data"
      ? `tensile-A.csv · ${selectedPoint.index}행`
      : mode === "material"
        ? "재료점 · 단축 인장"
        : mode === "pde"
          ? "Poisson 문제"
          : mode === "conditions"
            ? condition === "fixed"
              ? "고정 · Face set 12"
              : "하중 · Face set 18"
            : parts[selected];
  const contextRows: Array<[string, React.ReactNode]> =
    mode === "data"
      ? [
          ["자료 ID", "tensile-A.csv"],
          ["원본 행", selectedPoint.index],
          ["Strain", selectedPoint.strain],
          ["원본 Stress", `${selectedPoint.rawStress} MPa`],
          [
            "변환 Stress",
            scaleValid ? `${selectedPoint.stress} MPa` : "배율 오류",
          ],
          ["채널 배율", sampleScale],
          ["사용 상태", selectedPoint.mask],
          ["사용 구간", strainRegion],
        ]
      : mode === "material"
        ? [
            ["모델", "등방 선형 탄성"],
            ["E", `${doc.young} MPa`],
            ["ν", doc.poisson],
            ["경로", "0 → 0.01 → 0"],
            ["CAD", "불필요"],
          ]
        : mode === "pde"
          ? [
              ["방정식", "−∇ · (κ ∇u) = f"],
              ["κ", doc.pdeK],
              ["f", doc.pdeSource],
              ["영역", "단위 정사각형"],
              ["경계", "u = 0"],
            ]
          : mode === "conditions"
            ? [
                ["조건 ID", condition === "fixed" ? "BC-FIX-12" : "BC-LOAD-18"],
                [
                  "고정 참조",
                  condition === "fixed"
                    ? "Support block / Face set 12"
                    : "Clamp arm / Face set 18",
                ],
                [
                  "조건",
                  condition === "fixed" ? "UX = UY = UZ = 0" : "FZ = −150 N",
                ],
                ["별도 보기 선택", parts[selected]],
              ]
            : [];
  const qrows = [
    {
      id: "e1821",
      element: 1821,
      region: "Clamp arm",
      metric: "Jacobian",
      value: meshFixed ? 0.42 : 0.08,
      status: meshFixed ? "수정 시안" : "검사 필요",
    },
    {
      id: "e2308",
      element: 2308,
      region: "Support block",
      metric: "Aspect ratio",
      value: meshFixed ? 3.2 : 12.4,
      status: meshFixed ? "수정 시안" : "검사 필요",
    },
    {
      id: "e5012",
      element: 5012,
      region: "Base plate",
      metric: "Skewness",
      value: 0.21,
      status: "검사 통과",
    },
  ];
  const tree = (
    <div className="panel-stack">
      <div className="tree">
        <div className="tree-label">준비 문서 / PRE-041</div>
        <button
          className="tree-item"
          disabled={host === "경량"}
          onClick={() => setMode("cad")}
        >
          <Box size={14} /> Fixture assembly <small>r{doc.revision}</small>
        </button>
        {Object.entries(parts).map(([id, name]) => (
          <button
            key={id}
            className={`tree-item child ${selected === id ? "selected" : ""}`}
            onClick={() => setSelected(id)}
          >
            <Box size={13} />
            {name}
            <small>{id === selected ? "선택" : ""}</small>
          </button>
        ))}
        <div className="tree-label">해석 준비</div>
        <button className="tree-item" onClick={() => setMode("mesh")}>
          <Layers size={14} /> Mesh <Badge>r{doc.mesh}</Badge>
        </button>
        <button
          className="tree-item"
          onClick={() => {
            setSelected("support");
            setCondition("fixed");
            setMode("conditions");
          }}
        >
          <MousePointer2 size={14} /> 고정 · Face set 12
        </button>
        <button
          className="tree-item"
          onClick={() => {
            setSelected("arm");
            setCondition("load");
            setMode("conditions");
          }}
        >
          <MousePointer2 size={14} /> 하중 · Face set 18
        </button>
        <div className="tree-label">CAD 없는 입력</div>
        <button
          className={`tree-item ${mode === "data" ? "selected" : ""}`}
          onClick={() => setMode("data")}
        >
          <FileSpreadsheet size={14} /> 인장 시험 자료
        </button>
        <button
          className={`tree-item ${mode === "material" ? "selected" : ""}`}
          onClick={() => setMode("material")}
        >
          <Beaker size={14} /> 재료점 정의
        </button>
        <button
          className={`tree-item ${mode === "pde" ? "selected" : ""}`}
          onClick={() => setMode("pde")}
        >
          <Sigma size={14} /> Poisson 문제
        </button>
      </div>
      <div className="status-line">
        host {host} · 작업 모드 {mode}
      </div>
    </div>
  );
  const inspector = (
    <div className="panel-stack">
      <div className="selection-summary">
        <span className="muted">현재 보기 선택</span>
        <p>
          <strong>{contextTitle}</strong>
        </p>
        <p>
          {mode === "cad" || mode === "mesh" ? `Object ID ${selected} · ` : ""}
          저장 r{saved.revision}
        </p>
      </div>
      {command && (
        <div className="pinned-command">
          <strong>치수 편집 · {parts[command.target]}</strong>
          <span>편집 대상 고정 · 보기 선택과 독립</span>
        </div>
      )}
      <div className="panel-scroll">
        {command ? (
          <>
            <Field label="너비 [mm]">
              <input
                aria-label="편집 너비"
                type="number"
                value={command.width}
                onChange={(e) =>
                  setCommand({ ...command, width: e.target.value })
                }
              />
            </Field>
            <Properties
              rows={[
                ["명령 대상", parts[command.target]],
                ["원래 값", `${doc.dimensions[command.target]} mm`],
                ["저장 revision", `r${saved.revision}`],
              ]}
            />
            {!(Number(command.width) > 0) && (
              <Notice tone="bad">
                너비는 0보다 커야 합니다. 적용·내보내기가 차단됩니다.
              </Notice>
            )}
          </>
        ) : contextRows.length ? (
          <Properties rows={contextRows} />
        ) : (
          <>
            <Properties
              rows={[
                ["유형", selected === "pin" ? "원통 피처" : "PartDesign Body"],
                ["문서", "PRE-041"],
                [
                  "보존 revision",
                  history.map((x) => "r" + x.revision).join(" · "),
                ],
                ["너비", `${doc.dimensions[selected]} mm`],
                ["재료", "강재 · 예시"],
                ["형상 상태", "합성 모델"],
                ["제작·사용 승인", <Badge tone="warn">UNKNOWN</Badge>],
              ]}
            />
            <Button
              icon={Settings2}
              onClick={() =>
                setCommand({
                  target: selected,
                  width: String(doc.dimensions[selected]),
                })
              }
            >
              선택 부품 치수 편집
            </Button>
            <p className="muted">
              제품에서는 FreeCAD native Tasks와 transaction을 사용합니다. 이
              시안은 대상 고정·입력 보존을 검토합니다.
            </p>
          </>
        )}
      </div>
      {command && (
        <div className="editor-actions">
          <Button
            primary
            icon={Check}
            disabled={!(Number(command.width) > 0)}
            onClick={() => {
              setDoc({
                ...doc,
                dimensions: {
                  ...doc.dimensions,
                  [command.target]: Number(command.width),
                },
              });
              setMessage(
                `${parts[command.target]} 너비 ${command.width} mm 적용 · 미저장`,
              );
              setCommand(null);
            }}
          >
            치수 적용
          </Button>
          <Button onClick={() => setCommand(null)}>취소</Button>
        </div>
      )}
    </div>
  );
  let center: React.ReactNode;
  if (mode === "data")
    center = (
      <div className="panel-stack">
        <div className="source-caption">
          <FileSpreadsheet size={14} />
          <strong>tensile-A.csv</strong>
          <Badge>합성 36행</Badge>
          <span className="spacer" />
          <span>선택 {dataRow.replace("row-", "")}행</span>
        </div>
        <div className="pre-data-pane">
          <Chart
            data={[
              {
                x: points.map((p) => p.strain),
                y: points.map((p) => (p.mask === "사용" ? p.stress : null)),
                customdata: points.map((p) => p.id),
                type: "scatter",
                mode: "lines+markers",
                line: { color: "#377caa", width: 2 },
                marker: {
                  size: points.map((p) => (p.id === dataRow ? 10 : 4)),
                  color: points.map((p) =>
                    p.id === dataRow ? "#b45e3b" : "#377caa",
                  ),
                },
              },
            ]}
            layout={{
              xaxis: { title: { text: "Axial strain [−]" } },
              yaxis: { title: { text: "변환 Axial stress [MPa]" } },
            }}
            onSelect={(id) => setDataRow(id)}
          />
          <DataGrid
            rows={points}
            columns={[
              { field: "index", headerName: "원본 행", width: 82, flex: 0 },
              { field: "strain", headerName: "Strain [−]" },
              { field: "rawStress", headerName: "원본 [MPa]" },
              { field: "stress", headerName: "변환 [MPa]" },
              { field: "mask", headerName: "사용" },
            ]}
            selectedId={dataRow}
            onSelect={(r) => setDataRow(r.id)}
          />
        </div>
        {!scaleValid && (
          <Notice tone="bad">
            채널 배율은 0보다 큰 유한한 수여야 합니다. 변환 곡선을 표시하지
            않습니다.
          </Notice>
        )}
        <div className="editor-actions">
          <Field label="채널 배율">
            <input
              aria-label="자료 채널 배율"
              type="number"
              value={sampleScale}
              onChange={(e) => setSampleScale(e.target.value)}
            />
          </Field>
          <Field label="사용 구간 [strain]">
            <select
              value={strainRegion}
              onChange={(e) => setStrainRegion(e.target.value)}
            >
              <option>0.02–0.08</option>
              <option>0.00–0.05</option>
              <option>전체 구간</option>
            </select>
          </Field>
        </div>
      </div>
    );
  else if (mode === "material")
    center = (
      <div className="pre-material-main">
        <div>
          <h2>재료점 · 단축 인장</h2>
          <p className="muted">
            형상 없이 재료 구성식과 시험 경로를 정의합니다.
          </p>
        </div>
        <Field label="재료 모델">
          <select>
            <option>Isotropic linear elastic</option>
          </select>
        </Field>
        <div className="form-grid">
          <Field label="Young's modulus [MPa]">
            <input
              aria-label="Young modulus"
              type="number"
              value={doc.young}
              onChange={(e) =>
                setDoc({ ...doc, young: Number(e.target.value) })
              }
            />
          </Field>
          <Field label="Poisson ratio [−]">
            <input
              aria-label="Poisson ratio"
              type="number"
              step="0.01"
              value={doc.poisson}
              onChange={(e) =>
                setDoc({ ...doc, poisson: Number(e.target.value) })
              }
            />
          </Field>
        </div>
        <Field label="시험 경로">
          <select>
            <option>Strain controlled · 0 → 0.01 → 0</option>
          </select>
        </Field>
        <Properties
          rows={[
            ["단위계", "mm · N · MPa"],
            ["초기 응력", "0 MPa"],
            ["샘플", "단일 재료점"],
            ["연결 시험 자료", "tensile-A.csv"],
          ]}
        />
        {!(doc.young > 0 && doc.poisson > -1 && doc.poisson < 0.5) && (
          <Notice tone="bad">
            E &gt; 0, −1 &lt; ν &lt; 0.5가 필요합니다. Case 생성이 차단됩니다.
          </Notice>
        )}
        <Notice>
          실제 재료점 계산은 Runner에 제출할 고정 Case를 생성한 뒤 수행합니다.
          이 시안은 정의만 편집합니다.
        </Notice>
      </div>
    );
  else if (mode === "pde")
    center = (
      <div className="pre-material-main">
        <div>
          <h2>Poisson 문제</h2>
          <p className="muted">스칼라 장 · 단위 정사각형 영역 · CAD 불필요</p>
        </div>
        <div className="pde-equation">−∇ · (κ ∇u) = f</div>
        <div className="form-grid">
          <Field label="확산 계수 κ">
            <input
              aria-label="PDE 확산 계수"
              type="number"
              value={doc.pdeK}
              onChange={(e) => setDoc({ ...doc, pdeK: Number(e.target.value) })}
            />
          </Field>
          <Field label="소스 항 f">
            <input
              aria-label="PDE 소스 항"
              type="number"
              value={doc.pdeSource}
              onChange={(e) =>
                setDoc({ ...doc, pdeSource: Number(e.target.value) })
              }
            />
          </Field>
        </div>
        <Properties
          rows={[
            ["영역", "[0, 1] × [0, 1]"],
            ["경계 조건", "Dirichlet · u = 0"],
            ["함수 공간", "CG · degree 1"],
            ["메시", "32 × 32 · 예시 정의"],
          ]}
        />
        {doc.pdeK <= 0 && (
          <Notice tone="bad">κ는 0보다 커야 합니다. 정의를 수정하세요.</Notice>
        )}
        <Notice>
          재료점과 별개의 PDE 입력입니다. 저장한 계수·경계·영역으로 새 Case를
          구성합니다.
        </Notice>
      </div>
    );
  else
    center = (
      <div className="panel-stack">
        {host === "경량" && (
          <Notice tone="warn">
            경량 host에는 CAD 편집기가 없습니다. 문서의 CAD payload를 보존하며
            FreeCAD host에서 재개할 수 있습니다.
          </Notice>
        )}
        <Viewport
          selected={selected}
          sizes={doc.dimensions}
          onSelect={setSelected}
        />
        {mode === "conditions" && (
          <div className="source-caption">
            <MousePointer2 size={14} />
            조건 참조{" "}
            {condition === "fixed"
              ? "Support block · 고정 Face set 12"
              : "Clamp arm · 하중 Face set 18"}
            <span>보기 선택: {parts[selected]}</span>
            <Badge tone="good">원본 region 참조 유지</Badge>
          </div>
        )}
      </div>
    );
  const quality = (
    <div className="pre-quality">
      <div className="panel-titlebar">
        <Badge tone={meshFixed ? "info" : "warn"}>
          {meshFixed ? "메시 수정 시안" : "2개 항목 재검토"}
        </Badge>
        <span className="spacer" />
        <Button
          icon={Layers}
          onClick={() => {
            setMeshFixed(true);
            setDoc({ ...doc, mesh: doc.mesh + 1 });
            setMessage(
              "새 메시 revision 생성 시안 · 이전 메시와 조건 참조 보존",
            );
          }}
        >
          국부 메시 수정 시안
        </Button>
      </div>
      <DataGrid
        rows={qrows}
        columns={[
          { field: "element", headerName: "요소 ID", width: 90, flex: 0 },
          { field: "region", headerName: "영역" },
          { field: "metric", headerName: "품질 지표" },
          { field: "value", headerName: "값" },
          { field: "status", headerName: "상태" },
        ]}
        onSelect={(r) => {
          setSelected(
            r.region === "Clamp arm"
              ? "arm"
              : r.region === "Support block"
                ? "support"
                : "body",
          );
          setMode("mesh");
        }}
      />
      <div className="status-line">
        값은 UI 검토용 합성 데이터 · 실제 메시 품질 검증 아님
      </div>
    </div>
  );
  return (
    <div className="app-screen">
      <Toolbar>
        <Button icon={Save} onClick={save}>
          문서 저장
        </Button>
        <Button icon={FolderOpen} onClick={() => location.reload()}>
          문서 재열기
        </Button>
        <div className="toolbar-separator" />
        <span className="native-host">{host} 배치 시안</span>
        <div className="pre-modebar">
          {[
            ["cad", "CAD", Box],
            ["mesh", "메시", Layers],
            ["data", "자료", FileSpreadsheet],
            ["material", "재료점", Beaker],
            ["pde", "PDE", Sigma],
          ].map(([m, label, Icon]) => (
            <Button
              key={String(m)}
              icon={Icon as typeof Box}
              className={mode === m ? "active" : ""}
              disabled={m === "cad" && host === "경량"}
              onClick={() => setMode(String(m))}
            >
              {String(label)}
            </Button>
          ))}
        </div>
        <span className="spacer" />
        <select
          aria-label="Pre host 선택"
          value={host}
          onChange={(e) => {
            setHost(e.target.value);
            if (e.target.value === "경량") setMode("data");
          }}
        >
          <option>FreeCAD</option>
          <option>경량</option>
        </select>
      </Toolbar>
      <div className="pre-save-strip">
        <Badge tone={!storageHealthy || dirty ? "warn" : "good"}>
          {!storageHealthy
            ? "브라우저 미저장"
            : dirty
              ? "미저장 변경"
              : "저장됨"}
        </Badge>
        <span>{message}</span>
        <span className="spacer" />
        <label>
          <input
            type="checkbox"
            checked={saveFail}
            onChange={(e) => setSaveFail(e.target.checked)}
          />{" "}
          다음 저장 실패 시험
        </label>
      </div>
      <Workspace
        id="pre-v1"
        panels={{
          tree: { title: "문서 · 모델", content: tree },
          view: {
            title:
              mode === "data"
                ? "시험 자료"
                : mode === "material"
                  ? "재료점"
                  : mode === "pde"
                    ? "PDE 정의"
                    : "모델 작업 공간",
            content: center,
          },
          properties: { title: "선택 · 편집", content: inspector },
          quality: { title: "메시 품질 · 조건 참조", content: quality },
        }}
        setup={(api) => {
          api.addPanel({
            id: "view",
            component: "content",
            title: "작업 공간",
          });
          api.addPanel({
            id: "tree",
            component: "content",
            title: "문서 · 모델",
            position: { referencePanel: "view", direction: "left" },
            initialWidth: 230,
          });
          api.addPanel({
            id: "properties",
            component: "content",
            title: "선택 · 편집",
            position: { referencePanel: "view", direction: "right" },
            initialWidth: 285,
          });
          api.addPanel({
            id: "quality",
            component: "content",
            title: "메시 품질 · 조건 참조",
            position: { referencePanel: "view", direction: "below" },
            initialHeight: 210,
          });
        }}
      />
    </div>
  );
}

type Operation = "native" | "probe" | "slice" | "line" | "compare";
const operationNames: Record<Operation, string> = {
  native: "원위치 조회",
  probe: "보간 탐침",
  slice: "단면",
  line: "선 경로",
  compare: "A/B 비교",
};
type Analysis = {
  id: string;
  name: string;
  source: string;
  operation: Operation;
  fields: Record<string, string>;
};
export function Post() {
  const [selected, setSelected] = useStored("post-selected", "A");
  const [missingB, setMissingB] = useStored("post-missing-b", false);
  const [layout, setLayout] = useStored("post-comparison", true);
  const [analyses, setAnalyses] = useStored<Analysis[]>("post-analyses", [
    {
      id: "ana-1",
      name: "Slice · X = 12",
      source: "A",
      operation: "slice",
      fields: { origin: "12, 0, 0", normal: "1, 0, 0" },
    },
    {
      id: "ana-2",
      name: "Node · 331",
      source: "B",
      operation: "native",
      fields: { nativeId: "331", association: "Point" },
    },
  ]);
  const [command, setCommand] = useStored<{
    operation: Operation;
    source: string;
    fields: Record<string, string>;
  } | null>("post-command", null);
  const [message, setMessage] = useState(
    "PostDocument r3 · 원본 A/B 및 분석 정의",
  );
  const [revision, setRevision] = useStored("post-revision", 3);
  const [saveFail, setSaveFail] = useState(false);
  const [cameraLinked, setCameraLinked] = useStored("post-camera", true);
  const [timeLinked, setTimeLinked] = useStored("post-time", true);
  const [rangeLinked, setRangeLinked] = useStored("post-range", true);
  const [timeA, setTimeA] = useStored("post-time-a", 1);
  const [timeB, setTimeB] = useStored("post-time-b", 0.5);
  const effectiveTimeB = timeLinked ? timeA : timeB;
  const displayTime = (s: string) => (s === "B" ? effectiveTimeB : timeA);
  const selectedAnalysis = analyses.find((a) => a.id === selected);
  const source = selectedAnalysis?.source ?? selected;
  const unavailable = source === "B" && missingB;
  function start(operation: Operation) {
    const defaults: Record<Operation, Record<string, string>> = {
      native: { nativeId: "331", association: "Point" },
      probe: { point: "12, 4, 2", frame: "Global", interpolation: "Linear" },
      slice: { origin: "12, 0, 0", normal: "1, 0, 0" },
      line: { start: "0, 0, 0", end: "40, 0, 0", samples: "51" },
      compare: {
        sourceA: "A",
        sourceB: "B",
        mapping: "동일 native ID",
        time: "동일 저장 step",
        denominator: "A",
        mask: "분모 0은 제외",
      },
    };
    setCommand({ operation, source, fields: defaults[operation] });
  }
  const sources = (
    <div className="panel-stack">
      <div className="tree">
        <div className="tree-label">RESULT SOURCES</div>
        {["A", "B"].map((s) => (
          <React.Fragment key={s}>
            <button
              className={`tree-item ${selected === s ? "selected" : ""}`}
              onClick={() => setSelected(s)}
            >
              <Layers size={14} />
              {s} · {s === "A" ? "150 N" : "200 N"}
              <Badge tone={s === "B" && missingB ? "bad" : "good"}>
                {s === "B" && missingB ? "원본 누락" : "연결됨"}
              </Badge>
            </button>
            {analyses
              .filter((a) => a.source === s)
              .map((a) => (
                <button
                  key={a.id}
                  className={`tree-item child ${selected === a.id ? "selected" : ""}`}
                  onClick={() => setSelected(a.id)}
                >
                  <Scissors size={12} />
                  {a.name}
                </button>
              ))}
          </React.Fragment>
        ))}
        <div className="tree-label">문서</div>
        <div className="data-preview">
          POST-018 · r{revision}
          <br />
          분석 {analyses.length}개 · 독립 source 2개
        </div>
      </div>
      <div className="editor-actions">
        <Button
          icon={AlertTriangle}
          onClick={() => {
            setMissingB(!missingB);
            setMessage(
              !missingB
                ? "B 원본 누락 복구 시험 · A 분석은 계속 사용할 수 있습니다."
                : "B 참조를 다시 연결했습니다.",
            );
          }}
        >
          {missingB ? "B 원본 재연결" : "B 누락 시험"}
        </Button>
      </div>
    </div>
  );
  const property = (
    <div className="panel-stack">
      <div className="selection-summary">
        <span className="muted">현재 보기 선택</span>
        <p>
          <strong>{selectedAnalysis?.name ?? `Source ${source}`}</strong>
        </p>
        <p>
          {source} · {unavailable ? "원본 누락" : "structural-result.vtu"}
        </p>
      </div>
      {command && (
        <div className="pinned-command">
          <strong>
            {operationNames[command.operation]} · 대상 Source {command.source}
          </strong>
          <span>편집 중 원본 고정 · 선택 변경은 새 명령에 적용</span>
        </div>
      )}
      <div className="panel-scroll">
        {command ? (
          <>
            <div className="command-field-list">
              {Object.entries(command.fields).map(([key, value]) => (
                <Field
                  key={key}
                  label={
                    (
                      {
                        nativeId: "원본 ID",
                        association: "Association",
                        point: "탐침 좌표 [mm]",
                        frame: "좌표계",
                        interpolation: "보간 방식",
                        origin: "평면 원점 [mm]",
                        normal: "평면 법선",
                        start: "시작점 [mm]",
                        end: "끝점 [mm]",
                        samples: "표본 수",
                        sourceA: "기준 원본",
                        sourceB: "비교 원본",
                        mapping: "공간 대응",
                        time: "시간 대응",
                        denominator: "변화율 분모",
                        mask: "Mask 정책",
                      } as Record<string, string>
                    )[key] ?? key
                  }
                >
                  <input
                    aria-label={`Post ${key}`}
                    value={value}
                    onChange={(e) =>
                      setCommand({
                        ...command,
                        fields: { ...command.fields, [key]: e.target.value },
                      })
                    }
                  />
                </Field>
              ))}
            </div>
            {command.operation === "probe" && (
              <Notice>
                보간점에는 native 절점 ID를 부여하지 않습니다. 좌표·보간 방식과
                범위 밖 상태를 보존합니다.
              </Notice>
            )}
            {command.operation === "native" && (
              <Notice>
                원본 mesh와 association에서 ID를 조회합니다. 보간 값으로
                대체하지 않습니다.
              </Notice>
            )}
          </>
        ) : (
          <>
            <Properties
              rows={[
                ["Source ID", source],
                ["입력", `${source === "A" ? "150" : "200"} N · 합성 사례`],
                ["Association", "Point"],
                ["Native mesh", `mesh-${source}-r1`],
                ["좌표계", "Global · mm"],
                [
                  "Time",
                  `${displayTime(source).toFixed(2)} s · 합성 저장 step`,
                ],
                ["Field", "Displacement · UZ"],
                ["Unit", "mm"],
                [
                  "가용 상태",
                  <Badge tone={unavailable ? "bad" : "good"}>
                    {unavailable ? "MISSING" : "READY"}
                  </Badge>,
                ],
              ]}
            />
            {selectedAnalysis && (
              <Properties
                rows={Object.entries(selectedAnalysis.fields).map(([k, v]) => [
                  k,
                  v,
                ])}
              />
            )}
            <p className="muted">
              native Properties·선택·카메라는 ParaView를 재사용합니다. 이 시안의
              3D 결과는 합성 자료입니다.
            </p>
          </>
        )}
      </div>
      {command && (
        <div className="editor-actions">
          <Button
            primary
            disabled={
              (command.source === "B" || command.operation === "compare") &&
              missingB
            }
            onClick={() => {
              const id = `ana-${Date.now()}`;
              const name = `${operationNames[command.operation]} · ${command.source}`;
              setAnalyses([...analyses, { id, name, ...command }]);
              setSelected(id);
              setCommand(null);
              setMessage(`새 분석 ${name} 생성 · 기존 분석 보존`);
            }}
          >
            분석 생성
          </Button>
          <Button onClick={() => setCommand(null)}>취소</Button>
        </div>
      )}
    </div>
  );
  const view = (
    <div className="panel-stack">
      <div className="post-controls">
        <label>
          <input
            type="checkbox"
            checked={cameraLinked}
            onChange={(e) => setCameraLinked(e.target.checked)}
          />
          카메라 연결
        </label>
        <label>
          <input
            type="checkbox"
            checked={timeLinked}
            onChange={(e) => setTimeLinked(e.target.checked)}
          />
          시간 연결
        </label>
        <label>
          <input
            type="checkbox"
            checked={rangeLinked}
            onChange={(e) => setRangeLinked(e.target.checked)}
          />
          공통 색 범위
        </label>
        <span className="spacer" />
        <label>
          A 시간{" "}
          <select
            aria-label="A 시간"
            value={timeA}
            onChange={(e) => setTimeA(Number(e.target.value))}
          >
            {[0.25, 0.5, 0.75, 1].map((t) => (
              <option key={t} value={t}>
                {t.toFixed(2)} s
              </option>
            ))}
          </select>
        </label>
        <label>
          B 시간{" "}
          <select
            aria-label="B 시간"
            value={effectiveTimeB}
            disabled={timeLinked}
            onChange={(e) => setTimeB(Number(e.target.value))}
          >
            {[0.25, 0.5, 0.75, 1].map((t) => (
              <option key={t} value={t}>
                {t.toFixed(2)} s
              </option>
            ))}
          </select>
        </label>
      </div>
      <div className="comparison-view">
        {!layout && unavailable ? (
          <div className="source-missing">
            <AlertTriangle size={26} />
            <strong>Source B 원본 누락</strong>
            <p>A를 선택해 독립 분석을 계속하세요.</p>
            <Button onClick={() => setMissingB(false)}>B 참조 다시 연결</Button>
          </div>
        ) : (
          <Viewport
            field
            source={layout ? "A" : source}
            time={displayTime(layout ? "A" : source)}
            rangeMax={
              rangeLinked ? 0.059 : layout || source === "A" ? 0.043 : 0.059
            }
            cameraLinkKey={cameraLinked ? "post" : undefined}
          />
        )}
        {layout &&
          (missingB ? (
            <div className="source-missing">
              <AlertTriangle size={26} />
              <strong>Source B를 찾을 수 없습니다</strong>
              <p>
                B 기반 분석 {analyses.filter((a) => a.source === "B").length}개
                보존
                <br />
                A의 보기·조회·새 분석은 계속 사용 가능
              </p>
              <Button className="outline" onClick={() => setMissingB(false)}>
                B 참조 다시 연결
              </Button>
            </div>
          ) : (
            <Viewport
              field
              source="B"
              time={effectiveTimeB}
              rangeMax={0.059}
              cameraLinkKey={cameraLinked ? "post" : undefined}
            />
          ))}
      </div>
      <div className="status-line">
        공간 대응: 동일 native ID · 기준 A · 분모 0 mask · 원본/파생 데이터 구별
      </div>
    </div>
  );
  const original = Array.from({ length: 10 }, (_, i) => ({
    id: String(331 + i),
    node: 331 + i,
    x: 12 + i,
    y: 4,
    z: 2,
    a: -(0.029 + i * 0.001) * timeA,
    b: missingB ? null : -(0.039 + i * 0.0014) * effectiveTimeB,
    association: "Point",
  }));
  const results = (
    <div className="panel-stack">
      <div className="source-caption">
        <Crosshair size={13} />
        <strong>{source} · 원위치 표</strong>
        <Badge>{unavailable ? "사용 불가" : "합성 native ID"}</Badge>
        <span className="spacer" />
        <span>보간점과 별도</span>
      </div>
      {unavailable ? (
        <Notice tone="warn">
          B 원본을 연결하면 같은 ID·association으로 복구합니다. A를 선택해 계속
          분석할 수 있습니다.
        </Notice>
      ) : (
        <DataGrid
          rows={original}
          columns={[
            { field: "node", headerName: "Native ID", width: 95, flex: 0 },
            { field: "x", headerName: "X [mm]" },
            { field: "y", headerName: "Y [mm]" },
            { field: "z", headerName: "Z [mm]" },
            {
              field: source === "B" ? "b" : "a",
              headerName: `${source} UZ [mm]`,
              valueFormatter: (p) =>
                p.value === null ? "MISSING" : Number(p.value).toFixed(4),
            },
            { field: "association", headerName: "Association" },
          ]}
        />
      )}
    </div>
  );
  return (
    <div className="app-screen">
      <Toolbar>
        <Button
          icon={Save}
          onClick={() => {
            if (!persistStored("post-analyses", analyses)) {
              setMessage(
                "브라우저 저장 실패 · 분석과 revision을 유지했습니다. 하단에서 재시도하세요.",
              );
              return;
            }
            if (saveFail) {
              setMessage(
                "문서 저장 실패 · 분석 정의·편집 입력·원본 참조를 보존했습니다. 재시도하세요.",
              );
              setSaveFail(false);
            } else {
              setRevision(revision + 1);
              setMessage(
                `PostDocument r${revision + 1} 저장 · 원본 참조·분석·보기 보존`,
              );
            }
          }}
        >
          문서 저장
        </Button>
        <div className="toolbar-separator" />
        {(["native", "probe", "slice", "line", "compare"] as Operation[]).map(
          (op) => (
            <Button
              key={op}
              icon={
                op === "native" || op === "probe"
                  ? Crosshair
                  : op === "line"
                    ? Waypoints
                    : op === "compare"
                      ? Columns2
                      : Scissors
              }
              disabled={unavailable || !!command}
              onClick={() => start(op)}
            >
              {operationNames[op]}
            </Button>
          ),
        )}
        <span className="spacer" />
        <Button
          icon={Columns2}
          className={layout ? "active" : ""}
          onClick={() => setLayout(!layout)}
        >
          {layout ? "장 분석 배치" : "A/B 배치"}
        </Button>
      </Toolbar>
      <div className="pre-save-strip">
        <Badge tone={missingB ? "warn" : "info"}>
          {missingB ? "부분 복구" : "문서 r" + revision}
        </Badge>
        <span>{message}</span>
        <span className="spacer" />
        <label>
          <input
            type="checkbox"
            checked={saveFail}
            onChange={(e) => setSaveFail(e.target.checked)}
          />
          다음 저장 실패 시험
        </label>
      </div>
      <Workspace
        id="post-v1"
        panels={{
          sources: { title: "Pipeline · 원본 / 분석", content: sources },
          view: { title: "장 분석 · 비교", content: view },
          properties: { title: "Source · 연산 속성", content: property },
          results: { title: "원위치 조회표", content: results },
        }}
        setup={(api) => {
          api.addPanel({
            id: "view",
            component: "content",
            title: "장 분석 · 비교",
          });
          api.addPanel({
            id: "sources",
            component: "content",
            title: "Pipeline · 원본 / 분석",
            position: { referencePanel: "view", direction: "left" },
            initialWidth: 230,
          });
          api.addPanel({
            id: "properties",
            component: "content",
            title: "Source · 연산 속성",
            position: { referencePanel: "view", direction: "right" },
            initialWidth: 280,
          });
          api.addPanel({
            id: "results",
            component: "content",
            title: "원위치 조회표",
            position: { referencePanel: "view", direction: "below" },
            initialHeight: 190,
          });
        }}
      />
    </div>
  );
}
