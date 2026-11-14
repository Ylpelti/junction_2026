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
    "No referral priority; FIFO queues expose indirect effects on all patients. GP review re-enters the shared FIFO queue.",
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
            run = simulate(config, population, seed, assisted)
            run["metrics"] = metrics(run, config)
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
    p = sub.add_parser("adapt-seed")
    p.add_argument("--project", default="../cancersignal")
    p.add_argument("--out", default="outputs/seed_patients.json")
    args = parser.parse_args()
    if args.command == "adapt-seed":
        patients = adapt_seed(args.project)
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(json.dumps([asdict(p) for p in patients], indent=2))
        print(f"Exported {len(patients)} histories with unknown reference labels to {args.out}")
        return
    config = json.loads(Path(args.config).read_text())
    patients = load_patients(args.patients) if args.patients else None
    if args.predictions:
        if patients is None:
            parser.error("--predictions requires --patients")
        attach_predictions(patients, json.loads(Path(args.predictions).read_text()))
    if args.command == "run":
        report = experiment(config, patients)
        export(args.out, report, plots=not args.no_plots)
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
