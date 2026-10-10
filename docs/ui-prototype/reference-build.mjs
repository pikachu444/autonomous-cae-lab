import { build } from "esbuild";
import { mkdir, readFile, writeFile } from "node:fs/promises";
await mkdir("dist/reference", { recursive: true });
await build({
  entryPoints: ["src/reference-main.tsx"],
  bundle: true,
  format: "iife",
  minify: true,
  sourcemap: false,
  outfile: "dist/reference/app.js",
  define: { "process.env.NODE_ENV": '"production"' },
  legalComments: "eof",
});
const js = (await readFile("dist/reference/app.js", "utf8")).replaceAll(
  "</script",
  "<\\/script",
);
const css = await readFile("dist/reference/app.css", "utf8");
for (const [name, title] of [
  ["abaqus", "Abaqus 2026 — browser interface study"],
  ["hypermesh", "HyperMesh 2026 — browser interface study"],
]) {
  const html = `<!doctype html><html lang="en"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>${title}</title><style>${css}</style></head><body><div id="root"></div><script>${js}</script></body></html>`;
  await writeFile(`dist/${name}.html`, html);
  console.log(
    `${name}.html: ${Buffer.byteLength(html).toLocaleString()} bytes`,
  );
}
