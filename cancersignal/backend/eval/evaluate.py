"""A/B/C evaluation: same extractor, same lab derivation, same rules, same age; only the input differs.

    A = today's note and its coded facts only
    B = A + laboratory history
    C = A + full history (earlier notes and their coded facts, labs, investigations)

Run from backend/:
    python -m eval.evaluate --split dev --extractor structured

Reuses the real pipeline code (StructuredSourceExtractor or LlmNoteExtractor,
derive_lab_findings, evaluate_triggers, age_in_years, rules from seed_rules).
No database, no server, no network; the LLM option only reads a response cache.
"""
import argparse
import csv
from dataclasses import dataclass
from pathlib import Path
import sys

from app.db.seed_rules import colorectal_rule_rows
from app.rag.context import ContextObservation, ExtractionResult, RetrievedContext
from app.rag.extraction import StructuredSourceExtractor
from app.reasoning.derived_findings import derive_lab_findings
from app.reasoning.trigger_engine import evaluate_triggers
from app.reasoning.vocabulary import AGE_YEARS
from app.schemas.records import ObservationRead, TriggerRuleRead
from app.services.analysis_service import age_in_years
from app.services.errors import PipelineError

from eval.cases import Case, load_cases

VARIANTS = ("A", "B", "C")
VARIANT_TEXT = {
    "A": "today's note only",
    "B": "note + laboratory history",
    "C": "note + full history (CancerSignal)",
}
LEVELS = ("none", "review", "urgent")
RESULTS_DIR = Path(__file__).with_name("results")


def rules() -> list[TriggerRuleRead]:
    """The real seeded rule definitions (SUO-01…SUO-10), without touching a database."""
    return [TriggerRuleRead(**row) for row in colorectal_rule_rows()]


def rule_code(rule: TriggerRuleRead) -> str:
    return rule.name.split(":")[0]


# ---- Variant inputs -----------------------------------------------------------

def history_for(case: Case, variant: str) -> list[ObservationRead]:
    """Raw earlier records visible in a variant (all strictly before t)."""
    if variant == "A":
        return []
    if variant == "B":
        return list(case.labs)
    if variant == "C":
        return list(case.history)
    raise ValueError(f"Unknown variant {variant!r}")


def coded_facts_for(case: Case, variant: str) -> list[ObservationRead]:
    """Coded symptom facts given to the structured extractor.

    Today's facts are in every variant (they are the note being analysed, at t).
    Earlier notes' facts only in C. The extractor keeps the latest status per code,
    so a fact recorded today overrides an older one.
    """
    return [*case.today_facts, *(case.history_facts if variant == "C" else [])]


def assert_no_future_data(case: Case, records: list[ObservationRead]) -> None:
    """Only today's note and its facts may be at t; everything else must be strictly before t."""
    for record in records:
        if record.id in case.today_ids:
            if record.observed_at != case.t:
                raise AssertionError(f"{case.id}: today's record {case.refs[record.id]} is not at t.")
        elif not (record.observed_at < case.t and record.recorded_at < case.t):
            raise AssertionError(f"{case.id}: {case.refs.get(record.id, record.id)} is not before t.")


def context(case: Case, records: list[ObservationRead]) -> RetrievedContext:
    return RetrievedContext(patient_id=case.patient_id, cutoff=case.t,
        observations=[ContextObservation(observation=r, source_excerpt=r.text) for r in records],
        ranked_observation_ids=[r.id for r in records])


# ---- Extractors ---------------------------------------------------------------

class StructuredRunner:
    """The real StructuredSourceExtractor on coded facts + the variant's records."""
    name = "structured"

    def __init__(self):
        self.extractor = StructuredSourceExtractor()

    def records(self, case: Case, variant: str) -> list[ObservationRead]:
        return [*coded_facts_for(case, variant), *history_for(case, variant)]

    def extract(self, case: Case, variant: str, records: list[ObservationRead]) -> ExtractionResult:
        return ExtractionResult.model_validate(self.extractor.extract(context(case, records), case.note))


class LlmCacheRunner:
    """The real LlmNoteExtractor reading note TEXT (no coded facts), cached responses only.

    Live calls are never allowed. A cache miss stops the run with the case id.
    """
    name = "llm-cache"

    def __init__(self, cache_dir: Path, env_file: Path | None):
        from app.services.llm_extraction import LlmNoteExtractor, build_from_settings

        if not cache_dir.is_dir():
            raise SystemExit(f"llm-cache: cache directory not found: {cache_dir}")
        build = build_from_settings(env_file, False, cache_dir)  # allow_live=False, always
        self.extractor = LlmNoteExtractor(StructuredSourceExtractor(), build_clinical=build)

    def records(self, case: Case, variant: str) -> list[ObservationRead]:
        return history_for(case, variant)

    def extract(self, case: Case, variant: str, records: list[ObservationRead]) -> ExtractionResult:
        try:
            return self.extractor.extract(context(case, records), case.note)
        except PipelineError as error:
            if error.code == "clinical_extraction_live_calls_disabled":
                raise SystemExit(f"llm-cache: no cached LLM response for {case.id} variant {variant}. "
                                 "Record the cache first with an authorised live run; this harness never calls a live LLM.") from None
            raise SystemExit(f"llm-cache: extraction failed for {case.id} variant {variant} ({error.code}).") from None


# ---- Pipeline -----------------------------------------------------------------

@dataclass(frozen=True)
class Outcome:
    case: Case
    variant: str
    level: str
    rules: frozenset[str]
    evidence_refs: tuple[str, ...]
    grounded: bool
    key_sources_hit: bool | None

    @property
    def level_ok(self) -> bool:
        return self.level == self.case.expected_level

    @property
    def rules_ok(self) -> bool:
        return self.rules == self.case.expected_rules

    @property
    def correct(self) -> bool:
        return self.level_ok and self.rules_ok


def run_variant(case: Case, variant: str, runner, rule_set: list[TriggerRuleRead]) -> Outcome:
    records = runner.records(case, variant)
    assert_no_future_data(case, records)
    extraction = runner.extract(case, variant, records)
    labs = [r for r in history_for(case, variant) if r.observation_type == "laboratory"]
    derived, _ = derive_lab_findings(labs, sex=case.sex)
    findings = [*extraction.findings, *derived]
    facts = {AGE_YEARS: age_in_years(case.birth_date, case.t)}
    evaluations = evaluate_triggers(case.patient_id, findings, rule_set, patient_facts=facts)

    codes = {rule.id: rule_code(rule) for rule in rule_set}
    triggered = [e for e in evaluations if e.triggered]
    level = "urgent" if any(e.priority == "urgent" for e in triggered) else "review" if triggered else "none"
    evidence_ids = {i for e in triggered for i in e.evidence_observation_ids}
    times = {r.id: r.observed_at for r in (case.note, *case.today_facts, *case.history, *case.history_facts)}
    grounded = all(i in case.refs and (i in case.today_ids or times[i] < case.t) for i in evidence_ids)
    refs = tuple(sorted({case.refs.get(i, f"UNKNOWN:{i}") for i in evidence_ids}))
    key_hit = (set(case.key_sources) <= set(refs)) if case.key_sources else None
    return Outcome(case=case, variant=variant, level=level, rules=frozenset(codes[e.trigger_rule_id] for e in triggered),
                   evidence_refs=refs, grounded=grounded, key_sources_hit=key_hit)


def run(cases: list[Case], runner) -> list[Outcome]:
    rule_set = rules()
    return [run_variant(case, variant, runner, rule_set) for case in cases for variant in VARIANTS]


# ---- Metrics ------------------------------------------------------------------

def ratio(numerator: int, denominator: int) -> float | None:
    return numerator / denominator if denominator else None


def metrics(outcomes: list[Outcome]) -> dict:
    n = len(outcomes)
    positive = [o for o in outcomes if o.case.expected_level != "none"]
    alerts = [o for o in outcomes if o.level != "none"]
    tp = sum(1 for o in positive if o.level != "none")
    fp = sum(1 for o in alerts if o.case.expected_level == "none")
    with_keys = [o for o in outcomes if o.key_sources_hit is not None]
    return {
        "n": n,
        "recall": ratio(tp, len(positive)),
        "precision": ratio(tp, len(alerts)),
        "false_alarms_per_100": (100 * fp / n) if n else None,
        "level_accuracy": ratio(sum(o.level_ok for o in outcomes), n),
        "exact_rules": ratio(sum(o.rules_ok for o in outcomes), n),
        "grounding": ratio(sum(o.grounded for o in alerts), len(alerts)),
        "key_sources": ratio(sum(bool(o.key_sources_hit) for o in with_keys), len(with_keys)),
        "tp": tp, "fp": fp, "fn": len(positive) - tp,
    }


def fmt(value) -> str:
    if value is None:
        return "–"
    if isinstance(value, float):
        return f"{value:.2f}"
    return str(value)


METRIC_COLUMNS = [
    ("recall", "Recall (any alert)"),
    ("precision", "Precision (any alert)"),
    ("false_alarms_per_100", "False alarms / 100"),
    ("level_accuracy", "Level accuracy"),
    ("exact_rules", "Exact rule set"),
    ("grounding", "Grounding"),
    ("key_sources", "Key sources hit"),
]


def table(outcomes: list[Outcome]) -> list[str]:
    head = "| Variant | n | " + " | ".join(label for _, label in METRIC_COLUMNS) + " |"
    lines = [head, "|" + " --- |" * (len(METRIC_COLUMNS) + 2)]
    for variant in VARIANTS:
        m = metrics([o for o in outcomes if o.variant == variant])
        cells = " | ".join(fmt(m[key]) for key, _ in METRIC_COLUMNS)
        lines.append(f"| {variant} ({VARIANT_TEXT[variant]}) | {m['n']} | {cells} |")
    return lines


# ---- Report -------------------------------------------------------------------

def summary(outcomes: list[Outcome], split: str, extractor: str) -> str:
    cases = list(dict.fromkeys(o.case.id for o in outcomes))
    lines = [
        "# CancerSignal A/B/C evaluation",
        "",
        f"Split: **{split}** ({len(cases)} cases) · extractor: **{extractor}** · rulebook `nice-2023-demo-1`",
        "",
        "> Synthetic, fictional cases. Prototype test results, not clinical validation. "
        "Precision here is not real-world positive predictive value. Do not tune rules on the test split.",
        "",
        "A = today's note only · B = note + laboratory history · C = note + full history (CancerSignal). "
        "Same extractor, lab derivation, rules and age in every variant.",
        "",
    ]
    splits = [s for s in ("dev", "test") if any(o.case.split == s for o in outcomes)]
    for name in [*splits, *(["all"] if len(splits) > 1 else [])]:
        subset = outcomes if name == "all" else [o for o in outcomes if o.case.split == name]
        n_cases = len({o.case.id for o in subset})
        lines += [f"## Split: {name} ({n_cases} cases)", "", *table(subset), ""]

    lines += ["## By category (level accuracy / recall per variant)", "",
              "| Category | n | " + " | ".join(f"{v} level acc. | {v} recall" for v in VARIANTS) + " |",
              "|" + " --- |" * (2 + 2 * len(VARIANTS))]
    for category in sorted({o.case.category for o in outcomes}):
        subset = [o for o in outcomes if o.case.category == category]
        cells = []
        for variant in VARIANTS:
            m = metrics([o for o in subset if o.variant == variant])
            cells += [fmt(m["level_accuracy"]), fmt(m["recall"])]
        lines.append(f"| {category} | {len({o.case.id for o in subset})} | " + " | ".join(cells) + " |")
    lines.append("")

    gaps = [o for o in outcomes if o.case.known_gap]
    if gaps:
        lines += ["## Known gaps (counted normally above)", "",
                  "| Case | Variant | Expected | Got | Note |", "| --- | --- | --- | --- | --- |"]
        for o in gaps:
            lines.append(f"| {o.case.id} | {o.variant} | {o.case.expected_level} {sorted(o.case.expected_rules)} | "
                         f"{o.level} {sorted(o.rules)} | {o.case.known_gap} |")
        lines.append("")

    wrong = [o for o in outcomes if not o.correct]
    lines += [f"## Mismatches ({len(wrong)} of {len(outcomes)} case-variants)", ""]
    if wrong:
        lines += ["| Case | Category | Variant | Expected | Got | Evidence |", "| --- | --- | --- | --- | --- | --- |"]
        for o in sorted(wrong, key=lambda o: (o.case.id, o.variant)):
            lines.append(f"| {o.case.id} | {o.case.category} | {o.variant} | {o.case.expected_level} "
                         f"{sorted(o.case.expected_rules)} | {o.level} {sorted(o.rules)} | {', '.join(o.evidence_refs) or '–'} |")
    else:
        lines.append("None.")
    lines.append("")
    return "\n".join(lines)


def write_csv(outcomes: list[Outcome], path: Path) -> None:
    ordered = sorted(outcomes, key=lambda o: (o.correct, o.case.id, o.variant))  # wrong first
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["case_id", "split", "category", "variant", "correct", "expected_level", "got_level",
                         "level_ok", "expected_rules", "got_rules", "rules_ok", "evidence_refs", "grounded",
                         "key_sources", "key_sources_hit", "known_gap"])
        for o in ordered:
            writer.writerow([o.case.id, o.case.split, o.case.category, o.variant, o.correct, o.case.expected_level,
                             o.level, o.level_ok, " ".join(sorted(o.case.expected_rules)), " ".join(sorted(o.rules)),
                             o.rules_ok, " ".join(o.evidence_refs), o.grounded, " ".join(o.case.key_sources),
                             "" if o.key_sources_hit is None else o.key_sources_hit, o.case.known_gap or ""])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="CancerSignal A/B/C evaluation on synthetic cases (no DB, no network).")
    parser.add_argument("--split", choices=["dev", "test", "all"], default="dev",
                        help="Which cases to run (default: dev). Do not tune on test.")
    parser.add_argument("--extractor", choices=["structured", "llm-cache"], default="structured")
    parser.add_argument("--cache-dir", type=Path, default=Path(".venv/extraction-cache"),
                        help="llm-cache only: validated LLM response cache.")
    parser.add_argument("--env-file", type=Path, help="llm-cache only: provider settings file (EXTRACTION_MODEL, ...).")
    parser.add_argument("--out", type=Path, default=RESULTS_DIR, help="Output directory (default: eval/results).")
    args = parser.parse_args(argv)

    cases = [c for c in load_cases() if args.split == "all" or c.split == args.split]
    runner = StructuredRunner() if args.extractor == "structured" else LlmCacheRunner(args.cache_dir, args.env_file)
    outcomes = run(cases, runner)

    text = summary(outcomes, args.split, args.extractor)
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "summary.md").write_text(text, encoding="utf-8")
    write_csv(outcomes, args.out / "cases.csv")
    print(text)
    print(f"Wrote {args.out / 'summary.md'} and {args.out / 'cases.csv'}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
