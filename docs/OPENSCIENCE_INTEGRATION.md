# OpenScience integration status

## Primary local continuation

Pinned OpenScience 2.0.146 is installed in an isolated Windows profile and
uses the existing local Ollama runtime; actual MCP connector listing succeeds.
A full prompt attempt failed acceptance despite exit0 because it made no tools
or experiments. A compact primary agent with a preserved-original 16k model
alias has now made a real study_create MCP call and persisted S-open-live.
The later live04 study and eight-candidate discovery also succeeded, but variable
registration invoked no tool. Its registry stayed revision0 and no experiments
were written; full acceptance is FAILED_OR_PARTIAL. Official GUI usage has not
been verified locally. The separate Lab browser surface has no live AI chat
connection. See [OPENSCIENCE_USE](OPENSCIENCE_USE.md) and
[CONNECTED_ACCEPTANCE](CONNECTED_ACCEPTANCE.md). See
[CONNECTED_CONTINUATION](CONNECTED_CONTINUATION.md) for failed
attempts, profile permissions and active-context evidence. The following older
cloud record is preserved and does not describe the restored local runtime.

## Historical cloud investigation

Provisional upstream: [Synthetic Sciences OpenScience](https://github.com/synthetic-sciences/openscience), examined at `8179773d14c6c552a23592323c782cd09b171df9`. Its [connector documentation](https://github.com/synthetic-sciences/openscience/blob/main/frontend/docs/src/content/openscience/connectors.mdx) describes project `openscience.json` local stdio MCP commands. Configure this repository's MCP bridge with absolute Python and script paths, point `CAELAB_STORE` at a persistent local directory and use the research instructions in `AGENTS.md.example`. The [runtime API](https://github.com/synthetic-sciences/openscience/blob/main/frontend/docs/src/content/openscience/api.mdx) has a server/SDK path for headless campaigns; a completed agent turn is not engineering validation.

The MCP Python SDK completed a local stdio handshake, tool discovery and valid CAD experiment. OpenScience CLI v2.0.145 was installed temporarily, but `openscience mcp list` stopped before configuration loading because this container's PID namespace and `/proc` view disagreed. No live OpenScience agent/tool trace is claimed. On a normal host, run `openscience mcp list`, ask the agent to discover, register and execute 38 mm width and rejected 30 mm bolt pitch experiments, then inspect OpenScience events and CAE-Lab evidence/artifact IDs. The exact upstream identity must be reconciled with the earlier Project conversation when available.

For company data, review OpenScience [sandbox behavior](https://github.com/synthetic-sciences/openscience/blob/main/SECURITY.md), local MCP execution permissions, [trace sharing and provider endpoints](https://github.com/synthetic-sciences/openscience/blob/main/frontend/docs/src/content/openscience/privacy.mdx). Linux bubblewrap/macOS Seatbelt are documented; Windows sandbox was not present in the examined code. Test the installed version's security settings before any protected model or test data is used. The inspected OpenScience source is Apache-2.0; connectors and models may have separate terms.
