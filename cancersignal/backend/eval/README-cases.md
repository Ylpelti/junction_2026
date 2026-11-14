# CancerSignal A/B/C evaluation cases (v1)

36 synthetic, fictional patients for comparing A (note only), B (note + labs) and C (note + full history).
Put the file at `cancersignal/backend/eval/cases.json`.

Expected labels were written by hand from `docs/rulebook-colorectal.md` (rules SUO-01…SUO-10, version
`nice-2023-demo-1`). They describe the intended clinical outcome with full information, so A and B are judged
against the same truth as C. An independent checker (not the project's engine) confirmed every label that does
not depend on reconciliation.

## Contents

| Category | Cases | What it tests |
| --- | --- | --- |
| history_decides | 8 | Today's note is vague; the signal is in earlier labs or notes. C should beat A. |
| clear | 8 | Today's note alone meets a rule. All variants should find these. |
| harmless | 6 | Nothing should fire. |
| hard_negative | 6 | Negated, resolved, explained or intentional findings. Nothing should fire. |
| boundary | 8 | Age 39/40, 49/50, 59/60 and FIT 9.9/10. |

Split: 19 `dev`, 17 `test`. Do not look at or tune on `test` before the final run.
Levels: 16 none, 15 review, 5 urgent. Time t for every case: 2026-11-14T09:00:00Z.

EVAL-001, EVAL-002, EVAL-017 and EVAL-023 are the four demo patients (Laine, Nieminen, Korhonen, Heikkinen).

## Format

- `patient`: `sex`, `birth_date`, `age_at_t` (for reading only; the harness computes age itself).
- `note`: today's note (`text`) and `coded`, the symptom facts a correct extraction of that note should produce
  (code from `reasoning/vocabulary.py`, verbatim quote, status). The structured extractor uses `coded`; the LLM
  extractor should read `text`.
- `history`: earlier observations, each with a human-readable `ref` (for example `LAB-0814A`). Notes can carry
  `coded` symptom facts too. Labs use codes `B-HB` (g/l), `P-FERRITIN` (ug/l) and `F-HB-FIT` (ug/g), as in
  `derived_findings.py`.
- `expected`: `level`, `rules`, optionally `key_sources` (refs a correct alert should cite) and `explained_by`
  (the record that explains a finding away).

## Read before reporting results

- `known_gap` marks cases where today's system is expected to disagree with the label. The main one is EVAL-028:
  reconciliation is not implemented, so an anaemia that was already investigated still fires SUO-07. Report it
  as a known limitation, do not change the label to make the score look better.
- EVAL-027 (bleeding attributed to known haemorrhoids, coded `uncertain`) is clinically debatable; ask the mentor.
- Synthetic data: results show that the method works on these cases, not clinical performance. Precision here is
  not real-world positive predictive value.
