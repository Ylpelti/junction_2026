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
2. **Free-text notes are not read** (owner: Coder, `extract.py`). The `structured-source-demo-v1` extractor only copies coded symptom and lab records, so the nurse's note text can never trigger a rule. Needs LLM extraction into the shared vocabulary in `app/reasoning/vocabulary.py` (`rectal_bleeding`, `change_in_bowel_habit`, `abdominal_pain`, `weight_loss`, `abdominal_mass`, `rectal_mass`), with verbatim quotes and explicit negation.
3. ~~**No urgency level**~~ **Done.** `TriggerResponse.priority` is `"urgent" | "review"`, set by the rule (SUO-08 and SUO-09 are urgent). The frontend (`feat/frontend-priority`) shows a red urgent alert when any triggered rule is `urgent`, lists urgent findings first with an "Urgent" label, and treats a missing priority as `review`.
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

- **CORS** defaults to `http://localhost:3000` and `http://127.0.0.1:3000`. Configure the JSON-array `CORS_ORIGINS` in `cancersignal/.env` for other frontend ports/URLs, then restart FastAPI. The frontend's backend URL is `NEXT_PUBLIC_API_URL`; see README for both settings.
- **Demo reset:** each Save creates a new note in the database, and the seed is insert-only. A way to reset demo data before a presentation would help.
- **Offline demo:** `AGENTS.md` asks for cached LLM responses for the demo patients, so the demo works without network.
