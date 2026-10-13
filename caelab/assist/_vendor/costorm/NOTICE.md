# Stanford Co-STORM subset

MIT source: stanford-oval/storm at fb951af7744dab086e34962e9bc6fe878e145f83.
Original LICENSE is retained. Source files identify the pin.

Retained: CoStormRunner, DiscourseManager, warm-start, actual moderator/expert modules,
knowledge tree/insertion/reorganization, article generation, dataclasses, interfaces,
logging and the two needed Wiki signatures and ArticleTextProcessing.

Application boundary changes: no eager provider/Bing/OpenAI embedding imports;
explicit LM/retriever/encoder injection and owner-controlled restoration. A narrow
namespaced signature-to-text bridge replaces the incompatible full DSPy dependency:
DSPy 2.4.9 requires OpenAI<2, whereas existing Haystack3.3 requires OpenAI>=2.6.
This is not a full DSPy implementation or a claim of untested model compatibility.
It preserves ordered fields, complete multiline prefixes, original output names,
and the rationale field; a malformed completion stops for explicit retry instead
of silently adding hidden continuation calls. No third-party package is downgraded.

Cosine similarity uses existing NumPy; lexical word/character-trigram hashing is
local and deterministic, not a semantic embedding service. Logging uses UTC;
serial context-propagating pools preserve cancellation ownership. Exception paths
in logging/warm-start/insertion propagate instead of silently dropping failed work.
Unresolved generated citations are refused before remapping. Archived source text
is not rewritten. Explicit input formatting fixes the upstream section path list.
No default provider, simulated user, key loader or public search is invoked.


Additional retained-source adaptation: a root-only knowledge tree keeps its generated
root paragraph as the report introduction. The upstream child-only report traversal
otherwise drops all evidence when reorganization removes the empty child sections.
Rejected completion keys are carried across worker boundaries; non-model preflight
failures do not invalidate a previously valid completion.
