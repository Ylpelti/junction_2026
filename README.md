# CancerSignal

**Helping nurses connect overlooked colorectal cancer signals across patient history.**

Built for **Junction 2026 · AstraZeneca’s Equitable and Effective Cancer Care in Finland challenge**.

CancerSignal brings clinical notes, laboratory results, and earlier encounters into one review workflow. It surfaces source-backed findings, applies deterministic colorectal rules, and helps nurses hand relevant findings to a physician with the supporting evidence intact.

**Synthetic-data prototype.** CancerSignal does not diagnose cancer or make autonomous referral decisions. Healthcare professionals decide on investigations and referrals.

## The workflow

1. **Review a patient’s history.** Open the nurse dashboard to inspect earlier notes, encounters, and laboratory results.
2. **Save a note and run analysis.** The backend retrieves eligible history for that patient and evaluates structured findings, with optional LLM extraction from clinical prose.
3. **Inspect the evidence.** Review triggered rules, source references, missing information, and a Finnish explanation. QCancer predictions appear separately from rule-based alerts.
4. **Request physician review.** Send the saved analysis to the physician queue for human review.

The default demo needs no external AI API key. Its extractor uses structured observations; understanding arbitrary free-text notes requires the optional LLM configuration.

## What powers it

| Component | Purpose |
| --- | --- |
| Next.js, React, TypeScript, Tailwind CSS | Nurse dashboard and physician review interface |
| FastAPI and Pydantic | Patient, observation, analysis, and review APIs |
| PostgreSQL 16, pgvector, SQLAlchemy, Alembic | Persistent records, evidence, retrieval, and migrations |
| Patient-specific retrieval | Complete history or lexical search by default; optional local hybrid retrieval |
| Python clinical rules | SUO-01–SUO-10 colorectal review signals and derived laboratory findings |
| Optional LLM extraction | Structured, source-backed facts with evidence validation |
| Finnish explanation engine | Deterministic summaries by default; optional LLM wording |
| QCancer-2013 | Separate numerical predictions that preserve unknown inputs |

History is scoped to one patient and must precede the current note in both observation and recording time. Numerical laboratory history is fetched independently of narrative search limits. LLM output does not determine urgency or calculate risk.

## Run locally

You need **Node.js 22+**, **Python 3.11+**, and **Docker with Compose**.

From the repository root, prepare the database:

```sh
cd cancersignal
# Preserve an existing local configuration.
[ -f .env ] || cp .env.example .env
# Edit .env and choose POSTGRES_PASSWORD before continuing.
docker compose up -d --wait db
```

Start the backend in the same terminal:

```sh
cd backend
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
python -m app.db.check
python -m alembic upgrade head
python -m app.db.seed
python -m uvicorn app.main:app --reload
```

In a second terminal, from the repository root:

```sh
cd cancersignal/frontend
npm ci
npm run dev
```

| Service | URL |
| --- | --- |
| Application | http://localhost:3000 |
| Interactive API documentation | http://localhost:8000/docs |
| Liveness check | http://localhost:8000/health |

See the [application guide](cancersignal/README.md) for configuration, checks, optional AI features, and troubleshooting.

## Repository map

```text
cancersignal/                 Main application
├── frontend/                Nurse dashboard and physician queue
├── backend/
│   ├── app/api/              HTTP endpoints
│   ├── app/db/               Database setup and synthetic fixtures
│   ├── app/contracts/        Shared pipeline contracts and evidence validation
│   ├── app/rag/              Retrieval and indexing
│   ├── app/extraction/       Structured clinical extraction
│   ├── app/reasoning/        Deterministic rules and laboratory findings
│   ├── app/risk_models/      QCancer implementation and license
│   ├── app/explanation/      Finnish explanation generation
│   ├── app/services/         Pipeline orchestration and persistence
│   ├── alembic/              Schema migrations
│   └── tests/               Unit, API, and integration tests
└── docs/                    Architecture and integration documentation
```

## Development and documentation

From `cancersignal/backend/`, with the virtual environment activated:

```sh
python -m pytest
```

From `cancersignal/frontend/`:

```sh
npm run typecheck
npm run build
```

Database integration tests require explicit opt-in; see the [application guide](cancersignal/README.md#development-checks).

- [API contracts](cancersignal/docs/contracts.md)
- [Data model](cancersignal/docs/data-model.md)
- [Colorectal rulebook](cancersignal/docs/rulebook-colorectal.md)
- [Retrieval integration](cancersignal/docs/rag-analysis-integration.md)
- [Risk models and limitations](cancersignal/docs/risk-models.md)
- [Physician review API](cancersignal/docs/physician-review-api.md)
- [Contribution and engineering guidance](cancersignal/AGENTS.md)

## Prototype boundaries

Use synthetic patient data only. Authentication and EHR integration are not implemented. Review requests, dismissal reasons, and physician decisions persist through the API. Clinical actions use demo actors and simulate workflow decisions; they do not book investigations or issue real referrals.

QCancer is not calibrated for Finland and uses a synthetic Townsend value of zero. Missing required inputs produce `insufficient_data`; numerical predictions never change rule-based review alerts. “No signals identified” does not mean “no cancer,” and failed or incomplete analyses provide no clinical conclusion.

The bundled QCancer implementation carries [AGPL-3.0 licensing](cancersignal/backend/app/risk_models/AGPL-3.0.txt); consult its [model documentation](cancersignal/docs/risk-models.md) before reuse.
