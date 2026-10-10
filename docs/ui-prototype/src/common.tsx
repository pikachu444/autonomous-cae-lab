import React, {
  createContext,
  useContext,
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from "react";
import {
  DockviewReact,
  themeLight,
  type DockviewApi,
  type IDockviewPanelProps,
} from "dockview";
import { AgGridReact } from "ag-grid-react";
import {
  ModuleRegistry,
  AllCommunityModule,
  themeQuartz,
  type ColDef,
  type CellValueChangedEvent,
  type GridApi,
} from "ag-grid-community";
import Plotly from "plotly.js-basic-dist-min";
import {
  Maximize2,
  Minimize2,
  RotateCcw,
  Move,
  type LucideIcon,
} from "lucide-react";
import "dockview/dist/styles/dockview.css";

ModuleRegistry.registerModules([AllCommunityModule]);
const prefix = "cae-design-v2:";
const pendingStorage = new Map<string, string>();
const storageListeners = new Set<() => void>();
let storageBlocked = false;
function storageChanged() {
  storageListeners.forEach((notify) => notify());
}
export function persistStored(key: string, value: unknown): boolean {
  const fullKey = prefix + key;
  const serialized = JSON.stringify(value);
  try {
    if (storageBlocked) throw new Error("Storage failure simulation");
    localStorage.setItem(fullKey, serialized);
    pendingStorage.delete(fullKey);
    storageChanged();
    return true;
  } catch {
    pendingStorage.set(fullKey, serialized);
    storageChanged();
    return false;
  }
}
export function useStorageHealth() {
  const [, update] = useState(0);
  useEffect(() => {
    const notify = () => update((n) => n + 1);
    storageListeners.add(notify);
    notify();
    return () => {
      storageListeners.delete(notify);
    };
  }, []);
  return pendingStorage.size === 0;
}
export function StorageStatus() {
  useStorageHealth();
  return (
    <div
      className={`storage-status ${pendingStorage.size ? "storage-error" : ""}`}
      role="status"
    >
      <span>
        {pendingStorage.size
          ? `브라우저 저장 실패 · ${pendingStorage.size}개 변경은 현재 창에만 남아 있습니다. 재열기 전에 재시도하세요.`
          : "배치·입력은 이 브라우저에 저장됩니다"}
      </span>
      {pendingStorage.size > 0 && (
        <Button
          onClick={() => {
            for (const [key, value] of [...pendingStorage]) {
              try {
                if (storageBlocked)
                  throw new Error("Storage failure simulation");
                localStorage.setItem(key, value);
                pendingStorage.delete(key);
              } catch {
                /* Retain every failed write for the next retry. */
              }
            }
            storageChanged();
          }}
        >
          저장 재시도
        </Button>
      )}
      <label>
        <input
          type="checkbox"
          checked={storageBlocked}
          onChange={(e) => {
            storageBlocked = e.target.checked;
            storageChanged();
          }}
        />
        브라우저 저장 실패 시험
      </label>
    </div>
  );
}
export function useStored<T>(
  key: string,
  initial: T,
): [T, React.Dispatch<React.SetStateAction<T>>] {
  const [value, setValue] = useState<T>(() => {
    try {
      const v =
        pendingStorage.get(prefix + key) ?? localStorage.getItem(prefix + key);
      return v ? JSON.parse(v) : initial;
    } catch {
      return initial;
    }
  });
  useEffect(() => {
    persistStored(key, value);
  }, [key, value]);
  return [value, setValue];
}
export function Button({
  children,
  icon,
  primary,
  danger,
  className = "",
  ...rest
}: React.ButtonHTMLAttributes<HTMLButtonElement> & {
  icon?: LucideIcon | ReactNode;
  primary?: boolean;
  danger?: boolean;
}) {
  const glyph =
    icon &&
    (typeof icon === "function" ||
      (typeof icon === "object" &&
        "$$typeof" in icon &&
        !React.isValidElement(icon)))
      ? React.createElement(icon as LucideIcon, { size: 15, strokeWidth: 1.7 })
      : icon;
  return (
    <button
      type="button"
      className={`button ${primary ? "primary" : ""} ${danger ? "danger" : ""} ${className}`}
      {...rest}
    >
      {glyph}
      {children}
    </button>
  );
}
export function Toolbar({ children }: { children: ReactNode }) {
  return <div className="toolbar">{children}</div>;
}
export function Badge({
  children,
  tone = "neutral",
}: {
  children: ReactNode;
  tone?: "good" | "warn" | "bad" | "info" | "neutral";
}) {
  return <span className={`badge ${tone}`}>{children}</span>;
}
export function Field({
  label,
  children,
}: {
  label: string;
  children: ReactNode;
}) {
  return (
    <label className="field">
      <span>{label}</span>
      {children}
    </label>
  );
}
export function Properties({ rows }: { rows: Array<[string, ReactNode]> }) {
  return (
    <dl className="property-list">
      {rows.map(([k, v]) => (
        <React.Fragment key={k}>
          <dt>{k}</dt>
          <dd>{v}</dd>
        </React.Fragment>
      ))}
    </dl>
  );
}
export function Notice({
  children,
  tone = "info",
}: {
  children: ReactNode;
  tone?: string;
}) {
  return (
    <div role="status" className={`notice ${tone}`}>
      {children}
    </div>
  );
}

type Panels = Record<string, { title: string; content: ReactNode }>;
const PanelContext = createContext<Panels>({});
function ContentPanel(p: IDockviewPanelProps) {
  const panels = useContext(PanelContext);
  return (
    <div className="dock-panel">
      {panels[p.api.id]?.content ?? <Notice>패널을 다시 열어 주세요.</Notice>}
    </div>
  );
}
const components = { content: ContentPanel };
export function Workspace({
  id,
  panels,
  setup,
}: {
  id: string;
  panels: Panels;
  setup: (api: DockviewApi) => void;
}) {
  const apiRef = useRef<DockviewApi | null>(null);
  const [active, setActive] = useState(Object.keys(panels)[0]);
  const [maximized, setMaximized] = useState(false);
  const [moveOpen, setMoveOpen] = useState(false);
  const [reference, setReference] = useState(
    Object.keys(panels)[1] ?? Object.keys(panels)[0],
  );
  const [direction, setDirection] = useState<
    "left" | "right" | "above" | "below"
  >("right");
  const [status, setStatus] = useState(
    "패널 제목을 끌어 배치 · 경계를 끌어 크기 조절",
  );
  const setupRef = useRef(setup);
  setupRef.current = setup;
  useEffect(() => {
    if (reference === active)
      setReference(Object.keys(panels).find((k) => k !== active) ?? active);
    for (const [key, panel] of Object.entries(panels)) {
      const api = apiRef.current?.getPanel(key)?.api;
      if (api && api.title !== panel.title) api.setTitle(panel.title);
    }
  }, [active, reference, panels]);
  const layoutKey = prefix + "layout:" + id;
  function reset() {
    const api = apiRef.current;
    if (!api) return;
    api.clear();
    setupRef.current(api);
    setStatus("기본 배치를 복원했습니다.");
  }
  function maximize() {
    const api = apiRef.current;
    if (!api) return;
    if (api.hasMaximizedGroup()) api.exitMaximizedGroup();
    else api.getPanel(active)?.api.maximize();
    setMaximized(api.hasMaximizedGroup());
  }
  return (
    <PanelContext.Provider value={panels}>
      <div className="workspace">
        <div className="layout-tools">
          <span className="layout-caption">{status}</span>
          <div className="spacer" />
          <label className="inline-label">
            작업창{" "}
            <select
              aria-label="작업창 선택"
              value={active}
              onChange={(e) => {
                setActive(e.target.value);
                apiRef.current?.getPanel(e.target.value)?.api.setActive();
              }}
            >
              {Object.entries(panels).map(([k, p]) => (
                <option key={k} value={k}>
                  {p.title}
                </option>
              ))}
            </select>
          </label>
          <Button icon={maximized ? Minimize2 : Maximize2} onClick={maximize}>
            {maximized ? "배치 복원" : "확대"}
          </Button>
          <Button
            icon={Move}
            aria-expanded={moveOpen}
            onClick={() => setMoveOpen(!moveOpen)}
          >
            이동
          </Button>
          <Button icon={RotateCcw} onClick={reset}>
            기본 배치
          </Button>
        </div>
        {moveOpen && (
          <div className="layout-move">
            <span>선택한 작업창을</span>
            <select
              aria-label="배치 기준 작업창"
              value={reference}
              onChange={(e) => setReference(e.target.value)}
            >
              {Object.entries(panels)
                .filter(([k]) => k !== active)
                .map(([k, p]) => (
                  <option key={k} value={k}>
                    {p.title}
                  </option>
                ))}
            </select>
            <select
              aria-label="배치 방향"
              value={direction}
              onChange={(e) => setDirection(e.target.value as typeof direction)}
            >
              <option value="left">왼쪽</option>
              <option value="right">오른쪽</option>
              <option value="above">위</option>
              <option value="below">아래</option>
            </select>
            <Button
              primary
              disabled={reference === active}
              onClick={() => {
                const api = apiRef.current;
                const ref = api?.getPanel(reference);
                if (ref) {
                  api?.getPanel(active)?.api.moveTo({
                    group: ref.group,
                    position:
                      direction === "above"
                        ? "top"
                        : direction === "below"
                          ? "bottom"
                          : direction,
                  });
                  setMoveOpen(false);
                  setStatus("작업창 배치를 저장했습니다.");
                }
              }}
            >
              배치 적용
            </Button>
          </div>
        )}
        <div className="dock-root dockview-theme-light">
          <DockviewReact
            theme={themeLight}
            components={components}
            onReady={(e) => {
              const api = e.api;
              apiRef.current = api;
              try {
                const saved = localStorage.getItem(layoutKey);
                if (saved) api.fromJSON(JSON.parse(saved));
                else setupRef.current(api);
              } catch {
                api.clear();
                setupRef.current(api);
                setStatus("저장 배치를 읽지 못해 기본 배치를 열었습니다.");
              }
              for (const [key, p] of Object.entries(panels))
                if (!api.getPanel(key))
                  api.addPanel({
                    id: key,
                    title: p.title,
                    component: "content",
                  });
              if (api.activePanel) setActive(api.activePanel.id);
              api.onDidActivePanelChange((p) => {
                if (p) setActive(p.id);
              });
              api.onDidLayoutChange(() => {
                setMaximized(api.hasMaximizedGroup());
                if (!persistStored("layout:" + id, api.toJSON())) {
                  setStatus("이 환경에서는 배치 저장을 사용할 수 없습니다.");
                }
              });
            }}
          />
        </div>
      </div>
    </PanelContext.Provider>
  );
}

const gridTheme = themeQuartz.withParams({
  fontFamily: "Segoe UI, Malgun Gothic, sans-serif",
  fontSize: 12,
  headerFontSize: 11,
  rowHeight: 31,
  headerHeight: 32,
  backgroundColor: "#ffffff",
  foregroundColor: "#273544",
  headerBackgroundColor: "#f2f4f7",
  borderColor: "#d4dce5",
  accentColor: "#24649b",
  selectedRowBackgroundColor: "#e2eef8",
  rowHoverColor: "#f2f7fb",
  wrapperBorder: false,
  wrapperBorderRadius: 0,
  cellHorizontalPadding: 11,
});
export function DataGrid({
  rows,
  columns,
  selectedId,
  onSelect,
  onEdit,
  height,
}: {
  rows: any[];
  columns: ColDef[];
  selectedId?: string;
  onSelect?: (row: any) => void;
  onEdit?: (event: CellValueChangedEvent) => void;
  height?: number | string;
}) {
  const api = useRef<GridApi | null>(null);
  const selectRef = useRef(onSelect);
  selectRef.current = onSelect;
  useEffect(() => {
    if (!api.current) return;
    api.current.forEachNode((n) => n.setSelected(n.data?.id === selectedId));
    const node = selectedId ? api.current.getRowNode(selectedId) : undefined;
    if (node) api.current.ensureNodeVisible(node, "middle");
  }, [selectedId, rows]);
  return (
    <div
      className="data-grid"
      style={height ? { height, flex: "none" } : undefined}
    >
      <AgGridReact
        theme={gridTheme}
        rowData={rows}
        columnDefs={columns.map((c) => ({
          ...c,
          flex: c.flex ?? (c.width ? undefined : 1),
        }))}
        getRowId={(p) => String(p.data.id)}
        defaultColDef={{ resizable: true, sortable: true, minWidth: 75 }}
        maintainColumnOrder
        rowSelection={{
          mode: "singleRow",
          checkboxes: false,
          enableClickSelection: true,
        }}
        onGridReady={(e) => {
          api.current = e.api;
          if (selectedId) e.api.getRowNode(selectedId)?.setSelected(true);
        }}
        onRowClicked={(e) => selectRef.current?.(e.data)}
        onRowSelected={(e) => {
          if (e.node.isSelected() && e.source !== "api")
            selectRef.current?.(e.data);
        }}
        onCellValueChanged={onEdit}
        tooltipShowDelay={300}
        animateRows={false}
      />
    </div>
  );
}

export function Chart({
  data,
  layout,
  onSelect,
}: {
  data: any[];
  layout?: Record<string, any>;
  onSelect?: (id: string, point?: any) => void;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const callback = useRef(onSelect);
  callback.current = onSelect;
  useEffect(() => {
    const node = ref.current;
    if (!node) return;
    Plotly.react(
      node,
      data,
      {
        autosize: true,
        margin: { l: 55, r: 20, t: 25, b: 45 },
        paper_bgcolor: "#fff",
        plot_bgcolor: "#fff",
        font: {
          family: "Segoe UI, Malgun Gothic, sans-serif",
          size: 11,
          color: "#546579",
        },
        xaxis: { gridcolor: "#e5eaf0", zerolinecolor: "#c8d2df" },
        yaxis: { gridcolor: "#e5eaf0", zerolinecolor: "#c8d2df" },
        showlegend: false,
        hovermode: "closest",
        uirevision: "stable",
        ...layout,
      },
      { responsive: true, displayModeBar: false, scrollZoom: false },
    );
  }, [data, layout]);
  useEffect(() => {
    const node = ref.current as any;
    if (!node) return;
    const listener = (e: any) => {
      const p = e.points?.[0];
      if (p)
        callback.current?.(String(p.customdata ?? p.text ?? p.pointIndex), p);
    };
    node.on("plotly_click", listener);
    const ro = new ResizeObserver(() => Plotly.Plots.resize(node));
    ro.observe(node);
    return () => {
      ro.disconnect();
      node.removeListener("plotly_click", listener);
      Plotly.purge(node);
    };
  }, []);
  return <div ref={ref} className="chart" />;
}
