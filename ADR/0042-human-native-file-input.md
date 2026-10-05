# 0042 — Connect human FCStd input to the existing native model workflow

Status: Accepted, 2026-10-06. Requirements R01–R03, R19–R22, R43, R48, R52.

The Core/CLI/MCP already import editable FreeCAD documents, discover native
parameters and preserve CAD experiment revisions. The Lab UI could create a
sample or inspect an ID but could not accept a person's own FCStd file. G1
connects this missing input to existing Core and adapter behavior; it does not
replace native import or create another CAD implementation.

A same-origin, tokenized binary POST accepts one FCStd document between 100 bytes
and 25 MiB, matching the pinned importer's bounds. JSON remains limited to
128 KiB. No client host path, archive extraction, solver inference, public MCP
operation or research-profile widening is added. Existing Host/Origin,
read-only, store-containment, single-job, journal and cancellation gates apply.

Each upload retains exclusive original bytes, an input receipt and a new U ID.
The existing async job captures execution provenance and rechecks input before
calling Core import_native_model. Producer lookup stays outside synchronous
admission: the first source run exposed three HTTP observation timeouts there.
Imported model identity and source hash must match the retained input. A prepared
import record receives its completion seal only after the last original check.
Failed or interrupted partial inputs remain visible as UNCONFIRMED, with no
completed model-selection action. No old input or experiment is overwritten.

The recent list reads bounded metadata and explicitly leaves original integrity
NOT_CHECKED. Selecting a model verifies original bytes, then existing native
inspection reads its current editable revision. These are distinct identities:
registering/editing the model later does not modify the preserved uploaded file.
Browser file and CAD selection snapshots prevent late replies attaching to a
different store/model. Model inputs are also locked while execution is busy.

Base64-in-JSON would expand payloads and defeat the established JSON bound.
Arbitrary server paths would bypass human file selection and containment.
Replacing native import would duplicate tested behavior. These alternatives
were rejected. The source unit includes synthetic transport/selection/partial
publication controls and independent review; actual browser→FreeCAD→registration
→new CAD revision→reopen is a separate acceptance on a fresh store.

FCStd upload is a human local entry point, not arbitrary structural FEA support.
The current fixture.calculix parent remains restricted to its declared CAD
family. General revision/body/group materials, loads, BC and contact are G2.
OpenScience remains the research control plane with approved5.6Sol/OAuth;
numerical engines and Domain/adapter boundaries remain. Company data must stay
outside this public repository. Physical qualification remains UNKNOWN and
release NOT_RELEASED.

Actual r01 correction: native UUID model references can begin with a digit. Transport reuses Lab REFERENCE, not Core study/experiment check_id; adapter UUID/path validation is unchanged. The failed clean378 import and unsealed partial bytes are retained; source correction does not claim actual r02 PASS.
