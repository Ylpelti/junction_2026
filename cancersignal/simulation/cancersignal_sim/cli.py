import argparse
from copy import deepcopy
from dataclasses import asdict
import json
from pathlib import Path
from .engine import simulate, validate
from .inputs import adapt_seed, attach_predictions, generate, load_patients
from .reporting import comparison, export, metrics, replication_stats, sensitivity_plot, write_csv

LIMITATIONS = [
    "All demonstration parameters are hypothetical; no Finnish clinical calibration or validation.",
    "Relevant means assumed need for the modeled diagnostic pathway, not confirmed cancer.",
    "Seed histories are representative examples, not population estimates; unknown labels remain unknown.",
    "Finite horizon: latency summaries include observed milestones only and may have survivor bias. Read not_observed and unfinished counts alongside them.",
    "Not_observed combines non-routing, not-applicable outcomes and horizon censoring; it is not a survival estimate.",
    "Patient metrics use arrivals at/after warmup; resource metrics use all activity in the post-warmup window.",
    "Resources are continuous effective daily capacity, without opening hours, weekends or competing external workload.",
    "One follow-up at most; no mortality, disease progression, stage shift or survival benefit is modeled.",
    "Diagnosis means completion of specialist diagnostic pathway; treatment is an assumed milestone with unlimited downstream capacity.",
    "Review scheduling is configured explicitly: FIFO or nonpreemptive priority using the same GP capacity; priority may delay ordinary visits.",
    "Monte Carlo SD and standard error measure simulation variability, not parameter uncertainty or clinical evidence.",
    "Hypothetical routing conditional on reference labels is a generative assumption, not information available to clinicians.",
    "Extraction F1 and retrieval recall are not detection sensitivity and are never used as such."
]


def experiment(config, patients=None):
    validate(config)
    runs, differences = [], []
    for seed in config["seeds"]:
        population = patients if patients is not None else generate(config, seed)
        pair = []
        for assisted in (False, True):
            run = simulate(config, population, seed, model=config.get("assisted_model", "B") if assisted else "A")
            run["metrics"] = metrics(run, config)
            from .study import kpis, patient_comparison
            run["cohort_metrics"] = kpis(run, config)
            run["cohort_metrics"].update({"paired."+k:v for k,v in patient_comparison(pair[0] if pair else run, run, config).items()})
            pair.append(run)
            runs.append(run)
        differences.append(comparison(pair[0]["metrics"], pair[1]["metrics"]))
    return {"schema_version": "1.0", "configuration": config, "units": "effective calendar days",
            "limitations": LIMITATIONS, "runs": runs,
            "paired_differences": [{"seed": seed, "differences": diff} for seed, diff in zip(config["seeds"], differences)],
            "paired_statistics": replication_stats(differences)}


SWEEP = {"signal.tpr": [0.4, 0.8, 1.0], "signal.fpr": [0.0, 0.12, 0.4, 0.8],
         "capacities.gp": [1, 2, 3], "capacities.diagnostic": [1, 2, 3],
         "capacities.specialist": [1, 2, 3], "service.review.mean": [0.0, 0.05, 0.2],
         "signal.gp_time_saved": [0.0, 0.01, 0.04]}


def sensitivity(config, patients=None):
    results = []
    for parameter, values in SWEEP.items():
        for value in values:
            varied = deepcopy(config)
            target = varied
            parts = parameter.split(".")
            for part in parts[:-1]:
                target = target[part]
            target[parts[-1]] = value
            report = experiment(varied, patients)
            results.append({"parameter": parameter, "value": value, "configuration": varied,
                            "paired_statistics": report["paired_statistics"]})
    return results


def main():
    parser = argparse.ArgumentParser(description="Synthetic CancerSignal pathway simulation")
    sub = parser.add_subparsers(dest="command", required=True)
    for command in ("run", "sensitivity"):
        p = sub.add_parser(command)
        p.add_argument("--config", default="config/demo.json")
        p.add_argument("--patients")
        p.add_argument("--predictions")
        p.add_argument("--out", default=f"outputs/{command}")
        p.add_argument("--no-plots", action="store_true")
    p = sub.add_parser("study", help="Four-arm paired study with fixed 60-day cohorts")
    p.add_argument("--config", default="config/workflows.json")
    p.add_argument("--out", default="outputs/study")
    p.add_argument("--replications", type=int, default=None)
    p.add_argument("--sensitivity", action="store_true")
    p.add_argument("--reference", action="store_true")
    p.add_argument("--drain", action="store_true")
    p.add_argument("--workers", type=int, default=1)
    p = sub.add_parser("adapt-seed")
    p.add_argument("--project", default="..")
    p.add_argument("--out", default="outputs/seed_patients.json")
    args = parser.parse_args()
    if args.command == "adapt-seed":
        patients = adapt_seed(args.project)
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(json.dumps([asdict(p) for p in patients], indent=2))
        print(f"Exported {len(patients)} histories with unknown reference labels to {args.out}")
        return
    config = json.loads(Path(args.config).read_text())
    if args.command == "study":
        from .study import run_study
        if args.workers < 1:
            parser.error("--workers must be a positive integer")
        if args.replications is not None:
            if args.replications < 2:
                parser.error("--replications must be at least 2 for paired intervals")
            config["seeds"] = list(range(1001, 1001 + args.replications))
        run_study(config, args.out, args.sensitivity, args.reference, args.drain, args.workers)
        print(f"Study written to {args.out}")
        return
    patients = load_patients(args.patients) if args.patients else None
    if args.predictions:
        if patients is None:
            parser.error("--predictions requires --patients")
        attach_predictions(patients, json.loads(Path(args.predictions).read_text()))
    if args.command == "run":
        report = experiment(config, patients)
        export(args.out, report, plots=not args.no_plots)
        from .pitch_study import HEADLINES
        write_csv(Path(args.out)/"headline_metrics.csv", [{"seed":r["seed"], "model":r["model"], **{label:r["cohort_metrics"][metric] for label,metric in HEADLINES}} for r in report["runs"]])
    else:
        rows = sensitivity(config, patients)
        path = Path(args.out)
        path.mkdir(parents=True, exist_ok=True)
        (path / "sensitivity.json").write_text(json.dumps({"limitations": LIMITATIONS, "experiments": rows}, indent=2, allow_nan=False))
        write_csv(path / "sensitivity.csv", [{"parameter": r["parameter"], "value": r["value"], "metric": k, **v} for r in rows for k, v in r["paired_statistics"].items()])
        if not args.no_plots:
            # Set up headless plotting and a baseline comparison alongside the sweep.
            export(path, experiment(config, patients), plots=True)
            sensitivity_plot(path, rows)
    print(f"Results written to {args.out}")


if __name__ == "__main__":
    main()
