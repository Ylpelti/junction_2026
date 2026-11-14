# A/B/C evaluation

> **Synthetic, fictional cases. These are prototype test results, not clinical validation.**
> Precision here is not real-world positive predictive value.

The evaluation compares three ways of looking at the same patient at time *t*.

| Variant | Input |
| --- | --- |
| **A** | Today's nurse note only |
| **B** | Today's note + laboratory history |
| **C** | Today's note + full history: earlier notes, labs, investigations. This is CancerSignal. |

Everything else is the same in every variant:
- the extractor;
- lab-derived findings (`derive_lab_findings`);
- the rulebook SUO-01…SUO-10 (`nice-2023-demo-1`, from `app/db/seed_rules.py`);
- age at *t* (`age_in_years`).

Only the input differs, so a difference in results comes from the history. The
harness imports the real backend code. It uses no database, server or network.

## Cases

[`backend/eval/cases.json`](../backend/eval/cases.json) holds 36 hand-labelled
cases, described in [`backend/eval/README-cases.md`](../backend/eval/README-cases.md).

| Category | Cases | What it tests |
| --- | --- | --- |
| `history_decides` | 8 | Today's note is vague; the signal is in the history |
| `clear` | 8 | Today's note alone meets a rule |
| `harmless` | 6 | Nothing should fire |
| `hard_negative` | 6 | Negated, resolved, explained or intentional findings |
| `boundary` | 8 | Age and FIT boundaries |

There are 19 `dev` cases and 17 `test` cases. The expected labels describe the
correct outcome with full information, so A and B are judged against the same
truth as C. The harness never creates or changes cases or labels.

## How to run

From `cancersignal/backend/`, with the virtual environment active:

```sh
python -m pytest eval/test_evaluate.py -q
python -m eval.evaluate --split dev                 # default extractor: structured
python -m eval.evaluate --split test                # final run only
python -m eval.evaluate --split all
```

Output:
- the summary is printed and written to `backend/eval/results/summary.md`;
- `backend/eval/results/cases.csv` has one row per case and variant, wrong ones first.

### Extractors

- **`structured` (default):** the real `StructuredSourceExtractor` reads each case's
  `coded` symptom facts (code, verbatim quote, status). This tests retrieval, lab
  derivation and rules with a correct extraction. It does not test the LLM.
- **`llm-cache`:** the real `LlmNoteExtractor` reads the note **text** instead of
  coded facts. It never calls a live LLM: live calls are always off, so every case
  needs a validated cached response. The first missing response stops the run with
  its case ID.

  ```sh
  python -m eval.evaluate --split dev --extractor llm-cache \
    --cache-dir .venv/extraction-cache --env-file .env.extraction
  ```

  The cache key includes the exact input, prompt, schema and model. Responses must
  be recorded with the same model and prompt version, in an authorised live run
  outside this harness.

### How today's facts are handled

The structured extractor keeps the latest status per symptom code.
- **Every variant:** today's coded facts are added at exactly *t*, so a fact
  recorded today overrides an older one. For example, a bowel change marked
  resolved today is not alerted on (EVAL-025).
- **History:** every other record must be strictly before *t*, for both event time
  and recording time. The loader and the harness both assert this.
- **Variant C only:** coded facts from earlier notes are included.

## Metrics

All metrics are computed per variant: for `dev`, `test` and `all`, and per category.

| Metric | Meaning |
| --- | --- |
| Recall (any alert) | Of cases that should alert (`expected.level != none`), the share that alerted at all |
| Precision (any alert) | Of cases that alerted, the share that should have |
| False alarms / 100 | Alerts on cases that should not alert, per 100 cases |
| Level accuracy | `none` / `review` / `urgent` exactly right |
| Exact rule set | The triggered rule IDs equal the expected ones |
| Grounding | Of alerting cases, the share whose every evidence record belongs to the case and is before *t* (or is today's note) |
| Key sources hit | Of cases with `key_sources`, the share whose alert cites all of them |

The level is `urgent` if any triggered rule is urgent, `review` if any rule
triggered, and `none` otherwise. Priority comes from the rule.

## Caveats

- **Synthetic data:** the cases are synthetic, small and hand-written. Results show
  that the method works on these cases, not clinical performance.
- **Not real-world PPV:** precision on this case mix is not real-world positive
  predictive value.
- **Do not tune on `test`:** develop on `dev` and run `test` once, for the final
  numbers.
- **Known gaps** (`known_gap` in the cases) are counted normally and also listed
  separately in the summary:
  - **EVAL-028:** reconciliation is not implemented. An anaemia that was already
    investigated still fires SUO-07 (and SUO-03). Report this as a known
    limitation, and do not change the label.
  - **EVAL-016:** a referral was already made; the case is kept as urgent.
  - **EVAL-027:** bleeding attributed to haemorrhoids is coded `uncertain`. This is
    clinically debatable; ask the mentor.
- **Structured is not the LLM:** with `structured`, extraction is assumed correct.
  The LLM's own accuracy needs the `llm-cache` run on recorded responses.
