# Backend TODO for the frontend demo

The nurse dashboard and physician queue in `frontend/` call the existing API v1
(see [contracts.md](contracts.md)). This page lists what the frontend still needs
from the backend. Owners are from the Pipeline and Ownership table in `AGENTS.md`.

**Status:** the frontend passes typecheck and build, and was tested in a browser
with prototype data and with mocked responses that follow the backend schemas.
The actual frontend API client and mappers have now been verified against running
FastAPI/PostgreSQL for patient/history reads, note saves, analysis responses and
CORS JSON POST preflights. A full browser walkthrough against the live backend
remains to be completed. Production build was verified with `npm run build -- --webpack`;
Turbopack's worker port was blocked in the verification environment.

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

1. ~~**No enabled rules in the seed**~~ **Done** (`feat/colorectal-rules`). `python -m app.db.seed` now also inserts the enabled colorectal rules SUO-01…SUO-10 ([rulebook-colorectal.md](rulebook-colorectal.md)). Lab-derived `anaemia` / `iron_deficiency_anaemia` / `fit_result` findings are computed in Python, so the seeded patients with low Hb can already trigger SUO-07 at age 60+.
2. ~~**Free-text notes are not read**~~ **Wired, needs configuration.** LLM note extraction (`app/extraction`) is connected through `app/services/llm_extraction.py` when `CANCERSIGNAL_EXTRACTION=llm`. Still to do:
   - set the Verda model ID and key;
   - record cached responses for the demo notes, so the demo works offline;
   - check live extraction quality on the demo patients.

   The default is still `off`.
3. ~~**No urgency level**~~ **Done.** `TriggerResponse.priority` is `"urgent" | "review"`, set by the rule (SUO-08 and SUO-09 are urgent). The frontend (`feat/frontend-priority`) shows a red urgent alert when any triggered rule is `urgent`, lists urgent findings first with an "Urgent" label, and treats a missing priority as `review`.
4. ~~**Demo patients missing**~~ **Done** (`feat/demo-patients-seed`). The demo patients are versioned in `backend/data/patients/demo_patients.json` and loaded with `python -m app.db.seed_demo`:
   - **Patients and expected alerts without LLM:** Laine (review), Nieminen (urgent), Korhonen (none) and Heikkinen (none). Each matches the eval case with the same history.
   - **Lab codes:** LOINC for Hb (718-7) and ferritin (2276-4). FIT uses the local code `F-HB-FIT`.

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

The [physician review handoff API](physician-review-api.md) persists submissions
and exposes the pending queue. The frontend uses it with backend data when
`USE_BACKEND_REVIEW_QUEUE` is on (`feat/frontend-review-requests`), and falls back
to browser state for prototype data or an unreachable backend.

- ~~Send an alert to the physician~~ **Done**, frontend connected:
  - "Send to physician" calls `POST /patients/{id}/review-requests` with the alert's analysis id.
  - 201 and 200 count as sent.
  - 404/409/422 show an error, and the alert stays unsent.
  - No referral draft is created.
- Dismiss an alert with one of four reasons, logged with user and time. *Still browser state only (`TODO(backend)`).*
- ~~Physician consultation queue~~ **Done**, frontend connected. `GET /review-requests` loads when the physician view opens and after a send. The backend order is kept.
- The physician's decision: order FIT / refer to specialist care / no action / acknowledge. *Still browser state only; shown as "not saved" for backend items (`TODO(backend)`).*
- Sent state is not restored after a page reload (could use `GET /review-requests?patient_id=…`).

## Other notes

- **CORS** defaults to `http://localhost:3000` and `http://127.0.0.1:3000`. Configure the JSON-array `CORS_ORIGINS` in `cancersignal/.env` for other frontend ports/URLs, then restart FastAPI. The frontend's backend URL is `NEXT_PUBLIC_API_URL`; see README for both settings.
- **Demo reset:** each Save creates a new note in the database, and the seed is insert-only. A way to reset demo data before a presentation would help.
- **Offline demo:** `AGENTS.md` asks for cached LLM responses for the demo patients, so the demo works without network.
