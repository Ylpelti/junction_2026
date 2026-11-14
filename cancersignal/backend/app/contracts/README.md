# Shared pipeline contracts — version 1.0

Internal handoff schemas, not database entities or new HTTP endpoints. Source
snapshots reuse `schemas.records.ObservationRead`; existing IDs, text, values,
units, timestamps and enums remain authoritative. No dependencies, database
columns, LLM calls, feature calculations, or trigger algorithms are added here.

## Component handoffs

| Component | Input | Output |
| --- | --- | --- |
| Retrieval | `PatientScope`, query | `clinical_context.RetrievedContext` |
| Structured access | Scope, optional code filter | `clinical_context.StructuredPatientContext` |
| Extraction | Retrieved context, optional explicit input note | `stages.FindingBatch` containing `ClinicalFinding[]` |
| Mathematics | Relevant numerical history | `stages.FeatureBatch` containing `ComputedFeature[]` |
| Rules | Scope, findings, features, existing `TriggerRuleRead[]` | `analysis.TriggerEvaluation[]` |
| Result assembly | Validated outputs and original sources | `analysis.AnalysisResult` |

Callable Protocols are in `interfaces.py`; implementations bind their repository
or provider dependencies. No FastAPI or SQLAlchemy session is required by these
interfaces. `ObservationResolver` optionally supplies missing sources by patient
and requested UUIDs; returned sources are still checked for ownership/time scope.

```python
from app.contracts.validation import merge_source_contexts, validate_finding, validate_feature

rag = retrieve_context(scope=scope, query=query)
numeric = load_structured_context(scope=scope, codes=None)
sources = merge_source_contexts(rag, numeric, input_note=note)
finding_batch = extract_findings(rag, input_note=note)
feature_batch = compute_features(numeric)
# Propagate batch status/issues/missing information; failed is not an empty success.
findings, features = finding_batch.findings, feature_batch.features
for finding in findings:
    validate_finding(finding, sources, scope=scope, input_note_id=note.id)
for feature in features:
    validate_feature(feature, sources, scope=scope, reproduce=algorithm_verifier)
# The independent rule component consumes these validated outputs.
# Construct AnalysisResult to check the complete reference graph.
```

These functions are integration signatures supplied by independent developers;
the example does not introduce another production pipeline.

## Significant decisions

- **Independent numerical history:** RAG hits and structured measurements are
  separate contexts. `Coverage` declares complete/partial/unknown history, eligible
  counts, and missing-data reasons. Complete contexts require exact counts.
  Completeness is a producer attestation for the declared time window/code filter,
  not proof an underlying repository query was exhaustive. Numerical algorithms
  must not treat semantic top-k results as complete baseline/trend data.
- **Explicit temporal scope:** `as_of` is an exclusive event-time cutoff;
  `recorded_before` is an exclusive knowledge cutoff, defaulting to and never later
  than `as_of`. `observed_since` is optional/inclusive. The current note is explicit
  input, not its own historical hit. Source snapshots, nested references and source
  tuples are immutable. Merging checks patient/cutoff consistency and rejects
  conflicting copies of one UUID. A canonical SHA-256 digest records the source
  snapshot for reproducibility.
- **Polarity separate from time:** present/absent/uncertain and
  current/historical/resolved/unknown are independent. Absence is not resolution.
  Uncertain/unknown states need reasons. Contradictory findings retain multiple
  source quotes; missing information is a typed message, not a negative fact.
- **Calculations separate from interpretation:** finite `Decimal` values serialize
  as decimal strings. Features record original input units, output units, method,
  version, source IDs, reference window and input coverage. Mixed units require an
  explicit conversion method; no conversion runs in this package. Unavailable
  features have no value and explain why. Partial/unknown feature coverage cannot
  support a matched trigger, even if an estimate has been calculated.
- **Three-state triggers:** matched/not_matched/indeterminate are distinct. Missing
  or uncertain inputs do not automatically become false. Indeterminate outcomes
  require reasons; matched outcomes require clinician review and usable supporting
  findings/features. Rule UUID/version must match metadata, and supporting source
  IDs must completely cover cited dependencies. These are integrity constraints,
  not a new implementation of rule expressions or clinical applicability.
- **Stage failures are data too:** `FindingBatch` and `FeatureBatch` carry scope,
  provenance, complete/partial/failed state, missing information and issues, even
  when there are no output records. A failed stage needs an error and cannot emit
  findings/features; partial output needs an explanation. Consumers must propagate
  that state before evaluating rules, not interpret an empty failure as “not matched.”
- **Provenance and evaluation:** component/method/version, optional LLM provider,
  model, prompt/configuration identifiers, rule sources/versions and optional
  dataset/version/split/A-B-C mode are explicit. Ground-truth labels stay outside
  model outputs to avoid leakage. Fixtures are neither clinical validation nor
  held-out evaluation labels.
- **ML remains separate:** the existing `ModelPrediction` type lives in
  `predictions.py` and remains available at its original import path. Predictions
  cannot become documented findings or support rules automatically. No model,
  prediction persistence, inference, or training is implemented.

## What validation proves

`validate_evidence`, `validate_finding`, `validate_feature`, and automatic
`AnalysisResult` validation check source existence, patient/time scope, exact quotes,
Unicode `[start,end)` offsets, units, and rule/finding/feature reference closure.
Missing/invalid sources raise `EvidenceValidationError` with a stable `code`.
Analysis does not modify source observations.

A `ValidationReport` proves **reference integrity only**. `clinical_support` is
explicitly `not_assessed`; a real quote does not prove its interpretation is
medically supported. Serialized results declare `reference_integrity_only` too.
Claim/negation/entailment assessment belongs to the producer, reconciliation and
evaluation components; parsing must not be presented as clinical verification.

Likewise, valid inputs and algorithm metadata do not prove the calculated value.
`calculation_reproduced` is false until a supplied deterministic verifier returns
the same finite `Decimal`. Call that verifier before releasing calculations to the
rule component and retain its report with audit/evaluation artifacts. No numerical
algorithms or medical thresholds are invented by these contracts.

## Compatibility

Evidence and finding-content primitives are reused by the existing
`schemas.analysis.StructuredFinding`; old import paths and wire fields remain
valid. Existing API evidence checks use the shared validator and retain their
error codes. The richer contracts are not silently written into old single-status
or boolean columns, and they do not change API v1 responses.

`adapters.py` provides explicit legacy content/status projections. It refuses
unrepresentable polarity/time pairs, missing-information loss, indeterminate-to-
boolean conversion, and feature-backed evaluations whose links would disappear.
Keep the rich finding ID/provenance object for audit; a content projection is not
a full roundtrip. Legacy context conversion declares unknown coverage. Connecting
rich outputs to persistence/API responses needs a separately coordinated versioned
mapping; there is no migration or full pipeline rewrite in this task.

## Fixtures and checks

`tests/fixtures/pipeline_contracts/` contains five explicitly synthetic JSON input
and output examples: longitudinal symptoms/labs, negated versus resolved symptoms,
completed historical investigation, contradictory/incomplete evidence, and no
matching trigger. Each has separate RAG/numerical contexts and an example result.
Outcomes are manually authored illustrations, not diagnoses or clinical thresholds.

From `backend/` with the environment active:

```sh
python -m pytest tests/test_pipeline_contracts.py
# Optional regression tests with PostgreSQL:
RUN_DATABASE_TESTS=1 python -m pytest
```

Contract tests require no database or external LLM credentials.
