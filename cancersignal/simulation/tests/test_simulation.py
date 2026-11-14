from copy import deepcopy
from dataclasses import asdict
import json
from pathlib import Path
import tempfile
import unittest
from cancersignal_sim.cli import experiment
from cancersignal_sim.engine import simulate, validate
from cancersignal_sim.inputs import Patient, adapt_seed, attach_predictions, generate, load_patients
from cancersignal_sim.reporting import metrics

ROOT = Path(__file__).resolve().parents[1]


class SimulationTests(unittest.TestCase):
    def setUp(self):
        self.c = json.loads((ROOT / "config/demo.json").read_text())
        self.c.update(duration=80, warmup=0, arrival_rate=2, seeds=[11, 22])

    def patients(self, relevant=False, n=3):
        return [Patient(str(i), 0, relevant, "test reference") for i in range(n)]

    def test_reproducible(self):
        self.assertEqual(experiment(self.c), experiment(self.c))

    def test_paired_population_and_capacities(self):
        report = experiment(self.c)
        for a, b in zip(report["runs"][::2], report["runs"][1::2]):
            self.assertEqual(a["capacities"], b["capacities"])
            self.assertEqual([(p["patient_id"], p["arrival"], p["relevant"]) for p in a["patients"]], [(p["patient_id"], p["arrival"], p["relevant"]) for p in b["patients"]])

    def test_zero_signal_identical_events(self):
        self.c["signal"].update(tpr=0, fpr=0)
        p = generate(self.c, 11)
        a = simulate(self.c, p, 11)
        b = simulate(self.c, p, 11, True)
        self.assertEqual(a["events"], b["events"])

    def test_analytical_fifo(self):
        self.c["capacities"]["gp"] = 1
        self.c["service"]["nurse"] = {"mean": 0, "cv": 0}
        self.c["service"]["gp"] = {"mean": 1, "cv": 0}
        run = simulate(self.c, self.patients(), 11)
        self.assertEqual([p["gp_start"] for p in run["patients"]], [0, 1, 2])
        self.assertEqual([p["gp_end"] for p in run["patients"]], [1, 2, 3])

    def test_event_order_and_resource_limits(self):
        for assisted in (False, True):
            run = simulate(self.c, generate(self.c, 11), 11, assisted)
            for p in run["patients"]:
                for stage in ("nurse", "gp", "review", "gp_followup", "diagnostic", "specialist"):
                    if stage + "_start" in p:
                        self.assertGreaterEqual(p[stage + "_start"], p[stage + "_queue"])
                        self.assertGreaterEqual(p[stage + "_queue"], p["arrival"])
                    if stage + "_end" in p:
                        self.assertGreaterEqual(p[stage + "_end"], p[stage + "_start"])
                if "specialist_start" in p:
                    self.assertGreaterEqual(p["specialist_start"], p["diagnostic_end"])
                if "treatment" in p:
                    self.assertGreaterEqual(p["treatment"], p["diagnosis"])
            self.assertEqual(len(run["patients"]), len({e["patient_id"] for e in run["events"] if e["event"] == "arrival"}))
            for s in run["resource_states"]:
                self.assertTrue(0 <= s["busy"] <= self.c["capacities"][s["resource"]])
                self.assertGreaterEqual(s["queue"], 0)

    def test_false_positives_consume_gp(self):
        self.c["signal"].update(fpr=1, review_probability=1, escalation_probability=0, gp_time_saved=0)
        self.c["service"]["review"] = {"mean": .5, "cv": 0}
        run = simulate(self.c, self.patients(), 11, True)
        self.assertEqual(metrics(run, self.c)["overall"]["false_positive_reviews"], 3)
        self.assertAlmostEqual(sum(p["review_end"] - p["review_start"] for p in run["patients"]), 1.5)
        self.assertTrue(all(not p["escalated"] for p in run["patients"]))

    def test_false_positive_review_can_delay_other_patients(self):
        self.c["capacities"]["gp"] = 1
        self.c["service"]["nurse"] = {"mean": 0, "cv": 0}
        self.c["service"]["gp"] = {"mean": 1, "cv": 0}
        self.c["service"]["review"] = {"mean": 3, "cv": 0}
        self.c["signal"].update(fpr=1, processing_delay=0, review_probability=1, escalation_probability=0, gp_time_saved=0)
        p = [Patient("first", 0, False, "test"), Patient("other", 1.5, False, "test")]
        a = simulate(self.c, p, 1)
        b = simulate(self.c, p, 1, True)
        self.assertGreater(b["patients"][1]["gp_start"], a["patients"][1]["gp_start"])
        self.assertEqual(metrics(b, self.c)["review_service_days"], 6)

    def test_false_negatives_can_still_receive_usual_care(self):
        self.c["signal"]["tpr"] = 0
        self.c["routing"]["initial_relevant"] = 1
        run = simulate(self.c, self.patients(True), 11, True)
        m = metrics(run, self.c)["overall"]
        self.assertEqual(m["false_negatives"], 3)
        self.assertEqual(m["reviews_started"], 0)
        self.assertEqual(m["investigation"]["n"], 3)

    def test_horizon_and_warmup(self):
        self.c.update(duration=2, warmup=1)
        self.c["service"]["nurse"] = {"mean": 10, "cv": 0}
        p = [Patient("early", 0), Patient("late", 1.5), Patient("excluded", 2)]
        run = simulate(self.c, p, 11)
        self.assertEqual(run["excluded_arrivals"], 1)
        m = metrics(run, self.c)
        self.assertEqual(m["overall"]["patients"], 1)
        self.assertEqual(m["overall"]["unfinished"], 1)
        self.assertAlmostEqual(m["resources"]["nurse"]["utilization"], .75)

    def test_adapter_preserves_unknown_labels(self):
        p = adapt_seed(ROOT.parent)
        self.assertEqual(len(p), 8)
        self.assertTrue(all(row.relevant is None for row in p))
        run = simulate(self.c, p, 11, True)
        self.assertTrue(all(row["signal"] is None for row in run["patients"]))
        self.assertEqual(p[0].clinical_observations[1]["numeric_value"], 132)

    def test_prediction_is_not_truth_and_future_rejected(self):
        p = Patient("p", 0, as_of="2026-02-12T10:00:00+00:00")
        pred = dict(patient_id="p", prediction_type="review_signal", value=True, model_name="test", model_version="1", as_of=p.as_of)
        attach_predictions([p], [pred])
        self.assertIsNone(p.relevant)
        self.assertTrue(simulate(self.c, [p], 11, True)["patients"][0]["signal"])
        pred["as_of"] = "2027-01-01T00:00:00+00:00"
        with self.assertRaisesRegex(ValueError, "available"):
            attach_predictions([p], [pred])

    def test_validation(self):
        for key, value in [("duration", -1), ("warmup", 80), ("prevalence", 2)]:
            c = deepcopy(self.c)
            c[key] = value
            with self.assertRaises(ValueError):
                validate(c)
        with self.assertRaises(ValueError):
            Patient("p", 0, True)
        with self.assertRaises(ValueError):
            simulate(self.c, [Patient("p", 0), Patient("p", 0)], 1)

    def test_roundtrip(self):
        p = generate(self.c, 11)
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "patients.json"
            f.write_text(json.dumps([asdict(x) for x in p]))
            self.assertEqual(p, load_patients(f))


if __name__ == "__main__":
    unittest.main()
