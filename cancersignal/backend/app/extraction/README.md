# Independent clinical extraction

This package consumes an already retrieved, synthetic patient snapshot. It does
not query PostgreSQL, perform retrieval, call mathematical models, evaluate
rules, persist findings, or register HTTP routes. Original observations remain
separate from model interpretations.

The package itself stays independent of the pipeline. The analysis API uses it
only when `CANCERSIGNAL_EXTRACTION=llm` is set (see "Analysis pipeline" below).
Then `app/services/llm_extraction.py` adapts it to the pipeline's extractor
interface.

## Install and run offline

From `cancersignal/backend/`, using Python 3.11+:

```sh
python3 -m venv .venv                  # only if needed
.venv/bin/python -m pip install -e '.[dev,llm]'
.venv/bin/python -m app.extraction --example examples/extraction/synthetic.json
.venv/bin/python -m pytest tests/extraction -q
```

The example uses an explicitly **hand-authored synthetic response**, not an LLM
prediction or benchmark result. It demonstrates Finnish source quotes, current
negation, historical bleeding, resolved pain, weight loss, a planned colonoscopy,
and conflicting accounts of completion. Its `partial` status is intentional.
Tests use fixture providers or `httpx.MockTransport`; no network, keys, frontend,
database server, or rule engine is needed. Existing shared schemas import ORM
declarations but do not connect to a database.

## Python integration

```python
from app.extraction import ClinicalExtractor
from app.extraction.providers import ChatCompletionsProvider, ProviderSettings

# Constructing this provider does not authorize or make live calls.
extractor = ClinicalExtractor(ChatCompletionsProvider(ProviderSettings()))
batch = extractor(
    context,                       # app.contracts.clinical_context.RetrievedContext
    input_note=current_note,       # SourceObservation, with an original source UUID
    structured_context=labs,       # optional StructuredPatientContext
)
if batch.status == "failed":
    handle_failure(batch.issues)    # Never interpret extraction failure as no signals.
else:
    consume_findings(batch.findings)
```

`ClinicalExtractor.__call__` implements the shared `FindingExtractor` protocol;
`structured_context` is an additional optional keyword. History-only extraction
is allowed by omitting `input_note`. A supplied input note must be a textual
`clinical_note` for this patient with `observed_at == context.as_of`. Its
`recorded_at` may be later under the existing explicit-input contract. Historical
records must satisfy both event-time and recorded-time cutoffs, strictly before
the analysis time. Structured context must share the patient and cutoffs and
cannot widen the retrieval time window. Caller input errors raise validation
errors **before** provider access. Provider/output/evidence failures return a
`failed` batch with an error code and no findings.

The output is the existing immutable `FindingBatch` / `ClinicalFinding`, including
patient ID, polarity, temporal status, original source IDs/quotes/offsets, explicit
uncertainty, missing information, and server-assigned provider/model/prompt/config
provenance. The model cannot assign patient IDs, finding IDs or provenance. An
empty successful batch is distinct from failure. Incomplete source coverage and
uncertain interpretations produce `partial` output.

For consumers using the older `StructuredFinding` schema:

```python
from app.extraction.compatibility import legacy_findings

old_schema_findings = legacy_findings(batch)
# Supply these to the existing consumer; no rule-engine changes are needed.
# Keep batch as the authoritative record with provenance and missing information.
```

The adapter reuses `app.contracts.adapters.to_legacy_finding` where lossless. The
old enum cannot express historical absence/uncertainty or unknown timing; those
cases become `uncertain`, retaining original states and gaps in uncertainty text.
This prevents the existing rules from treating them as positive facts. Failed
batches raise instead of becoming an empty rule input. The interface is
synchronous; the analysis route is a sync FastAPI handler, so it already runs in
a worker thread.

## Analysis pipeline

`app/services/llm_extraction.py` (`LlmNoteExtractor`) is the adapter. It is
enabled through `cancersignal/.env` or the environment:

| Variable | Meaning / default |
| --- | --- |
| `CANCERSIGNAL_EXTRACTION` | `off` (default: structured-only demo extractor) or `llm` |
| `CANCERSIGNAL_EXTRACTION_ENV_FILE` | Optional path to the provider settings file, e.g. `.env.extraction`; otherwise `EXTRACTION_*` come from the environment |
| `CANCERSIGNAL_EXTRACTION_ALLOW_LIVE` | `false` (default). Only `true` allows paid live calls |
| `CANCERSIGNAL_EXTRACTION_CACHE_DIR` | Optional validated response cache, e.g. `.venv/extraction-cache` |

How the adapter behaves:
- **Order:** the structured extractor runs first; LLM note findings are added with `legacy_findings()`.
- **Failures:** a failed batch or a bad configuration stores the run as `failed`, with error code `clinical_extraction_<code>`. It never turns into "no signals".
- **Offline demo:** run once with live calls allowed and a cache directory, then turn live calls off. Only cached notes (identical text and history) succeed, and others fail explicitly.
- **Dependency:** live calls need the `llm` extra (`httpx`).

## Provider configuration and authorized live use

Use exported environment variables or an explicitly selected local settings file.
To configure Verda without putting the key in shell history:

```sh
cp -n examples/extraction/.env.example .env.extraction
```

Edit `.env.extraction`: fill `EXTRACTION_API_KEY` with your Verda inference API
key and `EXTRACTION_MODEL` with the exact enabled model ID. This local file is
ignored by Git. Pass `--env-file .env.extraction` to the CLI, or
`ProviderSettings(_env_file=".env.extraction")` in Python. Exported variables take
precedence over file values. No `.env` file is discovered automatically and the
benchmark's configuration is unchanged.

| Variable | Meaning / default |
| --- | --- |
| `EXTRACTION_PROVIDER` | `verda` (default) or `openai` |
| `EXTRACTION_MODEL` | Required exact enabled model ID; no guessed default |
| `EXTRACTION_API_KEY` | Inference API key for the selected provider |
| `EXTRACTION_BASE_URL` | Optional HTTPS `/v1` base; defaults to the selected provider |
| `EXTRACTION_RESPONSE_FORMAT` | `json_schema` (default), or explicitly `json_object` |
| `EXTRACTION_REASONING_EFFORT` | Optional `none/minimal/low/medium/high/xhigh/max`; model must support the selected value |
| `EXTRACTION_MAX_OUTPUT_TOKENS` | `4096`, including any hidden reasoning tokens |
| `EXTRACTION_MAX_INPUT_BYTES` | `60000`, serialized messages plus schema |
| `EXTRACTION_CONTEXT_WINDOW_TOKENS` | Optional model-specific total context budget |
| `EXTRACTION_TIMEOUT_SECONDS` | `55` |
| `EXTRACTION_MAX_RESPONSE_BYTES` | `1000000` |

After configuring the file and explicitly authorizing a live call, invoke:

```sh
.venv/bin/python -m app.extraction \
  --env-file .env.extraction \
  --example examples/extraction/synthetic.json --live --allow-live \
  --cache-dir .venv/extraction-cache
```

Python callers must similarly opt in using
`ChatCompletionsProvider(settings, allow_live=True)` after authorization. Fixture
mode is the CLI default. An in-memory `httpx.MockTransport` bypasses the network
gate solely for tests. There are no automatic retries, provider/model switches,
parameter removal, output repair, or fixture fallbacks. Error reports omit remote
error bodies, secrets, source text, and hidden reasoning.

Provider formatting is isolated in `providers.py`. Both use Chat Completions;
OpenAI uses `max_completion_tokens` and `store=False`, Verda uses `max_tokens`.
Reasoning effort and JSON-schema support depend on the selected model. Unsupported
parameters yield an explicit `provider_request_rejected` failure; configure the
model capabilities rather than silently dropping parameters. A model supporting
JSON mode only can be explicitly configured with `json_object`; the identical
local Pydantic validation still applies. The prompt always includes the fixed
schema. This follows the [Verda compatibility documentation](https://docs.verda.com/inference/openai-compatibility/)
and [OpenAI structured-output documentation](https://developers.openai.com/api/docs/guides/structured-outputs?api-mode=chat).

Preflight limits reject oversized input without truncating records. The optional
context check conservatively budgets UTF-8 bytes plus framing/output allowance;
it is **not** a model tokenizer or exact token count. Configure the actual model
window; the provider may still reject an over-limit request. Token exhaustion,
refusal, incomplete output, timeout, HTTP errors and malformed responses all fail
explicitly. No live provider compatibility or clinical quality is established by
the mocked tests.

## Grounding, uncertainty and vocabulary

Existing pure contract validators check original IDs, patient/time boundaries,
exact quotes, and optional Unicode character offsets `[start,end)`. Missing-data
references are checked too. An invalid reference rejects the entire batch before
anything is returned for persistence. There is no database resolver that could
expand the supplied patient snapshot.

Every successful or partial batch reports `clinical_interpretation_not_verified`: source
integrity does not prove clinical entailment, correct negation/temporal reasoning,
or complete extraction. Notes are serialized as untrusted data under the user
role, with a system instruction to ignore embedded commands. This is a prompt
boundary, not a guarantee that a live model cannot misinterpret malicious notes.
Ambiguous model output must carry uncertainty; the module does not guess a
different clinical or temporal state. Model-based semantic accuracy still needs
independent evaluation and professional review.

The six canonical symptom names reuse **only constants** from
`app.reasoning.vocabulary`; no mathematical or trigger implementation is imported.
Lab-derived finding labels, diagnoses, probabilities, scores, referral decisions,
and numerical computation fields are excluded from the extraction schema.
Descriptions remain model interpretations and require review, even with valid
quotes. Explicit other source facts can use `documented_observation`.

The shared contract has no separate investigation workflow field. This module
therefore uses `investigation_planned`, `investigation_completed`,
`investigation_status_unknown`, and `follow_up` finding types. Event timing stays
in `temporal_status`, separate from planned/completed workflow. These types fit
the existing open finding vocabulary and do not change shared contracts or rules.
If richer workflow relations are later needed, propose a coordinated shared
`investigation_status` / event-link contract rather than overloading symptom
polarity or adding fields unilaterally.

## Demo response cache

Optional `cache_dir` stores only schema/evidence-validated responses. Its key
includes the exact input snapshot, prompt, schema, provider/model and nonsecret
configuration. Every cache read is revalidated against the original sources.
Cache hits work without live permission; a miss still requires it. An invalid
cache fails explicitly, without a paid retry. Cache storage errors are reported.
Use `.venv/extraction-cache` (already ignored) and synthetic data only. The
repository example remains clearly identified as a hand-authored replay.

The separate Kimi/DeepSeek/OpenAI benchmark checkout was not present in this
working tree, so its provider settings could not be inspected. No benchmark
dataset, prompt, score or report was changed. Align the exact deployed model ID
and supported parameters with that checkout before comparing results.
