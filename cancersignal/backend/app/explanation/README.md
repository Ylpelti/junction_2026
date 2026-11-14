# Independent Finnish clinical explanation

Consumes the existing shared `app.contracts.analysis.AnalysisResult`. It does not
retrieve records, run risk models, calculate features, evaluate rules, write to
the database, or register endpoints. No RAG, extraction, mathematical-model,
frontend, benchmark or shared-contract files are changed.

## Run offline

From `cancersignal/backend/`, using the existing Python 3.11+ environment:

```sh
.venv/bin/python -m pip install -e '.[dev,llm]'
.venv/bin/python -m app.explanation \
  --example app/explanation/examples/mock_analysis.json
.venv/bin/python -m app.explanation \
  --example app/explanation/examples/missing_data.json
.venv/bin/python -m app.explanation --api-v1 \
  --example app/explanation/examples/api_response.json
.venv/bin/python -m app.explanation --api-v1 \
  --example app/explanation/examples/qcancer_api_response.json
.venv/bin/python -m pytest tests/explanation -q
```

The fixtures are explicitly synthetic. The first contains a hand-authored
`ModelPrediction` payload representing an **unfinished model mock**, not an
implemented model, cancer probability, or validated score. The missing-data
example demonstrates unavailable features and an indeterminate rule. No model,
PostgreSQL server or network is needed for offline execution or unit tests.

## Python integration

```python
from app.explanation import ExplanationEngine
from app.explanation.providers import ChatProvider, ProviderSettings

# No provider: deterministic Finnish fallback; no network access.
explanation = ExplanationEngine()(validated_analysis_result)

# Configured provider, but live calls remain disabled by default.
provider = ChatProvider(ProviderSettings(_env_file=".env.explanation"))
engine = ExplanationEngine(provider)
explanation = engine(validated_analysis_result)
```

Keep the original analysis alongside `ExplanationResult`: every statement points
back to its original finding/feature/rule, prediction index, and observation IDs.
`input_digest` binds the output to the complete input snapshot. Output fields are
`summary_fi`, `findings`, `mathematical_outputs`, `rule_results`, `limitations`,
provenance and explicit issues. `mode` is `llm`, `fallback` or `unavailable`.

Input is revalidated, including mutable legacy prediction records. Invalid
patient/time/evidence graphs raise a sanitized `ExplanationInputError`; they do
not receive a seemingly valid fallback. Pending/running/failed analyses and
inputs with no explainable structured facts return `unavailable` with no clinical
statements and no provider call. Provider failures,
timeouts, malformed JSON, altered numbers or invented references return a valid
deterministic Finnish fallback with the specific issue code and attempted-provider
identity. No provider error body or source text is included in error reports.

## Why the LLM returns a plan

Free prose cannot reliably be checked for changed units, numerical words, implied
probabilities, diagnoses or referral advice. Instead, the LLM selects/orders
**approved fact keys**, echoes their exact quantities/evidence IDs, and chooses a
Finnish summary style. Python renders the clinical statements from the existing
states and values. The strict Pydantic plan accepts no free-text clinical claims.
No number from an LLM is rendered: even a valid echo is replaced by the original
input value. Finnish decimal punctuation is formatting only; no rounding, unit
conversion, risk calculation, new threshold or numerical inference occurs.

References must match the selected fact's exact evidence set, not merely exist
somewhere in the analysis. Guideline references are copied only from the existing
rule metadata. Matched/indeterminate rules, review flags, supporting findings,
all mathematical outputs, and negative/resolved/uncertain findings cannot be
omitted. Selecting one finding in a same-type group requires all its states;
contradictions are preserved rather than reconciled. All limitations are rendered
independently of the LLM plan. Unknown clinical labels receive a generic Finnish
description and explicit limitation, not a guessed translation.

Raw notes, finding descriptions, free-text uncertainty and generic model payloads
are not sent to the LLM or copied into generated clinical prose. The prompt uses
only the approved fact catalog; even these fields are treated as untrusted data.
Exact evidence integrity is not proof of clinical entailment. Output explicitly
records `calculation_correctness=not_assessed` and `clinical_validity=not_assessed`.
This layer checks fidelity to supplied outputs, not whether a risk model's
arithmetic, clinical usefulness, calibration or assumptions are correct.

## Future mathematical/risk-model integration

Existing computed values belong in `AnalysisResult.computed_features` using
`ComputedFeature`: status, finite Decimal value, unit, calculation method,
provenance, evidence and coverage. The explanation engine does not invent these
fields or compute their values. An unavailable feature stays unavailable.

`ModelPrediction.value` is generic JSON: it has no universal scale, units,
calibration or clinical-validation fields. By default, unknown predictions are described
as unverified model outputs and **their numbers are omitted**. A replaceable
display mapping can expose a supplied scalar and unit only after agreement on
the actual producer's payload:

```python
from app.explanation.schemas import PredictionDisplaySpec

# This identity and payload exist ONLY in our synthetic example.
spec = PredictionDisplaySpec(
    model_name="SYNTHETIC unfinished-model mock", model_version="mock-v1",
    prediction_type="synthetic_index",
    value_path=("estimate",), unit_path=("unit",),
)
engine = ExplanationEngine(provider=None, prediction_specs=(spec,))
```

Paths address dictionary keys inside `ModelPrediction.value`; no expressions or
model code execute. Identity/version/type must match exactly, the value must be
finite, the unit must have a bounded supported format, and original evidence IDs
must be present. Invalid or unmapped numbers are omitted with a limitation.
Predictions remain separate from documented clinical findings, even with a mapping.
No percent conversion or risk category is inferred. Typed uncertainty intervals,
stable prediction IDs and explicit model validation/scale metadata would improve
the future shared contract; this task proposes them without modifying it.

### Published QCancer output

The latest main provides QCancer predictions. `prediction_views.py` recognizes
only the published identity `QCancer-2013` / `QCancer-2013-open-source` /
`current_undiagnosed_cancer_risk`. It copies the supplied
`colorectal_cancer_risk_percent`, `any_cancer_risk_percent` and `horizon_years`
fields only when the source says `calculated` and the display fields/references
are valid. Percentage fields already contain percentages: there is no scaling,
rounding, site-risk summation, new cutoff, risk category or urgency calculation.

`insufficient_data`, `invalid_input` and `unsupported_input` produce explicit
Finnish explanations with no risk values. Unknown versions retain the generic
unmapped-prediction behavior. QCancer remains separate from the rule results and
never changes their outcome, priority or review flags. The explanation preserves
the limitation that this prototype's QCancer output is not clinically validated
or calibrated for Finland. The original `source_notice` is copied verbatim into
the prediction statement's metadata and excluded from the LLM prompt. A missing
notice is explicit rather than replaced with invented text. Retain the full
original prediction alongside the explanation. No risk-calculator implementation
is imported and its bundled license is unchanged.

The QCancer API fixture has hand-authored numbers solely for wire-format tests;
they are not calculator results or clinical-performance measurements.

## Current API v1 adapter

The engine now also accepts the existing public `AnalysisResponse`, either as its
Pydantic DTO or decoded JSON. The adapter lives entirely in `app/explanation`:

```python
from app.explanation import ExplanationEngine

engine = ExplanationEngine()  # Or explicitly supply a configured provider.
explanation = engine.explain_api(api_response)
# Optional: hydrate the original note with data fetched by the caller.
explanation = engine.explain_api(api_response, input_note=original_note)
```

The result has `input_format="api_v1"`. Patient/analysis ownership, original
source IDs, quotes, offsets, date cutoffs, rule references and snapshot consistency
are checked. A missing cutoff is rejected; execution time is never substituted
for the note's event time. If the original note is not a cited source, the adapter
can explain the supplied structured results with an explicit missing-note
limitation. Supplying that note must match its saved UUID, patient and event time.
The adapter does not query PostgreSQL or fetch any external records.

API v1 does **not** expose per-finding producer versions, separate computed
feature records, or causal rule-to-finding IDs. It now exposes predictions in
`predictions` and persisted copies in `provenance.predictions`; when both are
provided they must agree. The adapter supports earlier responses without these
additive fields too. Prediction patient/time/evidence boundaries are validated
with the shared contract. The adapter labels missing metadata; it does not invent
fields, parse numbers out of descriptions, or infer
causal relationships from shared observation IDs. Measurement values can be copied
from the supplied original records. All API findings and rule results are kept
in the plan; `rule_results[].finding_ids` remains empty because that relationship
is unavailable. Original rule evidence IDs, guideline references and review flags
are retained. `uncertain` maps conservatively to uncertain polarity/unknown timing
because API v1 cannot encode the two states independently.

Its internal deterministic projection describes a representation change, not the
original clinical producer or a newly calculated result. No urgency is computed
or overwritten. The full original response binds the output/cache digest, and
the original `AnalysisResponse` is not mutated. This is a callable integration
boundary: existing routes do not automatically call the engine or make new LLM
requests. Future mathematical outputs should use the rich `AnalysisResult` path
instead of trying to reconstruct absent fields from API v1.

`tests/explanation/test_api_adapter.py` is entirely offline. The optional
`test_api_integration.py` verifies an actual saved API analysis can be explained
without changing its readback; it uses the existing disposable PostgreSQL fixture:

```sh
CANCERSIGNAL_EXTRACTION=off RUN_DATABASE_TESTS=1 \
  .venv/bin/python -m pytest tests/explanation -q
```

## Providers and optional cache

Copy `app/explanation/examples/.env.example` to the ignored
`backend/.env.explanation`. Set `EXPLANATION_PROVIDER=verda|openai`,
`EXPLANATION_MODEL` and `EXPLANATION_API_KEY`; no model/key is hardcoded. An
explicit `--env-file` loads it; exported variables take precedence. Extraction
settings and its API key are not read automatically.

Optional variables: `EXPLANATION_BASE_URL` (HTTPS `/v1` base),
`EXPLANATION_RESPONSE_FORMAT=json_schema|json_object`,
`EXPLANATION_REASONING_EFFORT`, `EXPLANATION_MAX_OUTPUT_TOKENS` (4096),
`EXPLANATION_MAX_INPUT_BYTES` (60000), `EXPLANATION_MAX_RESPONSE_BYTES` (1000000),
and `EXPLANATION_TIMEOUT_SECONDS` (55). OpenAI uses `max_completion_tokens` and
`store=false`; Verda uses `max_tokens`. Unsupported parameters fail explicitly,
without automatic removal, model switching, output repair or paid retries.

Only after explicit authorization for a live invocation:

```sh
.venv/bin/python -m app.explanation \
  --example app/explanation/examples/mock_analysis.json \
  --env-file .env.explanation --live --allow-live \
  --cache-dir .venv/explanation-cache
```

Python live use likewise requires `ChatProvider(settings, allow_live=True)`.
Tests use deterministic mock plans/`httpx.MockTransport`, never real APIs. No
live provider compatibility or Finnish model quality is established by those tests.

Optional caching stores only validated plans, keyed by exact input, prompt,
catalog and nonsecret provider configuration. Every read revalidates references
and numbers. Tampering produces an explicit fallback, not a network retry.
Cache files are atomically written with owner-only access. Use an ignored local
directory and synthetic data only; no patient response cache is committed.
