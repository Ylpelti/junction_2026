import csv
import json
from pathlib import Path
import statistics

STAGES = {"gp": "gp_start", "investigation": "diagnostic_start", "referral": "referral", "diagnosis": "diagnosis", "treatment": "treatment"}


def quantile(values, q):
    if not values:
        return None
    v = sorted(values)
    pos = (len(v) - 1) * q
    lo = int(pos)
    return v[lo] + (v[min(lo + 1, len(v) - 1)] - v[lo]) * (pos - lo)


def distribution(values):
    return {"n": len(values), "mean": statistics.mean(values) if values else None,
            "median": quantile(values, .5), "p90": quantile(values, .9)}


def patient_metrics(rows):
    result = {"patients": len(rows), "unfinished": sum(not r["complete"] for r in rows)}
    for label, key in STAGES.items():
        values = [r[key] - r["arrival"] for r in rows if key in r]
        result[label] = {**distribution(values), "not_observed": len(rows) - len(values)}
    relevant = [r for r in rows if r["relevant"] is True]
    result["relevant_without_investigation"] = sum("diagnostic_start" not in r for r in relevant)
    result["relevant_no_route"] = sum(r["complete"] and "diagnostic_start" not in r for r in relevant)
    result["signals"] = sum(r["signal"] is True for r in rows)
    result["unknown_signal"] = sum(r["signal"] is None for r in rows)
    result["reviews_started"] = sum("review_start" in r for r in rows)
    result["reviews_completed"] = sum("review_end" in r for r in rows)
    result["true_positive_reviews"] = sum(r["relevant"] is True and "review_start" in r for r in rows)
    result["false_positive_reviews"] = sum(r["relevant"] is False and "review_start" in r for r in rows)
    result["true_positive_signals"] = sum(r["relevant"] is True and r["signal"] is True for r in rows)
    result["false_positive_signals"] = sum(r["relevant"] is False and r["signal"] is True for r in rows)
    result["false_negatives"] = sum(r["relevant"] is True and r["signal"] is False for r in rows)
    return result


def metrics(run, config):
    rows = [r for r in run["patients"] if r["arrival"] >= config["warmup"]]
    result = {"overall": patient_metrics(rows), "strata": {}, "resources": {}}
    for attr in ("relevant", "region", "group", "cohort"):
        result["strata"][attr] = {str(value): patient_metrics([r for r in rows if r[attr] == value]) for value in sorted({r[attr] for r in rows}, key=str)}
    window = config["duration"] - config["warmup"]
    for name, capacity in config["capacities"].items():
        states = [s for s in run["resource_states"] if s["resource"] == name]
        busy, queue = 0., 0.
        for a, b in zip(states, states[1:]):
            dt = max(0, min(b["time"], config["duration"]) - max(a["time"], config["warmup"]))
            busy += a["busy"] * dt
            queue += a["queue"] * dt
        stages = [name] if name != "gp" else ["gp", "review", "gp_followup"]
        waits = [r[s + "_start"] - r[s + "_queue"] for r in run["patients"] for s in stages
                 if s + "_start" in r and r[s + "_start"] >= config["warmup"]]
        result["resources"][name] = {"utilization": busy / (capacity * window), "mean_queue": queue / window,
            "queue_at_horizon": states[-1]["queue"], "busy_service_days": busy, "wait": distribution(waits)}
    result["review_service_days"] = sum(max(0, min(r.get("review_end", config["duration"]), config["duration"]) - max(r["review_start"], config["warmup"])) for r in run["patients"] if "review_start" in r)
    return result


def flatten(obj, prefix=""):
    result = {}
    for key, value in obj.items():
        name = f"{prefix}.{key}" if prefix else key
        if isinstance(value, dict):
            result.update(flatten(value, name))
        elif isinstance(value, (float, int)) or value is None:
            result[name] = value
    return result


def comparison(baseline, assisted):
    a, b = flatten(baseline), flatten(assisted)
    return {k: b[k] - a[k] if a[k] is not None and b.get(k) is not None else None for k in a}


def replication_stats(differences):
    result = {}
    for key in sorted(set().union(*(d.keys() for d in differences))):
        values = [d[key] for d in differences if d.get(key) is not None]
        n = len(values)
        mean = statistics.mean(values) if n else None
        se = statistics.stdev(values) / n ** .5 if n > 1 else None
        result[key] = {"n_pairs": n, "mean_difference": mean, "sd": statistics.stdev(values) if n > 1 else None,
                       "mc_standard_error": se, "min": min(values) if n else None, "max": max(values) if n else None}
    return result


def write_csv(path, rows):
    if not rows:
        path.write_text("")
        return
    fields = sorted(set().union(*(r.keys() for r in rows)))
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows({k: json.dumps(v) if isinstance(v, (list, dict)) else v for k, v in r.items()} for r in rows)


def export(path, report, plots=True):
    path = Path(path)
    path.mkdir(parents=True, exist_ok=True)
    (path / "results.json").write_text(json.dumps(report, indent=2, allow_nan=False))
    for field in ("patients", "events", "resource_states"):
        write_csv(path / f"{field}.csv", [{"seed": run["seed"], "scenario": run["scenario"], **row}
                  for run in report["runs"] for row in run[field]])
    write_csv(path / "paired_statistics.csv", [{"metric": key, **value} for key, value in report["paired_statistics"].items()])
    if plots:
        make_plots(path, report)


def make_plots(path, report):
    import os
    os.environ.setdefault("MPLCONFIGDIR", str(path.resolve() / ".matplotlib"))
    os.environ.setdefault("XDG_CACHE_HOME", str(path.resolve() / ".cache"))
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    colors = {"baseline": "#687887", "assisted": "#167e83"}
    fig, axes = plt.subplots(2, 2, figsize=(12, 8))
    for scenario in colors:
        runs = [r for r in report["runs"] if r["scenario"] == scenario]
        values = [p["diagnostic_start"] - p["arrival"] for r in runs for p in r["patients"]
                  if p["arrival"] >= report["configuration"]["warmup"] and p["relevant"] is True and "diagnostic_start" in p]
        if values:
            axes[0, 0].hist(values, bins=30, alpha=.5, label=scenario, color=colors[scenario])
        first = runs[0]
        gp = [s for s in first["resource_states"] if s["resource"] == "gp"]
        axes[0, 1].step([s["time"] for s in gp], [s["queue"] for s in gp], where="post", label=scenario, color=colors[scenario])
        x = list(range(4))
        offset = -.18 if scenario == "baseline" else .18
        axes[1, 0].bar([i + offset for i in x], [statistics.mean(r["metrics"]["resources"][name]["utilization"] for r in runs) for name in ("nurse", "gp", "diagnostic", "specialist")], width=.36, label=scenario, color=colors[scenario])
    axes[1, 0].set_xticks(range(4), ["Nurse", "GP", "Diagnostic", "Specialist"])
    axes[0, 0].set(title="Relevant cases reaching investigation (completed only)", xlabel="Days from arrival", ylabel="Patients across runs")
    axes[0, 1].set(title="GP queue — first replication", xlabel="Simulation day", ylabel="Waiting patients")
    axes[1, 0].set(title="Mean resource utilization", ylabel="Fraction of capacity", ylim=(0, 1))
    keys = ["strata.relevant.True.investigation.median", "strata.relevant.False.gp.median"]
    for i, key in enumerate(keys):
        stat = report["paired_statistics"].get(key, {})
        if stat.get("mean_difference") is not None:
            axes[1, 1].errorbar(i, stat["mean_difference"], yerr=stat["mc_standard_error"] or 0, fmt="o", color="#167e83")
    axes[1, 1].axhline(0, color="gray", linewidth=1)
    axes[1, 1].set_xticks([0, 1], ["Relevant: investigation", "Others: GP"])
    axes[1, 1].set(title="Assisted − baseline (mean ± 1 MC SE)", ylabel="Difference in median days")
    for ax in axes.flat:
        if ax.get_legend_handles_labels()[0]:
            ax.legend()
    fig.suptitle("Hypothetical operational simulation — not Finnish clinical estimates")
    fig.tight_layout()
    fig.savefig(path / "comparison.png", dpi=150)
    plt.close(fig)


def sensitivity_plot(path, rows):
    import matplotlib.pyplot as plt
    points = [r for r in rows if r["parameter"] == "signal.fpr"]
    fig, ax = plt.subplots(figsize=(8, 5))
    for metric, label in [("strata.relevant.True.investigation.median", "Relevant: investigation"), ("strata.relevant.False.gp.median", "Others: GP")]:
        usable = [r for r in points if r["paired_statistics"].get(metric, {}).get("mean_difference") is not None]
        ax.errorbar([r["value"] for r in usable], [r["paired_statistics"][metric]["mean_difference"] for r in usable], yerr=[r["paired_statistics"][metric]["mc_standard_error"] or 0 for r in usable], marker="o", label=label)
    ax.axhline(0, color="gray", linewidth=1)
    ax.set(xlabel="Assumed false-positive rate", ylabel="Assisted − baseline median days", title="Hypothetical sensitivity (mean ± 1 MC SE)")
    ax.legend()
    fig.tight_layout()
    fig.savefig(Path(path) / "false_positive_sensitivity.png", dpi=150)
    plt.close(fig)
