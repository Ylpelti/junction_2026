"""Inputs keep observed records, reference labels, and model predictions separate."""
import ast
from dataclasses import asdict, dataclass, field
from datetime import datetime
import hashlib
import json
import math
from pathlib import Path
import random
from typing import Protocol
from uuid import NAMESPACE_URL, uuid5


def rng(seed, patient_id, channel):
    digest = hashlib.sha256(f"{seed}:{patient_id}:{channel}".encode()).digest()
    return random.Random(int.from_bytes(digest[:16], "big"))


@dataclass
class Patient:
    patient_id: str
    arrival: float
    relevant: bool | None = None
    label_source: str | None = None
    cohort: str = "generated"
    region: str = "unspecified"
    group: str = "unspecified"
    clinical_observations: list = field(default_factory=list)
    prediction: dict | None = None
    as_of: str | None = None

    def __post_init__(self):
        if not self.patient_id or not math.isfinite(self.arrival) or self.arrival < 0:
            raise ValueError("Patient identifier and finite nonnegative arrival required")
        if self.relevant is not None and type(self.relevant) is not bool:
            raise ValueError("Reference relevant must be boolean or null")
        if self.relevant is not None and not self.label_source:
            raise ValueError("Reference labels require independent label_source")
        if self.prediction is not None:
            if type(self.prediction.get("review_signal")) is not bool:
                raise ValueError("Prediction requires explicit boolean review_signal")
            if not self.prediction.get("source"):
                raise ValueError("Prediction requires source provenance")
            if not self.as_of or not self.prediction.get("as_of"):
                raise ValueError("Prediction and patient require as_of timestamps")
            cutoff, predicted = datetime.fromisoformat(self.as_of), datetime.fromisoformat(self.prediction["as_of"])
            if cutoff.tzinfo is None or predicted.tzinfo is None or predicted > cutoff:
                raise ValueError("Prediction must be timezone-aware and available by patient as_of")


class SignalProvider(Protocol):
    def signal(self, patient: Patient, seed: int) -> bool | None: ...


class ConfiguredSignals:
    """Replace with measured outputs via this protocol, or per-patient prediction."""
    def __init__(self, config):
        self.config = config

    def signal(self, patient, seed):
        if patient.prediction is not None:
            return patient.prediction["review_signal"]
        if patient.relevant is None:
            return None  # Unknown reference is never imputed from text or prediction.
        rate = self.config["tpr" if patient.relevant else "fpr"]
        return rng(seed, patient.patient_id, "signal").random() < rate


def generate(config, seed):
    arrivals = rng(seed, "population", "arrival")
    now, result = 0.0, []
    while True:
        now += arrivals.expovariate(config["arrival_rate"])
        if now >= config["duration"]:
            return result
        pid = f"synthetic-{len(result):06d}"
        relevant = rng(seed, pid, "reference").random() < config["prevalence"]
        result.append(Patient(pid, now, relevant, "simulation prevalence assumption"))


def load_patients(path):
    rows = json.loads(Path(path).read_text())
    patients = [Patient(**row) for row in rows]
    if len({p.patient_id for p in patients}) != len(patients):
        raise ValueError("Duplicate patient identifiers")
    return patients


def adapt_seed(project, spacing=1.0):
    """Read literal HISTORIES via AST; never import backend or connect to DB."""
    source = Path(project) / "backend/app/db/seed.py"
    tree = ast.parse(source.read_text())
    histories = next(ast.literal_eval(n.value) for n in tree.body
                     if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "HISTORIES" for t in n.targets))
    patients = []
    for i, (scenario, notes, statuses, hb) in enumerate(histories):
        def uid(key):
            return str(uuid5(NAMESPACE_URL, f"https://cancersignal.invalid/synthetic/v1/{key}"))
        observations = []
        for visit, year in enumerate((2020, 2022, 2024, 2026)):
            observations.extend([
                {"id": uid(f"note/{i}/{visit}"), "observed_at": f"{year}-02-12T09:00:00+00:00", "observation_type": "clinical_note", "text": f"SYNTHETIC SOURCE NOTE — {scenario}. {notes[visit]}", "status": statuses[visit]},
                {"id": uid(f"lab/{i}/{visit}"), "observed_at": f"{year}-02-12T09:00:00+00:00", "observation_type": "laboratory", "code": "SYNTHETIC-HB", "numeric_value": hb[visit], "unit": "g/L"}])
        patients.append(Patient(uid(f"patient/{i}"), i * spacing, cohort=scenario,
                                clinical_observations=observations, as_of="2026-02-12T10:00:00+00:00"))
    return patients


def attach_predictions(patients, rows):
    """Explicit model review_signal only; never threshold arbitrary risk scores."""
    by_id = {p.patient_id: p for p in patients}
    seen = set()
    for row in rows:
        pid = row["patient_id"]
        if pid not in by_id or pid in seen:
            raise ValueError(f"Unknown or duplicate prediction patient: {pid}")
        seen.add(pid)
        if row.get("prediction_type") != "review_signal" or type(row.get("value")) is not bool:
            raise ValueError("Only explicit boolean review_signal ModelPrediction outputs supported")
        p = by_id[pid]
        p.prediction = {"review_signal": row["value"], "as_of": row["as_of"],
                        "source": f"{row['model_name']}:{row['model_version']}", "raw": row}
        p.__post_init__()
    return patients
