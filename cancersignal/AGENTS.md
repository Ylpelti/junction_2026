# Junction 2026 — Agent Instructions

## Project Context

We are a team of four building **CancerSignal**, a prototype during a 48-hour hackathon.

Our goal is to create a compelling, functional MVP that solves a real problem and can be demonstrated reliably to judges.

**Challenge:** AstraZeneca — Equitable and Effective Cancer Care in Finland.

**Solution:** AI-assisted clinical decision support to reduce delays in primary healthcare. The system uses RAG and LLMs to analyze longitudinal patient records, identify potentially overlooked cancer-related findings, and provide evidence with direct references to historical clinical events. Physicians review findings and determine further actions. A simulation explores potential improvements in patient flow and healthcare capacity.

**Intended tech stack:**
- Frontend: Next.js, React, TypeScript, Tailwind CSS
- Backend: Python, FastAPI, Pydantic
- Database: PostgreSQL + pgvector, Docker Compose
- AI: Verda/OpenAI-compatible LLM API, hybrid RAG, embeddings
- Optimization & simulation: OR-Tools, SimPy
- Data: Synthetic patient records only

Priorities:
1. Demonstrate the core value proposition.
2. Deliver a working end-to-end prototype.
3. Maintain a clear and intuitive user experience.
4. Keep the implementation simple and reliable.
5. Add extra features only when time permits.

## Development Principles

- Prefer simple, working solutions over complex designs.
- Prioritize speed without sacrificing correctness.
- Follow existing project conventions.
- Avoid unnecessary dependencies and abstractions.
- Do not overengineer for production-scale requirements.
- Reuse established libraries when appropriate.
- Keep changes focused on the assigned task.
- Avoid unrelated refactoring.

## Agent Workflow

Before implementing a substantial feature:
1. Inspect the relevant project files.
2. Understand existing architecture and interfaces.
3. Briefly outline the implementation approach.
4. Identify important assumptions or dependencies.

During implementation:
- Work autonomously within the assigned scope.
- Make reasonable implementation decisions.
- Keep changes incremental and focused.
- Preserve existing functionality.
- Follow agreed API contracts and data structures.
- Ask for clarification only when a decision materially affects the product or other workstreams.

After implementation:
1. Run relevant tests and build checks.
2. Fix errors introduced by the changes.
3. Review the resulting Git diff.
4. Summarize completed work and remaining issues.

Never claim that code has been tested unless the relevant checks were actually executed.

## Multi-Agent Collaboration

Multiple developers may use Claude Code and Codex simultaneously.

- Respect assigned tasks and file ownership.
- Use separate branches or worktrees for parallel work.
- Never overwrite another developer's changes.
- Do not modify shared APIs or schemas without coordination.
- Do not revert changes made by other developers.
- Do not push, merge, rebase, or force-push without explicit authorization.
- Keep changes easy to integrate.
- Report dependencies or blockers early.

## Testing and Reliability

- Prioritize the critical end-to-end user journey.
- Verify integrations between components.
- Run relevant tests, type checks, and builds.
- Add focused tests for important functionality.
- Use browser-based verification when available.
- Fix critical bugs before adding optional features.
- Clearly report any unverified functionality.

## Security

- Never commit secrets, API keys, or credentials.
- Use environment variables for sensitive information.
- Validate external inputs.
- Ask before performing destructive operations.
- Do not expose private data in logs or outputs.
- Use synthetic patient data only.

## Communication

- Be concise and technically precise.
- Focus on actionable results.
- Clearly distinguish completed work from plans.
- Explain significant architectural decisions.
- Surface problems rather than hiding them.
- Avoid unnecessary explanations of routine operations.

## Project Configuration

Frontend: Next.js + React + TypeScript

Backend: FastAPI + Python

Database: PostgreSQL + pgvector (Docker)

External services: Verda LLM API, optional OpenAI API

Deployment: TBD

Run each command below from `cancersignal/` (the directory containing this file).
Use separate terminals for the frontend and backend. Requires Node.js 22+ with npm
and Python 3.11+ with `venv` and pip. Backend commands use the macOS/Linux virtual
environment path; see `README.md` for Windows activation instructions.

| Operation | Frontend | Backend |
| --- | --- | --- |
| Install | `cd frontend && npm ci` | `cd backend && python3 -m venv .venv && .venv/bin/python -m pip install -r requirements.txt` |
| Development | `cd frontend && npm run dev` | `cd backend && .venv/bin/python -m uvicorn app.main:app --reload` |
| Check | `cd frontend && npm run typecheck` | With the backend running: `curl --fail http://localhost:8000/health` (expects `{"status":"ok"}`) |
| Build | `cd frontend && npm run build` | No build step; FastAPI runs directly from Python source. |
| Run after build | `cd frontend && npm start` | `cd backend && .venv/bin/python -m uvicorn app.main:app` |

Frontend: `http://localhost:3000`. Backend: `http://localhost:8000/health`;
interactive API documentation: `http://localhost:8000/docs`.

Automated tests are not configured yet. The commands above provide a frontend
type check and a backend smoke check. There is no root build script or monorepo
task runner. Database, Docker Compose, and external-service configurations are
not implemented in the current scaffold.

Core demo flow: Nurse enters clinical note → AI retrieves patient history → evidence-grounded findings with source references → physician review → optional healthcare pathway simulation.

Architecture constraints: FastAPI backend, modular components, synthetic patient data, traceable AI findings. No autonomous diagnosis or referral decisions.

## Git Workflow

We use a lightweight feature-branch workflow.

- Keep `main` stable and runnable.
- Never implement features directly on `main`.
- Create a separate branch for each feature or task.
- Use descriptive branch names, e.g. `feat/dashboard` or `fix/api-error`.
- Before starting new work, branch from the latest `main`.
- Commit small, logical changes with descriptive messages.
- Check `git status` and review changes before committing.
- Push feature branches and open pull requests when authorized.
- Never merge into `main` without human approval.
- Never force-push or overwrite teammates' work.
- Integrate completed features frequently to avoid large merge conflicts.

When a task is complete:
1. Run relevant tests and checks.
2. Review the changes.
3. Commit the implementation.
4. Push the feature branch when authorized.
5. Open a pull request for review when authorized.

If Git conflicts occur, explain the conflict and request guidance before making risky changes.
