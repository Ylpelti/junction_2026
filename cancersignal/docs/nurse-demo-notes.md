# Editable nurse demo notes

Implemented on `infra/render-vercel-demo`. Examples are input text only in
`frontend/data/demo-notes.json`; they never supply findings or rule outcomes.
They derive from `backend/app/db/demo_data/patients.en-v2.json`.

- Laine: ongoing bowel habit change, abdominal symptoms and fatigue; intended
  physician-review scenario alongside the existing haemoglobin history.
- Nieminen: continuing loose stools and abdominal pain; prior colonoscopy
  completion remains uncertain, not declared completed or definitely missed.
- Heikkinen: shoulder complaint with explicit 2022 resolved gastrointestinal
  symptoms and completed colonoscopy; historical symptoms must not become
  current positives.
- Korhonen: incomplete current symptom assessment after the vaccination visit;
  intended indeterminate scenario, not a claim that symptoms are absent.

These are intended scenarios, not verified live outcomes. The deployed endpoint
was not available during this change; no fresh deployed inference, evidence audit,
or live physician handoff was performed. No clinical rules, extraction behavior,
thresholds, or risk mathematics changed.

Selecting a patient does not submit anything. Save note uses the existing
observation-save and saved-note analysis requests when CancerSignal is enabled.
The current-practice toggle still saves text only. Existing result, evidence,
recommendation and physician-handoff components consume the backend response.

Drafts (including deliberately empty drafts) survive patient changes and reloads
in the same browser tab using session storage. Pending submissions retain their
original text and reconciliation workflow. Successfully saved notes remain in
backend history; the editor clears without re-inserting the example. Refreshing
the demo no longer discards user drafts. Closing the tab ends draft persistence.

Validation: frontend typecheck passed; all 26 frontend tests passed using the
installed Chromium-based Brave executable (mock API browser tests, not LLM
validation). The production webpack build passed with a local test API origin;
that local build artifact is not intended for deployment. Hosting must rebuild
using the existing project's configured backend origin.
