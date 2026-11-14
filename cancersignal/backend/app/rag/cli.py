"""Independent RAG CLI: python -m app.rag.cli --help."""
import argparse
from dataclasses import asdict
import json
from pathlib import Path
import sys
from uuid import UUID

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.contracts.common import PatientScope
from app.db.session import get_engine
from app.models import Observation
from app.rag.benchmark import run_benchmark
from app.rag.embeddings import LocalE5Embedder, MODEL_REVISION
from app.rag.engine import RetrievalEngine, RetrievalOptions
from app.rag.indexing import index_patient
from app.rag.repository import PatientRepository


def main():
    parser = argparse.ArgumentParser(description="Patient-isolated synthetic RAG retrieval and embedding tools")
    parser.add_argument("command", choices=("query", "structured", "index", "benchmark"))
    parser.add_argument("--patient-id", type=UUID)
    parser.add_argument("--note-id", type=UUID)
    parser.add_argument("--query", default="")
    parser.add_argument("--as-of")
    parser.add_argument("--observed-since")
    parser.add_argument("--recorded-before")
    parser.add_argument("--code", action="append")
    parser.add_argument("--mode", choices=("auto", "complete", "lexical", "dense", "hybrid"), default="auto")
    parser.add_argument("--top-k", type=int, default=3)
    parser.add_argument("--max-source-chars", type=int, default=32000)
    parser.add_argument("--dense", action="store_true", help="Enable local dense embeddings for the benchmark or auto retrieval")
    parser.add_argument("--download", action="store_true", help="Allow downloading the pinned model; otherwise use cached local files only")
    parser.add_argument("--revision", default=MODEL_REVISION)
    parser.add_argument("--model-cache", default=str(Path(sys.prefix) / "rag-model-cache"))
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.command != "benchmark" and args.patient_id is None:
        parser.error("--patient-id is required")
    try:
        use_embedding = args.command == "index" or args.mode in ("dense", "hybrid") or args.dense
        embedder = LocalE5Embedder(revision=args.revision, cache_dir=args.model_cache,
                                  local_files_only=not args.download) if use_embedding else None
        with Session(get_engine()) as session:
            if args.command == "benchmark":
                # No fixture or benchmark cache writes persist in the developer database.
                with session.begin():
                    result = run_benchmark(session, embedder=embedder, k=args.top_k, max_source_chars=args.max_source_chars)
                    session.rollback()
            else:
                if args.patient_id is None:
                    parser.error("--patient-id is required")
                if args.command == "index":
                    result = index_patient(session, args.patient_id, embedder, force=args.force)
                    session.commit()
                else:
                    query, cutoff = args.query, args.as_of
                    if args.note_id:
                        note = session.get(Observation, args.note_id)
                        if note is None or note.patient_id != args.patient_id or note.observation_type != "clinical_note" or not note.text:
                            raise ValueError("Input note must exist and belong to this patient.")
                        query, cutoff = query or note.text, note.observed_at
                    if cutoff is None:
                        parser.error("Supply --as-of or --note-id")
                    scope = PatientScope(patient_id=args.patient_id, as_of=cutoff,
                        observed_since=args.observed_since, recorded_before=args.recorded_before)
                    repository = PatientRepository(session)
                    if args.command == "structured":
                        result = repository.structured(scope=scope, codes=tuple(args.code) if args.code else None).model_dump(mode="json")
                    else:
                        output = RetrievalEngine(repository, embedder=embedder,
                            options=RetrievalOptions(mode=args.mode, top_k=args.top_k, max_source_chars=args.max_source_chars)).search(scope=scope, query=query)
                        result = {"context": output.context.model_dump(mode="json"), "diagnostics": asdict(output.diagnostics)}
        payload = json.dumps(result, indent=2, ensure_ascii=False)
        if args.output:
            args.output.write_text(payload + "\n")
        else:
            print(payload)
    except SQLAlchemyError:
        raise SystemExit("RAG database operation failed. Check PostgreSQL, .env, and Alembic migrations.") from None
    except (ValueError, RuntimeError) as error:
        raise SystemExit(str(error)) from None


if __name__ == "__main__":
    main()
