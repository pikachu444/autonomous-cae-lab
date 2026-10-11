# Product UI and MCP planning sources

The current full plan is [PRODUCT_UI_MCP_PLAN](../../PRODUCT_UI_MCP_PLAN.md).
The [v2 UI PDF](Autonomous_CAE_Lab_UI_Plan_v2.pdf) contains 12 workspace layouts,
one MCP connection diagram and nine pages of official reference images.
These are planning artifacts, not screenshots proving a newly implemented product.

Actual ChatGPT Pro produced the original and one bounded revision in the
[existing design conversation](https://chatgpt.com/c/6aca5116-b90c-83ee-82fb-1b0299a87fd3).
Original v1/v2 files in this directory are preserved byte-for-byte. The current
PRODUCT_UI_MCP_PLAN also applies Pro's [validity review](../../REQUIREMENTS_VALIDITY_REVIEW.md)
to its wording and implementation dependencies. Current decisions take precedence over
historical wording in either preserved version. In particular, the old requirement
section count is not a product completion denominator or a mandatory phase order.
The separate validity review records each old section's current effect and reason.

Root read the complete v1 text and all 22 rendered pages, then reviewed the v2
changes. Two independent read-only reviews closed the six identified design gaps.
Changed PDF pages 2, 3, 4, 5, 9, 10 and 13 were visually inspected; the other fifteen
rendered PNG files have the same hashes as v1. See the
[review record](../../../benchmarks/records/20261011-full-product-ui-mcp-plan-review.json)
for file digests, scope and saved Page receipts.

The public source reviewed by Pro was a10f2023a2084512839b5e0af8ab0adc0aeb9293.
Root separately compared the specified Pre/Post, MCP/client/service, jobs and CLI
files with local 4fd9ceab7c561b605c3e50b417d434021e46ec60 and found no changes in
that bounded scope. This does not certify every current local file, Windows use,
a live native bridge, general Post import, or numerical correctness.

Original downloads and page renders also remain in the local ignored
artifacts/product-ui-mcp-plan-20261011 directory. No original experiment was
modified and no new product or solver run was performed for this document review.
