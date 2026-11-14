# CancerSignal — Agent Instructions

## Project context

**Project:** CancerSignal — AstraZeneca Cancer Care Challenge, Junction 2026.

**Problem:** Potential cancer patients can experience delays in primary healthcare.
Relevant risk signals may be scattered across previous medical records,
laboratory results, and nurses' notes.

**Solution:** An AI-assisted tool for nurses and healthcare professionals. When a
nurse writes a new clinical note, the system retrieves relevant historical patient
information using patient-specific RAG and analyzes possible cancer-related risk
signals.

The system highlights relevant findings with references to original records,
allowing a physician to review the case and potentially initiate an accelerated
diagnostic referral.

## Planned components

- Nurse dashboard for clinical notes and patient history.
- Backend for patient data retrieval, AI analysis, and clinical triggers.
- Synthetic patient data and optional ML experimentation.
- Before-and-after simulation showing potential improvements in healthcare waiting times.

## Technical direction

- Frontend: Next.js, TypeScript.
- Backend: Python, FastAPI.
- AI: LLM + patient-specific RAG + structured clinical data.
- ML: scikit-learn / PyTorch if useful; do not install until needed.
- Simulation: Python.
- Database, LLM provider, and deployment: not selected yet.

## Important principles

- This is a hackathon prototype, not a production clinical application.
- Use synthetic patient data only.
- AI supports healthcare professionals; it does not autonomously diagnose cancer
  or make referral decisions.
- Keep components modular for parallel development.
- Avoid unnecessary complexity and dependencies.
- Do not present simulated outcomes as clinically validated results.
- Keep secrets in local environment variables; never commit credentials.
- Coordinate changes to shared API contracts and data schemas.
- Follow the repository's parent instructions for branches, review, and collaboration.

## Team structure

1. Frontend — dashboard and user experience (`frontend/`).
2. Backend & AI — API, RAG, risk-signal detection (`backend/`).
3. Data & Simulation — synthetic data, model evaluation, process simulation (`data/`).

Use `docs/` for shared design decisions and API documentation as these are agreed.

## Current scope and commands

Only the framework scaffold is implemented. Do not infer that any planned clinical,
AI, data, or simulation features exist. See `README.md` for local setup.

- Frontend install: `cd frontend && npm ci`
- Frontend development: `npm run dev`
- Frontend checks: `npm run typecheck` and `npm run build`
- Backend setup: `cd backend`, create and activate `.venv`, then
  `python -m pip install -r requirements.txt`
- Backend development: `python -m uvicorn app.main:app --reload`
- Backend smoke check: `curl --fail http://localhost:8000/health`
- Automated feature tests: not configured yet.
