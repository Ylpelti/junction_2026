# CancerSignal

AstraZeneca Cancer Care Challenge · Junction 2026

CancerSignal is a planned AI-assisted tool for nurses and healthcare professionals.
It will combine new clinical notes with relevant patient history through
patient-specific retrieval-augmented generation (RAG), highlighting possible
cancer-related risk signals with references to original records for physician review.

This repository currently contains **only a framework scaffold**: a Next.js
placeholder page and a FastAPI health endpoint. Patient workflows, AI/RAG,
datasets, ML, and simulations are not implemented.

## Structure

```text
cancersignal/
├── AGENTS.md       # Project context and development principles
├── README.md
├── .gitignore
├── frontend/       # Next.js App Router + TypeScript
├── backend/        # FastAPI + Python
├── data/           # Reserved for synthetic data and simulation work
└── docs/           # Reserved for shared documentation
```

The frontend and backend run independently in two terminals. No database,
external service, API key, or environment file is required for this scaffold.

## Prerequisites

- Node.js 22 LTS or newer and npm.
- Python 3.11 or newer with `venv` and pip.

Run the commands below from `cancersignal/` inside the repository.

## Frontend

```sh
cd frontend
npm ci
npm run dev
```

Open <http://localhost:3000>. Edit `frontend/app/page.tsx` to begin development.

Checks and production build (from `frontend/`):

```sh
npm run typecheck
npm run build
npm start
```

`npm start` serves the completed production build on port 3000. Stop the development
server before starting it on the same port. No automated feature tests are configured yet.

## Backend

In a second terminal:

```sh
cd backend
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m uvicorn app.main:app --reload
```

On Windows, use `py -m venv .venv` and activate with
`.venv\Scripts\Activate.ps1` in PowerShell instead.

- API: <http://localhost:8000>
- Interactive API documentation: <http://localhost:8000/docs>
- Health check: <http://localhost:8000/health>

Verify the running backend:

```sh
curl --fail http://localhost:8000/health
```

Expected response: `{"status":"ok"}`. The API root has no route yet; use `/docs`
or `/health`. Edit `backend/app/main.py` to begin development. The frontend does
not call the backend yet; integration will be added with the first feature.

## Planned work and ownership

1. **Frontend:** nurse dashboard, clinical notes, patient history, user experience.
2. **Backend & AI:** retrieval, LLM analysis, structured clinical data, risk signals.
3. **Data & Simulation:** synthetic datasets, optional scikit-learn/PyTorch
   experiments, evaluation, and before-and-after waiting-time simulations.

Agree shared API contracts and data schemas before implementing integrations.
Keep runtime dependencies local to each component; no monorepo task runner is needed.

## Prototype boundaries

Use **synthetic patient data only**. This is a hackathon prototype, not a production
clinical application. AI supports healthcare professionals and does not autonomously
diagnose cancer or make referral decisions. A physician reviews findings and any
referral. Simulated outcomes must not be presented as clinically validated results.

See [AGENTS.md](AGENTS.md) for the full project context and development principles.

Framework references: [Next.js setup](https://nextjs.org/docs/app/getting-started/installation)
and [FastAPI first steps](https://fastapi.tiangolo.com/tutorial/first-steps/).
