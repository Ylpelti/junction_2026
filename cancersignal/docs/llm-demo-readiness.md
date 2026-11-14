# LLM demo readiness verification — 2026-11-14

Base: `9718db3`. Worktree branch: `feat/llm-demo-readiness`. No paid inference
was authorized or performed. Synthetic contract tests are not independent clinical
validation, and source-reference validation does not establish clinical entailment.

## Changes and findings

- Fixed a missing `validate_evidence` import in `ClinicalExtractor`: a nonempty
  QCancer evidence handoff previously raised `NameError` instead of validating it.
  Regression tests cover valid evidence and invented IDs.
- Extraction cache identity no longer includes retrieval `generated_at`, which is
  wall-clock processing metadata and changes on every retrieval. All source fields,
  IDs, event/recording timestamps, patient identity, query, cutoff, coverage,
  retrieval provenance, prompt/schema and model configuration remain hashed.
- Both existing caches emit INFO logs with `hit`, `miss` or `disabled` and a key
  digest. Logs contain neither credentials nor note text. A hit means a file was
  found; validation must still succeed. API fields are unchanged.
- Retained separate extraction/ explanation caches, atomic owner-only writes,
  validation on every read, and fail-closed corrupted extraction cache handling.
  Corruption never triggers a paid retry. Explanation errors yield a labelled
  deterministic fallback; failed analysis yields no clinical conclusion.
- Added `scripts/verify_llm_demo.py`: existing saved notes, full FastAPI pipeline,
  actual configured PostgreSQL, GET readback and a second offline replay per case.
  It checks the canonical source snapshots and rejects extra observations belonging
  to these patients before inference. It neither seeds nor resets data.

The explanation cache deliberately retains analysis and finding IDs. A new analysis
run can miss that cache even when extraction hits, because plan fact keys refer to
new finding IDs. For exact explanation replay, GET the saved analysis (its Finnish
explanation is persisted); do not strip IDs or dates to reuse a different plan.

## Provider configuration

Both OpenAI and Verda use the existing OpenAI-compatible chat adapter. Local tests
exercise request construction and failures with `httpx.MockTransport`; they do not
prove current remote model availability or model-specific structured-output support.

Use exported variables or an explicit, ignored, owner-readable env file. Never put
keys in command arguments, reports, source code or screenshots. Extraction settings
have **no automatic .env discovery**. Database/application settings separately read
`cancersignal/.env`. Keep extraction and explanation env files separate.

| Variable | Required behavior |
| --- | --- |
| `EXTRACTION_PROVIDER` | `openai` or `verda` (default Verda) |
| `EXTRACTION_MODEL` | Required exact provider model ID; pin a revision if offered |
| `EXTRACTION_API_KEY` | Required for live calls; not needed for cache replay |
| `EXTRACTION_BASE_URL` | Optional HTTPS override; default OpenAI `https://api.openai.com/v1`, Verda `https://inference.verda.com/v1` |
| `EXTRACTION_RESPONSE_FORMAT` | `json_schema` default; explicitly select `json_object` only for a model requiring it; no automatic downgrade |
| `EXTRACTION_REASONING_EFFORT` | Optional model-supported value; unsupported combinations fail explicitly |
| `EXTRACTION_MAX_OUTPUT_TOKENS` | Default 4096 per call; hard limit, no retries |
| `EXTRACTION_MAX_INPUT_BYTES` | Default 60000; exceeding it fails without truncating sources |
| `EXTRACTION_CONTEXT_WINDOW_TOKENS` | Optional conservative byte-based budget, not a tokenizer measurement |
| `EXTRACTION_TIMEOUT_SECONDS` | Default 55, maximum 300 |
| `EXTRACTION_MAX_RESPONSE_BYTES` | Default 1000000 |
| `CANCERSIGNAL_EXTRACTION` | `llm` to enable API adapter; `off` is structured-only fallback, not LLM inference |
| `CANCERSIGNAL_EXTRACTION_ENV_FILE` | Explicit path for API extraction settings |
| `CANCERSIGNAL_EXTRACTION_ALLOW_LIVE` | Default false; only enable after explicit paid-call authorization |
| `CANCERSIGNAL_EXTRACTION_CACHE_DIR` | Ignored local cache directory |

For explanation LLM use, the parallel `EXPLANATION_*` settings and
`CANCERSIGNAL_EXPLANATION=llm`, `..._ENV_FILE`, `..._ALLOW_LIVE`, `..._CACHE_DIR`
apply; see `backend/app/explanation/README.md`. The bounded runner requires
`CANCERSIGNAL_EXPLANATION=deterministic` so there are no hidden explanation charges.

Authentication, HTTP errors, rate limits, timeouts, refusal, truncation, invalid JSON,
schema errors and invented evidence IDs fail explicitly. No retries, fabricated
negative findings, automatic model switching or fixture substitution occur.
QCancer unknowns remain unknown; Python rules retain their priority and mathematics.

## Stable demonstration workflow

The frontend `analyseNote` sends a new note, with a new save-time cutoff; the backend
assigns a new observation ID. Identical text is therefore not the same analysis
context. Do not normalize away these clinically significant differences.

Use the existing POST interface with the latest **saved** synthetic clinical-note
ID instead. The new runner finds those IDs from the unchanged repository dataset:

```text
POST /api/v1/patients/{patient_id}/analyses
{"note_observation_id": "<existing-note-uuid>"}
GET /api/v1/analyses/{returned-analysis-id}
```

This creates analysis runs, not notes. Later eligible record additions, corrections,
source content, timestamps, model or prompt changes must miss extraction cache.
Records outside the fixed historical cutoff are intentionally outside this snapshot;
use a new note/cutoff to demonstrate a later clinical state. Selective retrieval
retains its partial-coverage limitations; caching cannot improve missing retrieval.

Keep cache artifacts private and trusted. Schema/evidence validation is not a
signature proving that a cached response came from a remote provider. Do not copy
hand-authored fixture responses into a live-provider cache. For corrupt entries,
retain the failure report, move the affected entry aside, and explicitly authorize
any fresh paid call. Never silently refill a corrupt offline cache.

## Reproducible commands

From `cancersignal/backend`, install the existing `.[dev,llm]` extras in a Python
3.11+ environment and configure the existing database. Use an isolated demo/test
DB containing the four canonical patients and enabled existing rules. Follow the
existing seed documentation; this work does not change its implementation.

```sh
# Ordinary tests: no provider calls, DB tests skipped.
POSTGRES_PASSWORD=unused .venv/bin/python -m pytest -q

# Actual disposable PostgreSQL tests; configured role needs CREATEDB.
RUN_DATABASE_TESTS=1 .venv/bin/python -m pytest -q

# Existing actual HTTP smoke; --hybrid uses cached real E5 weights.
.venv/bin/python scripts/smoke_pipeline.py
CANCERSIGNAL_RETRIEVAL_MODEL_CACHE=/absolute/path/to/rag-model-cache \
  HF_HUB_OFFLINE=1 .venv/bin/python scripts/smoke_pipeline.py --hybrid

# Offline replay against configured, already seeded synthetic DB.
CANCERSIGNAL_EXPLANATION=deterministic CANCERSIGNAL_RETRIEVAL=auto \
  .venv/bin/python scripts/verify_llm_demo.py \
  --env-file /secure/path/extraction.env \
  --cache-dir .venv/extraction-demo-cache --output /tmp/demo-replay.json
```

An empty offline cache must fail with `live_calls_disabled`, not succeed with empty
findings. Provider/model and all nonsecret settings must match cache preparation.
For API replay, set `CANCERSIGNAL_EXTRACTION=llm`, the same env/cache paths, and
`CANCERSIGNAL_EXTRACTION_ALLOW_LIVE=false`. Restart the API after configuration
changes because extractor configuration is cached in-process.

**Only after explicit paid-call authorization**, use a fresh empty cache directory:

```sh
CANCERSIGNAL_EXPLANATION=deterministic CANCERSIGNAL_RETRIEVAL=auto \
  .venv/bin/python scripts/verify_llm_demo.py --allow-paid-live \
  --env-file /secure/path/extraction.env \
  --cache-dir .venv/extraction-demo-cache-new --output /tmp/demo-live.json
```

Maximum: four extraction attempts, no retries, default output budget 4 × 4096
tokens. Each patient's second pass disables network access and must reuse validated
cache. The runner uses the real FastAPI routes in-process (not a TCP server), SQL
retrieval, unchanged rules, QCancer, Finnish fallback explanations, persistence and
GET readback. Existing `smoke_pipeline.py` separately verifies actual TCP HTTP.
The report includes provider/model/config provenance, attempt count, provider-reported
usage when available, latency, cache events, full rich findings, API results and
independent labels **added after inference**. Cost remains null without verified
pricing. Missing usage is not zero usage. Exit code is nonzero on failed analyses.
Review clinical interpretations manually; schema success alone is not accuracy.

## Verification results and limitations

- Full suite with actual disposable PostgreSQL: **547 passed, 1 skipped** in
  25.39 seconds. The skipped test is the opt-in external inference test.
  An initial run without database configuration failed the CORS dependency check;
  loading the existing secure database configuration resolved it.
- Actual uvicorn HTTP smoke: lexical and real pinned multilingual E5 hybrid passed,
  including persisted Finnish explanation and idempotent review handoff. E5 weights
  came from the existing local cache; no download or inference API was used.
- New four-patient test: actual PostgreSQL/FastAPI, complete-history retrieval,
  hand-authored mock provider responses, four misses then four hits, identical GET
  readback. QCancer reported `insufficient_data` for every patient.
- Existing suites cover negation, contradictions, resolved history, invented
  citations, failed providers, invalid outputs, cache corruption and explanation
  fallback. Hybrid unit/integration tests use fake embeddings; only the separate
  HTTP hybrid smoke above used actual E5.
- Real external LLM calls: **0**. Live Finnish extraction quality, provider-specific
  acceptance, actual token costs and provider latency remain unverified. No live
  response cache was produced. The existing single-case opt-in pytest smoke remains
  available, but the new runner is the bounded four-patient workflow.

The machine-readable `llm-demo-mocked-report.json` contains full per-patient findings
and source quotes. Its findings are deliberate mock inputs, not measured model
predictions. Measured in-process first/replay latency was about 0.05–0.08 seconds;
this is not a live inference latency estimate.

| Patient | Mocked extracted interpretation preserved | Actual unchanged rules in mocked run |
| --- | --- | --- |
| Laine | Current bowel change; historical pain; Hb evidence retained independently | SUO-02 and SUO-07 |
| Nieminen | Historical plan; completion uncertain with later follow-up; current bleeding negated | SUO-07; no invented proof of missed colonoscopy |
| Heikkinen | Historical bleeding, completed investigation, resolved pain, current absence | No triggered rules |
| Korhonen | Documented historical negative bleeding evidence; no invented current symptoms | No triggered rules |

Temporal states and source links survived replay; all accepted quotes/IDs matched
supplied sources. Invalid IDs were rejected in separate tests. False-alert and
missed-finding rates, unsupported clinical interpretation counts, and model temporal
accuracy are **not measured** by these hand-authored cases. The responses intentionally
do not enumerate every possible finding. In particular, an unresolved follow-up
fact need not generate a rule alert, and resolved/routine cases can correctly have
no additional alerts. No histories, independent labels, A/B/C benchmark, clinical
rules or risk calculations were changed.
