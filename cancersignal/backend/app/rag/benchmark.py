"""Small, explicitly synthetic retrieval benchmark; labels never enter retrieval."""
from datetime import datetime, timezone
import json
from pathlib import Path
from time import perf_counter

from sqlalchemy.dialects.postgresql import insert

from app.contracts.common import PatientScope
from app.db.seed import seed, synthetic_id
from app.models import Observation
from app.rag.engine import RetrievalEngine, RetrievalOptions
from app.rag.indexing import index_patient
from app.rag.repository import PatientRepository

FIXTURES = Path(__file__).parent / "evaluation"


def prepare_fixture(session):
    seed(session)
    for entry in json.loads((FIXTURES / "records.json").read_text()):
        when = datetime(entry["year"], 3, 1, tzinfo=timezone.utc)
        session.execute(insert(Observation).values(id=synthetic_id(entry["key"]),
            patient_id=synthetic_id(entry["patient_key"]), observed_at=when, recorded_at=when,
            observation_type=entry["observation_type"], text=entry["text"], code=entry.get("code"), status=entry["status"])
            .on_conflict_do_nothing(index_elements=["id"]))


def run_benchmark(session, *, embedder=None, k=3, max_source_chars=32000):
    prepare_fixture(session)
    cases = json.loads((FIXTURES / "labels.json").read_text())
    indexed_ms = None
    if embedder:
        start = perf_counter()
        for index in range(8):
            index_patient(session, synthetic_id(f"patient/{index}"), embedder)
        indexed_ms = (perf_counter() - start) * 1000
    repo = PatientRepository(session)
    rows = []
    for case in cases:
        scope = PatientScope(patient_id=synthetic_id(case["patient_key"]), as_of=case["as_of"])
        required = {str(synthetic_id(key)) for key in case["required"]}
        followup = {str(synthetic_id(key)) for key in case["followup"]}
        for mode in ("complete", "lexical", "dense", "hybrid"):
            if mode in ("dense", "hybrid") and embedder is None:
                rows.append({"scenario": case["name"], "mode": mode, "status": "not_run", "reason": "No embedding adapter requested."})
                continue
            engine = RetrievalEngine(repo, embedder=embedder,
                options=RetrievalOptions(mode=mode, top_k=k, max_source_chars=max_source_chars))
            start = perf_counter()
            output = engine.search(scope=scope, query=case["query"])
            latency = (perf_counter() - start) * 1000
            returned = {str(hit.source.id) for hit in output.context.retrieved_observations}
            primary = output.diagnostics.primary_ranked_ids
            if mode == "complete":
                primary = [str(hit.source.id) for hit in output.context.retrieved_observations]
            top = set(primary[:k])
            rows.append(dict(scenario=case["name"], mode=mode, status="ok", k=k,
                recall_at_k=len(top & required) / len(required), precision_at_k=len(top & required) / k,
                context_recall=len(returned & required) / len(required), missing_required=sorted(required - returned),
                followup_preservation=len(returned & followup) / len(followup) if followup else None,
                patient_isolation_violations=sum(hit.source.patient_id != scope.patient_id for hit in output.context.retrieved_observations),
                latency_ms=round(latency, 3), context_source_count=len(returned),
                source_chars=output.diagnostics.source_chars,
                estimated_tokens=(output.diagnostics.source_chars + 2) // 3,
                coverage=output.context.coverage.status))
    return dict(synthetic_only=True, clinically_validated=False, labels_version="rag-fixture-v1",
        token_estimate="ceil(serialized_source_characters/3), not an actual LLM tokenizer budget",
        baseline_at_k_order="chronological, not query ranked", embedding_profile=embedder.model_key if embedder else None,
        indexing_ms=round(indexed_ms, 3) if indexed_ms is not None else None, results=rows)
