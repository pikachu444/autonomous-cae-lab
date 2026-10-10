import { build } from "esbuild";
import { mkdir, readFile, writeFile } from "node:fs/promises";
const out = "dist";
await mkdir(out, { recursive: true });
await build({
  entryPoints: ["src/main.tsx"],
  bundle: true,
  format: "iife",
  minify: true,
  sourcemap: false,
  outfile: `${out}/app.js`,
  define: { "process.env.NODE_ENV": '"production"' },
  loader: { ".woff2": "dataurl" },
  legalComments: "eof",
});
const js = (await readFile(`${out}/app.js`, "utf8")).replaceAll(
  "</script",
  "<\\/script",
);
const css = await readFile(`${out}/app.css`, "utf8");
const html = `<!doctype html><html lang="ko"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>CAE Lab · Interaction Study</title><style>${css}</style></head><body><div id="root"></div><script>${js}</script></body></html>`;
await writeFile(`${out}/index.html`, html);
console.log(
  `Built standalone dist/index.html (${(Buffer.byteLength(html) / 1024 / 1024).toFixed(2)} MiB)`,
);
