# KaTeX 0.19.0

The unmodified `dist/katex.min.js` and MIT license are retained from the
official npm package. `provenance.json` records its archive integrity and
the exact retained file hashes. No package install is needed at runtime.

Research answers use `output=mathml` and the local browser's MathML renderer.
No CDN, fonts or network requests are required. `trust=false`, `strict=error`,
bounded macro expansion and a fresh macro dictionary prevent answer text
from enabling HTML/URL extensions or carrying macros into another answer.
Unsupported expressions remain literal text; the exact raw answer is kept.

Official options: https://katex.org/docs/options
Security: https://katex.org/docs/security
