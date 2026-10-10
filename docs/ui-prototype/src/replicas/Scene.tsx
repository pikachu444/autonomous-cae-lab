import { useEffect, useRef } from "react";
import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import {
  assemblyGeometry,
  resultGeometry,
  resultInfo,
  type ResultNode,
} from "./model";

export type SceneProps = {
  theme: "abaqus" | "hypermesh";
  dataset?: "assembly" | "result";
  representation?: "shaded" | "edges" | "wireframe" | "transparent";
  selected?: string[];
  hidden?: string[];
  onSelect?: (id: string, additive: boolean) => void;
  onProbe?: (node: ResultNode) => void;
  command?: {
    name: "fit" | "iso" | "front" | "top" | "right" | "zoomIn" | "zoomOut";
    tick: number;
  };
  explode?: number;
  clip?: { enabled: boolean; axis: "x" | "y" | "z"; position: number };
  field?: "none" | "magnitude" | "ux" | "uy" | "uz";
  deformation?: number;
  showLoads?: boolean;
  probeMode?: boolean;
  probeId?: number;
};

type SceneHandle = {
  renderer: THREE.WebGLRenderer;
  scene: THREE.Scene;
  camera: THREE.OrthographicCamera;
  controls: OrbitControls;
  meshes: THREE.Mesh[];
  center: THREE.Vector3;
  bounds: THREE.Box3;
  extent: number;
  clipping: THREE.Plane;
  loads: THREE.Group;
  marker: THREE.Group;
  fit: (direction?: "iso" | "front" | "top" | "right") => void;
};

function spectrum(value: number) {
  return new THREE.Color().setHSL(
    (1 - Math.max(0, Math.min(1, value))) * 0.67,
    0.97,
    0.48,
  );
}

export function Scene(props: SceneProps) {
  const host = useRef<HTMLDivElement>(null);
  const current = useRef(props);
  current.current = props;
  const handle = useRef<SceneHandle | null>(null);
  const resultMode = props.dataset === "result";

  useEffect(() => {
    const parent = host.current;
    if (!parent) return;
    const scene = new THREE.Scene();
    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
    renderer.setClearColor(0x000000, 0);
    renderer.outputColorSpace = THREE.SRGBColorSpace;
    renderer.localClippingEnabled = true;
    renderer.domElement.setAttribute(
      "aria-label",
      "Interactive engineering model",
    );
    parent.appendChild(renderer.domElement);
    const camera = new THREE.OrthographicCamera(-100, 100, 75, -75, 0.01, 5000);
    camera.up.set(0, 0, 1);
    const controls = new OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;
    controls.dampingFactor = 0.16;
    controls.screenSpacePanning = true;
    controls.minZoom = 0.15;
    controls.maxZoom = 25;
    scene.add(new THREE.AmbientLight(0xffffff, 1.4));
    const key = new THREE.DirectionalLight(0xffffff, 2.1);
    key.position.set(100, -160, 240);
    scene.add(key);
    const fill = new THREE.DirectionalLight(0xdde6fa, 1.3);
    fill.position.set(-140, 100, 70);
    scene.add(fill);
    const clipping = new THREE.Plane(new THREE.Vector3(1, 0, 0), 0);
    const meshes: THREE.Mesh[] = [];
    const addMesh = (
      id: string,
      geometry: THREE.BufferGeometry,
      color: string,
    ) => {
      geometry.computeVertexNormals();
      geometry.computeBoundingBox();
      const material = new THREE.MeshStandardMaterial({
        color,
        metalness: 0.08,
        roughness: 0.65,
        side: THREE.DoubleSide,
      });
      const mesh = new THREE.Mesh(geometry, material);
      mesh.userData = {
        id,
        color,
        center: geometry.boundingBox!.getCenter(new THREE.Vector3()),
      };
      const edges = new THREE.LineSegments(
        resultMode
          ? new THREE.WireframeGeometry(geometry)
          : new THREE.EdgesGeometry(geometry, 24),
        new THREE.LineBasicMaterial({
          color: props.theme === "abaqus" ? 0x252c38 : 0x343b44,
          transparent: true,
          opacity: resultMode ? 0.56 : 0.78,
        }),
      );
      edges.name = "edges";
      mesh.add(edges);
      scene.add(mesh);
      meshes.push(mesh);
    };
    if (resultMode) {
      const geometry = new THREE.BufferGeometry();
      geometry.setAttribute(
        "position",
        new THREE.Float32BufferAttribute(
          resultGeometry.nodes.flatMap((n) => [n.x, n.y, n.z]),
          3,
        ),
      );
      geometry.setIndex(resultGeometry.triangles);
      addMesh(
        "result-support",
        geometry,
        props.theme === "abaqus" ? "#bbc486" : "#73ad80",
      );
    } else {
      for (const component of assemblyGeometry) {
        const geometry = new THREE.BufferGeometry();
        geometry.setAttribute(
          "position",
          new THREE.Float32BufferAttribute(component.positions, 3),
        );
        addMesh(
          component.id,
          geometry,
          props.theme === "abaqus"
            ? component.kind === "Fastener"
              ? "#abb3b9"
              : "#c9c9a8"
            : component.color,
        );
      }
    }
    const bounds = new THREE.Box3();
    meshes.forEach((mesh) => bounds.expandByObject(mesh));
    const center = bounds.getCenter(new THREE.Vector3());
    const size = bounds.getSize(new THREE.Vector3());
    const extent = Math.max(size.x, size.y, size.z);
    controls.target.copy(center);
    let fitted = false;
    const fit = (direction: "iso" | "front" | "top" | "right" = "iso") => {
      const delta =
        direction === "front"
          ? new THREE.Vector3(0, -2, 0.0001)
          : direction === "top"
            ? new THREE.Vector3(0, -0.0001, 2)
            : direction === "right"
              ? new THREE.Vector3(2, 0, 0.0001)
              : new THREE.Vector3(1.3, -1.9, 1.3);
      camera.position.copy(center).add(delta.multiplyScalar(extent));
      camera.zoom = 1;
      camera.updateProjectionMatrix();
      controls.target.copy(center);
      controls.update();
      fitted = true;
    };
    const loads = new THREE.Group();
    const loadedPoints = resultMode
      ? resultGeometry.nodes.filter((n) => n.loaded)
      : [];
    const loadPositions = resultMode
      ? loadedPoints
          .filter(
            (_, i) =>
              i % Math.max(1, Math.floor(loadedPoints.length / 9)) === 0,
          )
          .slice(0, 9)
          .map((n) => new THREE.Vector3(n.x, n.y, n.z))
      : [];
    for (const position of loadPositions) {
      const arrow = new THREE.ArrowHelper(
        new THREE.Vector3(0, 0, -1),
        position.clone().add(new THREE.Vector3(0, 0, extent * 0.15)),
        extent * 0.15,
        0xe59a10,
        extent * 0.035,
        extent * 0.017,
      );
      loads.add(arrow);
    }
    scene.add(loads);
    const marker = new THREE.Group();
    const dot = new THREE.Mesh(
      new THREE.SphereGeometry(extent * 0.009, 16, 12),
      new THREE.MeshBasicMaterial({ color: 0xffec55, depthTest: false }),
    );
    dot.renderOrder = 100;
    marker.add(dot);
    marker.visible = false;
    scene.add(marker);
    const raycaster = new THREE.Raycaster();
    let down = { x: 0, y: 0 };
    const pointerDown = (event: PointerEvent) => {
      down = { x: event.clientX, y: event.clientY };
    };
    const pointerUp = (event: PointerEvent) => {
      if (
        event.button !== 0 ||
        Math.hypot(event.clientX - down.x, event.clientY - down.y) > 4
      )
        return;
      const rect = renderer.domElement.getBoundingClientRect();
      raycaster.setFromCamera(
        new THREE.Vector2(
          ((event.clientX - rect.left) / rect.width) * 2 - 1,
          (-(event.clientY - rect.top) / rect.height) * 2 + 1,
        ),
        camera,
      );
      const hit = raycaster
        .intersectObjects(
          meshes.filter((m) => m.visible),
          false,
        )
        .find(
          (h) =>
            !current.current.clip?.enabled ||
            clipping.distanceToPoint(h.point) >= 0,
        );
      if (!hit) {
        if (!event.ctrlKey && !event.shiftKey)
          current.current.onSelect?.("", false);
        return;
      }
      const mesh = hit.object as THREE.Mesh;
      if (resultMode && current.current.probeMode && hit.face) {
        const positions = mesh.geometry.getAttribute("position");
        let nearest = hit.face.a,
          distance = Infinity;
        for (const index of [hit.face.a, hit.face.b, hit.face.c]) {
          const point = new THREE.Vector3()
            .fromBufferAttribute(positions, index)
            .applyMatrix4(mesh.matrixWorld);
          const candidate = point.distanceToSquared(hit.point);
          if (candidate < distance) {
            distance = candidate;
            nearest = index;
          }
        }
        const node = resultGeometry.nodes[nearest];
        marker.position.copy(
          new THREE.Vector3().fromBufferAttribute(positions, nearest),
        );
        marker.visible = true;
        current.current.onProbe?.(node);
      } else {
        current.current.onSelect?.(
          String(mesh.userData.id),
          event.ctrlKey || event.metaKey || event.shiftKey,
        );
      }
    };
    renderer.domElement.addEventListener("pointerdown", pointerDown);
    renderer.domElement.addEventListener("pointerup", pointerUp);
    const observer = new ResizeObserver(() => {
      const w = parent.clientWidth,
        h = parent.clientHeight;
      if (!w || !h) return;
      renderer.setSize(w, h);
      const half = extent * (resultMode ? 0.74 : 0.63);
      camera.left = (-half * w) / h;
      camera.right = (half * w) / h;
      camera.top = half;
      camera.bottom = -half;
      camera.updateProjectionMatrix();
      if (!fitted) fit();
    });
    observer.observe(parent);
    let frame = 0;
    const draw = () => {
      controls.update();
      if (!document.hidden) renderer.render(scene, camera);
      frame = requestAnimationFrame(draw);
    };
    draw();
    handle.current = {
      renderer,
      scene,
      camera,
      controls,
      meshes,
      center,
      bounds,
      extent,
      clipping,
      loads,
      marker,
      fit,
    };
    return () => {
      handle.current = null;
      cancelAnimationFrame(frame);
      observer.disconnect();
      controls.dispose();
      renderer.domElement.removeEventListener("pointerdown", pointerDown);
      renderer.domElement.removeEventListener("pointerup", pointerUp);
      scene.traverse((object) => {
        if (
          object instanceof THREE.Mesh ||
          object instanceof THREE.LineSegments ||
          object instanceof THREE.Line
        ) {
          object.geometry.dispose();
          (Array.isArray(object.material)
            ? object.material
            : [object.material]
          ).forEach((material) => material.dispose());
        }
      });
      renderer.dispose();
      renderer.domElement.remove();
    };
  }, [props.theme, resultMode]);

  useEffect(() => {
    const h = handle.current;
    if (!h) return;
    const representation = props.representation ?? "edges";
    const field = props.field ?? "none";
    const axis = props.clip?.axis ?? "x";
    const cut =
      h.bounds.min[axis] +
      (h.bounds.max[axis] - h.bounds.min[axis]) * (props.clip?.position ?? 0.5);
    h.clipping.normal.set(
      axis === "x" ? 1 : 0,
      axis === "y" ? 1 : 0,
      axis === "z" ? 1 : 0,
    );
    h.clipping.constant = -cut;
    const planes = props.clip?.enabled ? [h.clipping] : [];
    for (const mesh of h.meshes) {
      const id = String(mesh.userData.id);
      mesh.visible = !(props.hidden ?? []).includes(id);
      const material = mesh.material as THREE.MeshStandardMaterial;
      const selected = (props.selected ?? []).includes(id);
      material.color.set(
        selected
          ? props.theme === "abaqus"
            ? "#f39868"
            : "#e8b859"
          : mesh.userData.color,
      );
      material.wireframe = representation === "wireframe";
      material.transparent = representation === "transparent";
      material.opacity = representation === "transparent" ? 0.3 : 1;
      material.clippingPlanes = planes;
      const edges = mesh.getObjectByName("edges") as THREE.LineSegments;
      if (edges) {
        edges.visible =
          representation === "edges" || representation === "transparent";
        (edges.material as THREE.LineBasicMaterial).clippingPlanes = planes;
      }
      if (!resultMode) {
        const direction = (mesh.userData.center as THREE.Vector3)
          .clone()
          .sub(h.center);
        direction.z += h.extent * 0.04;
        mesh.position.copy(
          direction.multiplyScalar((props.explode ?? 0) * 0.9),
        );
      } else {
        const position = mesh.geometry.getAttribute(
          "position",
        ) as THREE.BufferAttribute;
        resultGeometry.nodes.forEach((n, i) =>
          position.setXYZ(
            i,
            n.x + n.ux * (props.deformation ?? 0),
            n.y + n.uy * (props.deformation ?? 0),
            n.z + n.uz * (props.deformation ?? 0),
          ),
        );
        position.needsUpdate = true;
        mesh.geometry.computeVertexNormals();
        mesh.geometry.computeBoundingSphere();
        if (edges) {
          edges.geometry.dispose();
          edges.geometry = new THREE.WireframeGeometry(mesh.geometry);
        }
        material.vertexColors = field !== "none";
        if (field !== "none") {
          const values = resultGeometry.nodes.map((n) => n[field]);
          const min = Math.min(...values),
            max = Math.max(...values),
            span = max - min || 1;
          const colors = values.flatMap((value) => {
            const c = spectrum((value - min) / span);
            return [c.r, c.g, c.b];
          });
          mesh.geometry.setAttribute(
            "color",
            new THREE.Float32BufferAttribute(colors, 3),
          );
          material.color.set("#ffffff");
        }
      }
      material.needsUpdate = true;
    }
    h.loads.visible = resultMode && Boolean(props.showLoads);
    h.marker.visible = false;
  }, [
    props.theme,
    resultMode,
    props.representation,
    props.selected,
    props.hidden,
    props.explode,
    props.clip,
    props.field,
    props.deformation,
    props.showLoads,
  ]);

  useEffect(() => {
    const h = handle.current,
      command = props.command;
    if (!h || !command) return;
    if (command.name === "zoomIn" || command.name === "zoomOut") {
      h.camera.zoom *= command.name === "zoomIn" ? 1.2 : 1 / 1.2;
      h.camera.updateProjectionMatrix();
    } else h.fit(command.name === "fit" ? "iso" : command.name);
  }, [props.command, resultMode]);

  useEffect(() => {
    const h = handle.current;
    if (!h || !resultMode) return;
    const node = resultGeometry.nodes.find((n) => n.id === props.probeId);
    h.marker.visible =
      Boolean(node) && !(props.hidden ?? []).includes("result-support");
    if (node) {
      const factor = props.deformation ?? 0;
      h.marker.position.set(
        node.x + node.ux * factor,
        node.y + node.uy * factor,
        node.z + node.uz * factor,
      );
    }
  }, [
    props.probeId,
    props.deformation,
    props.field,
    props.selected,
    props.hidden,
    props.clip,
    resultMode,
  ]);

  const field = props.field ?? "none";
  const values =
    resultMode && field !== "none"
      ? resultGeometry.nodes.map((n) => n[field])
      : [];
  const min = values.length ? Math.min(...values) : 0,
    max = values.length ? Math.max(...values) : 0;
  return (
    <div
      className={`engineering-scene scene-${props.theme}`}
      data-dataset={props.dataset ?? "assembly"}
    >
      <div className="scene-canvas" ref={host} />
      {resultMode && field !== "none" && (
        <div className="scene-legend" aria-label="Result legend">
          <strong>
            {field === "magnitude"
              ? "U, Magnitude"
              : `U, ${field.slice(-1).toUpperCase()}`}
          </strong>
          <span>[{resultInfo.unit}]</span>
          <div className="scene-scale">
            {Array.from({ length: 12 }, (_, i) => (
              <div key={i}>
                <i
                  style={{
                    background: `#${spectrum(1 - i / 11).getHexString()}`,
                  }}
                />
                <span>{(max - ((max - min) * i) / 11).toExponential(3)}</span>
              </div>
            ))}
          </div>
          <small>Retained static result</small>
        </div>
      )}
      <div className="scene-axes" aria-hidden="true">
        <svg viewBox="0 0 80 72">
          <path d="M30 49L63 58" stroke="#e8554e" />
          <path d="M30 49L9 62" stroke="#49b15f" />
          <path d="M30 49L30 13" stroke="#4e7df0" />
          <path
            d="M59 53L63 58L56 60M15 56L9 62L18 64M26 21L30 13L34 21"
            fill="none"
            stroke="currentColor"
          />
          <text x="66" y="65">
            X
          </text>
          <text x="0" y="72">
            Y
          </text>
          <text x="27" y="10">
            Z
          </text>
        </svg>
      </div>
      <div className="scene-caption">
        {resultMode
          ? `Support · ${resultInfo.nodes.toLocaleString()} nodes · ${resultInfo.elements.toLocaleString()} elements`
          : "Roller fixture · 15 components · mm"}
      </div>
    </div>
  );
}
