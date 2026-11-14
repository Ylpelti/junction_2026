"""python -m app.extraction --example examples/extraction/synthetic.json"""
import argparse
import json
from pathlib import Path
import sys

from pydantic import ValidationError

from app.contracts.clinical_context import RetrievedContext, SourceObservation, StructuredPatientContext
from app.contracts.validation import EvidenceValidationError
from app.extraction.providers import ChatCompletionsProvider, FixtureProvider, ProviderSettings
from app.extraction.service import ClinicalExtractor


def main() -> int:
    parser = argparse.ArgumentParser(description="Standalone synthetic clinical extraction; offline by default.")
    parser.add_argument("--example", type=Path, required=True)
    parser.add_argument("--env-file", type=Path, help="Explicit local provider settings file; no automatic .env discovery.")
    parser.add_argument("--live", action="store_true", help="Use the configured API instead of the hand-authored fixture.")
    parser.add_argument("--allow-live", action="store_true", help="Explicitly authorize this live API invocation.")
    parser.add_argument("--cache-dir", type=Path, help="Optional validated response cache; use an ignored local directory.")
    args = parser.parse_args()
    if args.live and not args.allow_live:
        parser.error("Live calls require --allow-live after explicit authorization.")
    if args.env_file is not None and not args.env_file.is_file():
        parser.error("The specified environment file does not exist or is not a file.")
    try:
        example = json.loads(args.example.read_text(encoding="utf-8"))
        context = RetrievedContext.model_validate(example["context"])
        note = SourceObservation.model_validate(example["input_note"]) if example.get("input_note") else None
        structured = StructuredPatientContext.model_validate(example["structured_context"]) if example.get("structured_context") else None
        provider = (ChatCompletionsProvider(ProviderSettings(_env_file=args.env_file), allow_live=True) if args.live else
                    FixtureProvider(json.dumps(example["synthetic_response"], ensure_ascii=False)))
        batch = ClinicalExtractor(provider, cache_dir=args.cache_dir)(context, input_note=note, structured_context=structured)
    except (OSError, ValueError, KeyError, ValidationError, EvidenceValidationError):
        print("Invalid example or provider configuration; inspect the fixture and EXTRACTION_* settings.", file=sys.stderr)
        return 2
    print(batch.model_dump_json(indent=2))
    return 1 if batch.status == "failed" else 0


if __name__ == "__main__":
    raise SystemExit(main())
