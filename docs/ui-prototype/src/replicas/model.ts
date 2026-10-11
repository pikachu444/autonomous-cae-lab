import assembly from "./assembly-data.json";
import result from "./result-data.json";

export const assemblyGeometry = assembly;
export const resultGeometry = result;
export const components = assembly.map(
  ({ id, name, color, kind, faces, triangles }) => ({
    id,
    name,
    color,
    kind,
    faces,
    triangles,
  }),
);
export const resultNodes = result.nodes;
export const resultInfo = result.info;
export type ResultNode = (typeof resultNodes)[number];

function boundsOf(positions: number[]) {
  const min = [Infinity, Infinity, Infinity],
    max = [-Infinity, -Infinity, -Infinity];
  positions.forEach((value, i) => {
    min[i % 3] = Math.min(min[i % 3], value);
    max[i % 3] = Math.max(max[i % 3], value);
  });
  return { min, max, dimensions: max.map((value, i) => value - min[i]) };
}
export const componentBounds = Object.fromEntries(
  assembly.map((c) => [c.id, boundsOf(c.positions)]),
);
export const assemblyBounds = boundsOf(assembly.flatMap((c) => c.positions));
export const resultBounds = boundsOf(
  result.nodes.flatMap((n) => [n.x, n.y, n.z]),
);
