# Backend TODO for the frontend demo

The nurse dashboard and physician queue in `frontend/` call the existing API v1
(see [contracts.md](contracts.md)). This page lists what the frontend still needs
from the backend. Owners are from the Pipeline and Ownership table in `AGENTS.md`.

**Status:** the frontend passes typecheck and build, and was tested in a browser
with prototype data and with mocked responses that follow the backend schemas.
**It has not been run against a running backend yet.**

## Where the frontend touches the backend

| File | Purpose |
| --- | --- |
| `frontend/lib/api.ts` | One function per endpoint. Base URL is `NEXT_PUBLIC_API_URL` (default `http://localhost:8000`). |
| `frontend/lib/mappers.ts` | The only file that knows backend field names. Change this file if the API changes. |
| `frontend/lib/flags.ts` | Flags for the fallbacks used where the backend has gaps. Each use is marked `TODO(backend)`. |

Endpoints used:
- `GET /api/v1/patients`
- `GET /api/v1/patients/{id}/observations`
- `POST /api/v1/patients/{id}/analyses`, with `{"note": ObservationCreate}`. `observed_at` and `recorded_at` are the save time (time *t*).
- `POST /api/v1/patients/{id}/observations`, used when "Current practice" is selected and no analysis runs.

How the frontend reads an analysis:
- **Run status:** `failed`, `pending` or `running` is shown as "CancerSignal unavailable".
- **No alert:** a `completed` run with no triggered rule shows no alert.
- **Alert:** at least one triggered rule shows a yellow "physician review" alert.
- **Findings:** each triggered `TriggerResponse` becomes one finding card.
- **Source chips:** resolved through `source_observations`. A reference that cannot be resolved is hidden and listed under "Not found in records".

## Blocking for the demo

These must be done before the real backend can show any alert.

1. **No enabled rules in the seed** (owner: Mathematician). `app/db/seed.py` creates no `trigger_rules`, so every analysis ends with "no signals identified". The demo needs sourced rules (`lahde`, `lahde_kohta`) for the colorectal criteria.
2. **Free-text notes are not read** (owner: Coder, `extract.py`). The `structured-source-demo-v1` extractor only copies coded symptom and lab records, so the nurse's note text can never trigger a rule. Needs LLM extraction with a fixed JSON schema, verbatim quotes and explicit negation.
3. **No urgency level** (owner: Mathematician + Coder, needs a contract change). `TriggerResponse` has no priority or severity, so the frontend can only show yellow (`review`). A red `urgent` alert needs a field such as `priority: "urgent" | "review"` that comes from the rule, not the LLM.
4. **Demo patients missing** (owner: Niklas + Mathematician). The prototype patients should be seed data with ground-truth labels, named `SYNTHETIC …` because the API requires that prefix. They are Korhonen (none), Laine (review), Nieminen (urgent) and Heikkinen (none, already investigated).

## Missing data fields

The UI shows these from local fallback data or leaves them empty.

| Needed in UI | Today | Suggested addition |
| --- | --- | --- |
| Lab reference range and L/H flag | Not stored; shown as "—". The frontend must not compute it (Product Rule 8). | `reference_low`, `reference_high`, `abnormal_flag` on lab observations, computed in Python |
| Note author role (nurse/physician) | Notes show only "NOTE" | Author role on `clinical_note` or encounter |
| Appointment time and reason for visit | Taken from `FALLBACK_APPOINTMENTS` in list order | Appointment/encounter data for "today" |
| Referrals and test requests | `investigation` observations are shown instead | Referral type with status (open / result not acknowledged / closed) |
| Human-readable record IDs | UUID prefix shown, e.g. `LAB-22222222` | Optional display reference, e.g. `NOTE-0905` |

## Missing endpoints

These run only in browser state (`USE_LOCAL_WORKFLOW`) and are lost on reload.

- Send an alert to the physician, with the evidence and a referral draft.
- Dismiss an alert with one of four reasons, logged with user and time.
- The physician consultation queue, sorted urgent → review → routine, then by time received.
- The physician's decision: order FIT / refer to specialist care / no action / acknowledge.

## Other notes

- **CORS** allows only `http://localhost:3000` and `http://127.0.0.1:3000`. Run the frontend on port 3000, or add the other origin.
- **Demo reset:** each Save creates a new note in the database, and the seed is insert-only. A way to reset demo data before a presentation would help.
- **Offline demo:** `AGENTS.md` asks for cached LLM responses for the demo patients, so the demo works without network.
