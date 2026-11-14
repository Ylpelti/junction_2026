"""SimPy FIFO resources, finite observation horizon, common random numbers."""
from dataclasses import asdict
import math
import simpy
from .inputs import ConfiguredSignals, rng

RESOURCES = ("nurse", "gp", "diagnostic", "specialist")


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


def service_time(config, seed, patient, stage):
    spec = config["service"]["gp" if stage == "gp_followup" else stage]
    mean, cv = spec["mean"], spec["cv"]
    if not mean or not cv:
        return mean
    sigma = math.sqrt(math.log1p(cv * cv))
    return rng(seed, patient.patient_id, f"service:{stage}").lognormvariate(math.log(mean) - sigma * sigma / 2, sigma)


def simulate(config, patients, seed, assisted=False, signals=None):
    validate(config)
    if len({p.patient_id for p in patients}) != len(patients):
        raise ValueError("Duplicate patient identifiers")
    env = simpy.Environment()
    resources = {name: simpy.Resource(env, capacity=config["capacities"][name]) for name in RESOURCES}
    signals = signals or ConfiguredSignals(config["signal"])
    events, states, rows = [], [], {}

    def snapshot(name):
        r = resources[name]
        states.append({"time": env.now, "resource": name, "busy": r.count, "queue": len(r.queue)})

    for name in resources:
        snapshot(name)

    def event(p, stage, kind):
        events.append({"patient_id": p.patient_id, "time": env.now, "stage": stage, "event": kind})

    def serve(p, stage, resource, duration):
        row = rows[p.patient_id]
        event(p, stage, "queue_enter")
        row[stage + "_queue"] = env.now
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

    def pathway(p):
        yield env.timeout(p.arrival)
        row = {**asdict(p), "signal": None, "escalated": False, "complete": False}
        rows[p.patient_id] = row
        event(p, "pathway", "arrival")
        yield env.process(serve(p, "nurse", "nurse", service_time(config, seed, p, "nurse")))
        if assisted:
            row["signal"] = signals.signal(p, seed)
            if row["signal"] is not None and type(row["signal"]) is not bool:
                raise ValueError("Signal provider must return boolean or None")
            if row["signal"]:
                yield env.timeout(config["signal"]["processing_delay"])
        gp_duration = service_time(config, seed, p, "gp")
        # Saving only applies to signalled records; does not add capacity.
        if row["signal"]:
            gp_duration = max(0, gp_duration - config["signal"]["gp_time_saved"])
        yield env.process(serve(p, "gp", "gp", gp_duration))
        if row["signal"] and rng(seed, p.patient_id, "review").random() < config["signal"]["review_probability"]:
            yield env.process(serve(p, "review", "gp", service_time(config, seed, p, "review")))
            row["escalated"] = rng(seed, p.patient_id, "escalation").random() < config["signal"]["escalation_probability"]
        label = "unknown" if p.relevant is None else "relevant" if p.relevant else "other"
        route = config["routing"]
        investigate = rng(seed, p.patient_id, "initial").random() < route[f"initial_{label}"]
        if not investigate and not row["escalated"]:
            yield env.timeout(config["delays"]["followup"])
            yield env.process(serve(p, "gp_followup", "gp", service_time(config, seed, p, "gp_followup")))
            investigate = rng(seed, p.patient_id, "followup").random() < route[f"followup_{label}"]
        if investigate or row["escalated"]:
            yield env.timeout(config["delays"]["investigation"])
            yield env.process(serve(p, "diagnostic", "diagnostic", service_time(config, seed, p, "diagnostic")))
            if rng(seed, p.patient_id, "referral").random() < route[f"referral_{label}"]:
                row["referral"] = env.now
                event(p, "specialist", "referral")
                yield env.timeout(config["delays"]["specialist"])
                yield env.process(serve(p, "specialist", "specialist", service_time(config, seed, p, "specialist")))
                yield env.timeout(config["delays"]["diagnosis"])
                row["diagnosis"] = env.now
                event(p, "pathway", "diagnosis")
                if p.relevant is True and rng(seed, p.patient_id, "treatment").random() < route["treatment_relevant"]:
                    yield env.timeout(config["delays"]["treatment"])
                    row["treatment"] = env.now
                    event(p, "pathway", "treatment")
        row["complete"] = True
        event(p, "pathway", "exit")

    for p in sorted(patients, key=lambda p: (p.arrival, p.patient_id)):
        env.process(pathway(p))
    env.run(until=config["duration"])
    for name in resources:
        snapshot(name)
    return {"scenario": "assisted" if assisted else "baseline", "seed": seed,
            "capacities": dict(config["capacities"]), "patients": list(rows.values()), "events": events,
            "resource_states": states, "excluded_arrivals": sum(p.arrival >= config["duration"] for p in patients)}
