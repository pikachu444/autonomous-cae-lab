# Abaqus 2026 / HyperMesh 2026 browser studies

The user explicitly requested two working browser studies that follow these
products' established application interfaces. Web technology is allowed. A new
dashboard, simplified card UI, or desktop-only interpretation is not requested.
These are interface reproductions, not licensed Abaqus/HyperMesh applications.

## Visual authority

- Abaqus/CAE 2026.HF2 actual screen in Dassault SIMULIA Community:
  https://3dswym.3dexperience.3ds.com/post/simulia-community/eroding-contact-defined-in-abaqus-cae_ImFO0rT6SOmN10CCcKq8Sw
  Direct image: https://3dswym.3dexperience.3ds.com/media?id=JH3eQ1qrTfSpQia9JpV2VA
- HyperMesh 2026 official workspace, version stated in the documentation:
  https://help.altair.com/hwdesktop/hwx/topics/chapter_heads/workspace_r.htm
  https://help.altair.com/hwdesktop/hwx/images/workspace_hwx.png
- Local reference captures are under artifacts/engineering-ui-20261010/.

The Abaqus 2026 full reference manual URL was unavailable. The actual 2026.HF2
screen establishes the visual reference; older documentation must not be
represented as verified 2026 functionality.

## Required result

Separate abaqus.html and hypermesh.html, each filling the browser viewport.
No surrounding website shell, cards, marketing introduction, giant title, or
revision badges. Normal compact application menus, toolbars, native-looking
forms, resizable panels, and a large model workspace. English tool names follow
the reference. One quiet status-bar label identifies the browser study.

The model and retained displacement data come from existing local project
artifacts. UI commands change the displayed model/state; they do not claim new
CAD-kernel edits, remeshing, commercial-solver runs, or engineering approval.
Actual commands must be observable: selection, visibility/isolation, camera,
representation, section clipping, exploded assembly, field/component and
deformation display, exact node query, material/condition definitions, Undo/Redo,
save/reopen of the browser study, table/curve selection and workspace sizing.
Unsupported native calculation commands explain the absent connection and never
produce fake success. Do not populate result arrays with invented solver values.

## Ownership and integration

Root owns reference-main.tsx, reference-build.mjs, src/replicas/Scene.tsx,
src/replicas/model.ts, src/replicas/base.css and the generated local data.
Worker A owns src/replicas/Abaqus.tsx and Abaqus.css only.
Worker B owns src/replicas/HyperMesh.tsx and HyperMesh.css only.
Workers are not alone in the codebase. Do not revert or edit each other's files.

Both export a default React component. Both may use installed React, lucide-react,
AG Grid, Plotly, Dockview, and Three; shared old application CSS is not imported.
Scene contract is fixed below; root will implement it in parallel.

```ts
type SceneProps = {
  theme: 'abaqus' | 'hypermesh';
  dataset?: 'assembly' | 'result';
  representation?: 'shaded' | 'edges' | 'wireframe' | 'transparent';
  selected?: string[];
  hidden?: string[];
  onSelect?: (id: string, additive: boolean) => void;
  onProbe?: (node: {id: number; x: number; y: number; z: number;
    ux: number; uy: number; uz: number; magnitude: number}) => void;
  command?: {name: 'fit'|'iso'|'front'|'top'|'right'|'zoomIn'|'zoomOut'; tick: number};
  explode?: number; // 0..1 assembly display displacement only
  clip?: {enabled: boolean; axis: 'x'|'y'|'z'; position: number}; // normalized 0..1
  field?: 'none'|'magnitude'|'ux'|'uy'|'uz';
  deformation?: number; // display multiplier of actual retained U
  showLoads?: boolean;
  probeMode?: boolean;
  probeId?: number; // exact retained node selected in the table/query/plot
};
export function Scene(props: SceneProps): JSX.Element;
```

`model.ts` exports `components: {id:string; name:string; color:string;
kind:string; faces:number; triangles:number}[]`, `resultNodes` (same fields as
onProbe), and `resultInfo: {nodes:number; elements:number; unit:string;
source:string; maxMagnitude:number; minUz:number; maxUz:number}`.
The result dataset is a single retained support mesh, not the whole assembly.
Use result ID `result-support`; avoid showing assembly metadata as its source.

## Inspection

Build once, inspect both at 1440x900 and 1920x1080, exercise core controls, fix
findings in one batch, then confirm. Inspect the two official references beside
the actual renders. Record actual observations and untested boundaries without
turning basic interaction checks into a claim of professional feature parity.

## Observed result — 2026-10-10

Two self-contained HTML files build successfully. TypeScript and the scoped
design detector pass. Actual browser inspection covered 1280x720, 1440x900 and
1920x1080, with no whole-page overflow or console errors/warnings observed.

Root exercised material validation, Undo/Redo, multiple materials/conditions,
target preservation during another selection, JSON save/new/reopen, malformed
JSON rejection without losing the open study, panel resizing, hide/restore,
exploded display, section clipping, field/deformation changes and exact node
query. Node 331 has Uz = -4.58389e-5 mm in both screens; a direct viewport pick
selected node 2957. Both values were compared to the original VTU arrays.
Abaqus table node 302 also appears as a separate selected XY point, even though
it is absent from the reduced background scatter. This is a spatial/node plot,
not a manufactured time response.

Independent source and screenshot review found five material issues, all fixed:
unrelated load arrows, new definitions overwriting old ones, repeated ribbon
glyphs, malformed nested study data and missing XY selection markers. The
reviewer confirmed these corrections from source and actual captures; Root
performed browser actions. A subsequent Root check also fixed Query resetting
an already selected field. Main Model ribbon tools now have distinct glyphs.

The captures, saved-study specimens and final bundles are retained locally at
`artifacts/engineering-ui-20261010/`; the acceptance record names their hashes.
No native CAD edit/remesh, commercial solver job or new numerical evaluation
was run. Browser study JSON is not a native .cae/.hm file. Module coverage,
keyboard shortcuts and algorithms are not equivalent to the full commercial
products. The earlier six-app synthetic study is not product acceptance.
