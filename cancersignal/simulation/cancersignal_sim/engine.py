"""SimPy shared-capacity resources with optional nonpreemptive GP review priority, finite observation horizon, common random numbers."""
from dataclasses import asdict
import math
import simpy
from .inputs import ConfiguredSignals, rng

RESOURCES = ("nurse", "gp", "diagnostic", "specialist")


def review_priority(stage, urgency=None):
    """Only actual review stages receive priority; no reference-label access.

    Hypothetical alerts have no clinical urgency and receive ordinary review
    priority. Active service is never interrupted; equal priorities remain FIFO.
    """
    if stage in ("review", "review_followup", "review_symptom_change"):
        return -2 if urgency == "urgent" else -1
    return 0


def validate(config):
    def number(v, name, lower=0, upper=float("inf"), strict=False):
        if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or v < lower or v > upper or (strict and v == lower):
            raise ValueError(f"Invalid {name}: {v}")
    number(config["duration"], "duration", strict=True)
    number(config["warmup"], "warmup", upper=config["duration"])
    if config["warmup"] >= config["duration"]:
        raise ValueError("warmup must be less than duration")
    number(config["arrival_rate"], "arrival_rate", strict=True)
    number(config["prevalence"], "prevalence", upper=1)
    if not config["seeds"] or any(type(s) is not int for s in config["seeds"]) or len(set(config["seeds"])) != len(config["seeds"]):
        raise ValueError("Provide unique integer seeds; number of seeds is replication count")
    for name in RESOURCES:
        if type(config["capacities"][name]) is not int or config["capacities"][name] < 1:
            raise ValueError(f"{name} capacity must be a positive integer")
    for name in (*RESOURCES, "review"):
        for key in ("mean", "cv"):
            number(config["service"][name][key], f"service.{name}.{key}")
    for name, value in config["routing"].items():
        number(value, f"routing.{name}", upper=1)
    for name, value in config["delays"].items():
        number(value, f"delays.{name}")
    for name, value in config["signal"].items():
        number(value, f"signal.{name}", upper=1 if name in ("tpr", "fpr", "review_probability", "escalation_probability") else float("inf"))


    if config.get("review_queue", "fifo") not in ("fifo", "priority"):
        raise ValueError("review_queue must be fifo or priority")
    for name, value in config.get("real_review_policy", {}).items():
        if name not in ("urgent", "review"):
            raise ValueError("Real review policy supports urgent/review categories only")
        number(value, f"real_review_policy.{name}", upper=1)
    if "workflow" in config:
        w = config["workflow"]
        required = ("followup_probability", "monitor_probability", "review_followup_probability",
                    "change_probability_relevant", "change_probability_other", "change_probability_unknown",
                    "change_investigation_relevant", "change_investigation_other", "change_investigation_unknown",
                    "repeat_probability", "avoidable_repeat_rate", "duplicate_flag_tpr", "duplicate_flag_fpr",
                    "selective_review_probability", "clinician_cancel_probability", "symptom_change_delay", "repeat_delay")
        for name in required:
            if name not in w:
                raise ValueError(f"Missing workflow.{name}")
            number(w[name], f"workflow.{name}", upper=float("inf") if name.endswith("delay") else 1)
        if w["followup_probability"] + w["monitor_probability"] > 1:
            raise ValueError("followup_probability + monitor_probability must not exceed 1")
        for key in ("mean", "cv"):
            number(config["service"].get("optimization_review", config["service"]["review"])[key], f"optimization_review.{key}")


def service_time(config, seed, patient, stage):
    service = {"gp_followup": "gp", "gp_change": "gp", "diagnostic_repeat": "diagnostic", "optimization_review": "optimization_review"}.get(stage, stage)
    spec = config["service"].get(service, config["service"]["review"])
    mean, cv = spec["mean"], spec["cv"]
    if not mean or not cv:
        return mean
    sigma = math.sqrt(math.log1p(cv * cv))
    return rng(seed, patient.patient_id, f"service:{stage}").lognormvariate(math.log(mean) - sigma * sigma / 2, sigma)


def simulate(config, patients, seed, assisted=False, signals=None, *, model=None):
    validate(config)
    if len({p.patient_id for p in patients}) != len(patients):
        raise ValueError("Duplicate patient identifiers")
    model = model or ("B" if assisted else "A")
    if model not in ("A", "B", "C", "D"):
        raise ValueError("model must be A, B, C or D")
    assisted = model != "A"
    real_mode = config.get("signal_mode", "hypothetical") == "real_model"
    if config.get("signal_mode", "hypothetical") not in ("hypothetical", "real_model"):
        raise ValueError("Unknown signal_mode")
    if real_mode and getattr(signals, "mode", None) != "real_model":
        raise ValueError("real_model requires validated real predictions; random fallback is forbidden")
    if real_mode and model == "B":
        raise ValueError("Integrated real_model compares A/C/D; B is the historical hypothetical benchmark")
    workflow = config.get("workflow")
    env = simpy.Environment()
    resources = {name: (simpy.PriorityResource if name == "gp" and config.get("review_queue") == "priority" else simpy.Resource)(env, capacity=config["capacities"][name]) for name in RESOURCES}
    signals = signals or ConfiguredSignals(config["signal"])
    events, states, rows = [], [], {}

    def snapshot(name):
        r = resources[name]
        states.append({"time": env.now, "resource": name, "busy": r.count, "queue": len(r.queue)})

    for name in resources:
        snapshot(name)

    def event(p, stage, kind):
        events.append({"patient_id": p.patient_id, "time": env.now, "stage": stage, "event": kind})

    def serve(p, stage, resource, duration, urgency=None):
        row = rows[p.patient_id]
        event(p, stage, "queue_enter")
        if stage + "_queue" in row:
            raise RuntimeError(f"Duplicate service stage {stage} for {p.patient_id}")
        row[stage + "_queue"] = env.now
        if resource == "gp" and config.get("review_queue") == "priority":
            priority = review_priority(stage, urgency or row.get("signal_urgency"))
            row[stage + "_priority"] = priority
            req = resources[resource].request(priority=priority)
        else:
            req = resources[resource].request()
        snapshot(resource)
        yield req
        snapshot(resource)
        row[stage + "_start"] = env.now
        event(p, stage, "service_start")
        yield env.timeout(duration)
        row[stage + "_end"] = env.now
        event(p, stage, "service_end")
        resources[resource].release(req)
        snapshot(resource)

    def draw(p, channel):
        return rng(seed, p.patient_id, channel).random()

    def reference_plan(p):
        # Generative clinical behavior shared across all arms; NOT a model input.
        # Reference labels determine hypothetical observed clinical decisions here.
        label = "unknown" if p.relevant is None else "relevant" if p.relevant else "other"
        route = config["routing"]
        plan = {
            "baseline_initial_investigation": draw(p, "initial") < route[f"initial_{label}"],
            "baseline_followup_investigation": draw(p, "followup") < route[f"followup_{label}"],
            "baseline_referral": draw(p, "referral") < route[f"referral_{label}"],
            "baseline_plan": "followup",
            "symptom_change": False,
            "change_investigation": False,
            "repeat_planned": False,
            "repeat_avoidable_reference": False,
            "repeat_duplicate_evidence": False,
        }
        if workflow:
            u = draw(p, "plan")
            plan["baseline_plan"] = ("followup" if u < workflow["followup_probability"] else
                "monitor" if u < workflow["followup_probability"] + workflow["monitor_probability"] else "discharge")
            plan["symptom_change"] = draw(p, "symptom_change") < workflow[f"change_probability_{label}"]
            plan["change_investigation"] = draw(p, "change_investigation") < workflow[f"change_investigation_{label}"]
            plan["repeat_planned"] = draw(p, "repeat_planned") < workflow["repeat_probability"]
            plan["repeat_avoidable_reference"] = draw(p, "repeat_avoidable") < workflow["avoidable_repeat_rate"]
            # An imperfect observable duplicate-evidence flag, never direct access
            # to reference relevance/avoidability in the intervention policy.
            rate = workflow["duplicate_flag_tpr"] if plan["repeat_avoidable_reference"] else workflow["duplicate_flag_fpr"]
            plan["repeat_duplicate_evidence"] = draw(p, "duplicate_evidence") < rate
        return plan

    def obtain_signal(p, row):
        row["signal_time"] = env.now
        row["signal"] = signals.signal(p, seed)
        if real_mode:
            entry = signals.initial(p)
            row["real_predictions_used"].append({"decision_id": "initial", "time": env.now,
                "input_sha256": entry["input_sha256"], "response_sha256": entry["response_sha256"],
                "recommendation": entry["recommendation"]})
            row["signal_urgency"] = entry["recommendation"]["urgency"]
        if row["signal"] is not None and type(row["signal"]) is not bool:
            raise ValueError("Signal provider must return boolean or None")

    def selection_probability(row):
        if real_mode:
            policy = config.get("real_review_policy", {"urgent": 1., "review": .65})
            return policy.get(row.get("signal_urgency", "review"), 0.)
        return (workflow or {}).get("selective_review_probability", 1)

    def later_review(p, row, stage, indicated):
        if not real_mode or model == "A":
            return indicated
        entry = signals.later_decision(p, stage, env.now - p.arrival)
        if entry is None:
            return indicated
        recommendation = entry["recommendation"]
        row["real_predictions_used"].append({"decision_id": stage, "time": env.now,
            "input_sha256": entry["input_sha256"], "response_sha256": entry["response_sha256"],
            "recommendation": recommendation})
        if indicated or not recommendation['review_signal']:
            return indicated
        probability = config["signal"]["review_probability"]
        if model == "D":
            probability *= config.get("real_review_policy", {"urgent": 1., "review": .65}).get(recommendation['urgency'], 0.)
        if draw(p, "review:"+stage) >= probability:
            return indicated
        yield env.timeout(config["signal"]["processing_delay"])
        service = "review_"+stage
        yield env.process(serve(p, service, "gp", service_time(config, seed, p, service), urgency=recommendation["urgency"]))
        escalated = draw(p, "escalation:"+stage) < config["signal"]["escalation_probability"]
        row[service+"_escalated"] = escalated
        return escalated

    def review(p, row):
        yield env.process(serve(p, "review", "gp", service_time(config, seed, p, "review")))
        row["escalated"] = draw(p, "escalation") < config["signal"]["escalation_probability"]
        row["review_action"] = "investigate" if row["escalated"] else "retain"
        if workflow and not row["escalated"] and draw(p, "review_followup") < workflow["review_followup_probability"]:
            row["review_action"] = "followup"

    def pathway(p):
        yield env.timeout(p.arrival)
        plan = reference_plan(p)
        row = {**asdict(p), **plan, "signal": None, "escalated": False, "complete": False,
               "repeat_avoided": False, "review_action": "none", "selective_review_skipped": False, "real_predictions_used": []}
        rows[p.patient_id] = row
        event(p, "pathway", "arrival")
        yield env.process(serve(p, "nurse", "nurse", service_time(config, seed, p, "nurse")))
        # B exactly preserves the original timing, service savings and RNG channels.
        if model == "B":
            obtain_signal(p, row)
            if row["signal"]:
                yield env.timeout(config["signal"]["processing_delay"])
        gp_duration = service_time(config, seed, p, "gp")
        if model == "B" and row["signal"]:
            gp_duration = max(0, gp_duration - config["signal"]["gp_time_saved"])
        yield env.process(serve(p, "gp", "gp", gp_duration))
        investigate = plan["baseline_initial_investigation"]
        # The initial clinician decision is fixed before C/D obtain a signal.
        row["baseline_decision_time"] = env.now
        if investigate:
            row["first_indication"] = env.now
        if model in ("C", "D"):
            obtain_signal(p, row)
        needs_review = row["signal"] and (model == "B" or not investigate)
        if needs_review and draw(p, "review") < config["signal"]["review_probability"]:
            if model == "D" and draw(p, "selective_review") >= selection_probability(row):
                row["selective_review_skipped"] = True
                row["selective_skip_time"] = env.now
            else:
                if model in ("C", "D"):
                    yield env.timeout(config["signal"]["processing_delay"])
                yield env.process(review(p, row))
        if not investigate and row["escalated"]:
            row["first_indication"] = env.now
            investigate = True
        if not investigate:
            actual_plan = "followup" if row["review_action"] == "followup" else plan["baseline_plan"]
            row["actual_plan"] = actual_plan
            if actual_plan == "followup":
                yield env.timeout(config["delays"]["followup"])
                yield env.process(serve(p, "gp_followup", "gp", service_time(config, seed, p, "gp_followup")))
                investigate = plan["baseline_followup_investigation"]
                if real_mode:
                    investigate = yield env.process(later_review(p, row, "followup", investigate))
            else:
                event(p, "pathway", "safety_net_monitoring" if actual_plan == "monitor" else "discharge_with_safety_net")
            if not investigate and plan["symptom_change"]:
                yield env.timeout(workflow["symptom_change_delay"])
                event(p, "pathway", "symptom_change")
                yield env.process(serve(p, "gp_change", "gp", service_time(config, seed, p, "gp_change")))
                investigate = plan["change_investigation"]
                if real_mode:
                    investigate = yield env.process(later_review(p, row, "symptom_change", investigate))
            if investigate:
                row["first_indication"] = env.now
        if investigate:
            yield env.timeout(config["delays"]["investigation"])
            yield env.process(serve(p, "diagnostic", "diagnostic", service_time(config, seed, p, "diagnostic")))
            if plan["repeat_planned"]:
                yield env.timeout(workflow["repeat_delay"])
                if model == "D" and not real_mode and plan["repeat_duplicate_evidence"]:
                    yield env.process(serve(p, "optimization_review", "gp", service_time(config, seed, p, "optimization_review")))
                    row["repeat_avoided"] = draw(p, "repeat_cancel") < workflow["clinician_cancel_probability"]
                    event(p, "diagnostic_repeat", "clinician_cancel" if row["repeat_avoided"] else "clinician_retain")
                if not row["repeat_avoided"]:
                    yield env.process(serve(p, "diagnostic_repeat", "diagnostic", service_time(config, seed, p, "diagnostic_repeat")))
            if plan["baseline_referral"]:
                row["referral"] = env.now
                event(p, "specialist", "referral")
                yield env.timeout(config["delays"]["specialist"])
                yield env.process(serve(p, "specialist", "specialist", service_time(config, seed, p, "specialist")))
                yield env.timeout(config["delays"]["diagnosis"])
                row["diagnosis"] = env.now
                event(p, "pathway", "diagnosis")
                if p.relevant is True and draw(p, "treatment") < config["routing"]["treatment_relevant"]:
                    yield env.timeout(config["delays"]["treatment"])
                    row["treatment"] = env.now
                    event(p, "pathway", "treatment")
        row["complete"] = True
        row["pathway_exit"] = env.now
        event(p, "pathway", "exit")

    for p in sorted(patients, key=lambda p: (p.arrival, p.patient_id)):
        env.process(pathway(p))
    env.run(until=config["duration"])
    for name in resources:
        snapshot(name)
    return {"scenario": {"A": "baseline", "B": "assisted", "C": "nonblocking", "D": "optimized"}[model], "model": model, "seed": seed,
            "capacities": dict(config["capacities"]), "patients": list(rows.values()), "events": events,
            "resource_states": states, "excluded_arrivals": sum(p.arrival >= config["duration"] for p in patients)}
