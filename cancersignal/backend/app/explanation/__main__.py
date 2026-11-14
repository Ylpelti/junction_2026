"""Offline by default: python -m app.explanation --example PATH."""
import argparse
import json
from pathlib import Path
import sys

from pydantic import ValidationError

from app.contracts.analysis import AnalysisResult
from app.explanation.providers import ChatProvider, ProviderSettings
from app.explanation.schemas import PredictionDisplaySpec
from app.explanation.service import ExplanationEngine, ExplanationInputError


def main():
    parser = argparse.ArgumentParser(description="Synthetic Finnish clinical explanation; offline by default.")
    parser.add_argument("--example", type=Path, required=True)
    parser.add_argument("--api-v1", action="store_true", help="Explain an existing API AnalysisResponse fixture.")
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--allow-live", action="store_true", help="Explicit authorization for this live LLM invocation.")
    parser.add_argument("--env-file", type=Path)
    parser.add_argument("--cache-dir", type=Path)
    args = parser.parse_args()
    if args.live and not args.allow_live:
        parser.error("Live calls require explicit authorization and --allow-live.")
    if args.env_file is not None and not args.env_file.is_file():
        parser.error("The selected environment file does not exist.")
    try:
        example = json.loads(args.example.read_text(encoding="utf-8"))
        if example.get("synthetic") is not True:
            raise ValueError("CLI examples must be explicitly synthetic")
        specs = tuple(PredictionDisplaySpec.model_validate(row) for row in example.get("prediction_display_specs", []))
        provider = ChatProvider(ProviderSettings(_env_file=args.env_file), allow_live=True) if args.live else None
        engine = ExplanationEngine(provider, prediction_specs=specs, cache_dir=args.cache_dir)
        explanation = (engine.explain_api(example["analysis_response"], input_note=example.get("input_note")) if args.api_v1 else
                       engine(AnalysisResult.model_validate(example["analysis_result"])))
    except (OSError, ValueError, ValidationError, ExplanationInputError, KeyError):
        print("Invalid synthetic input or explanation settings; no explanation was generated.", file=sys.stderr)
        return 2
    print(explanation.model_dump_json(indent=2))
    return 1 if explanation.mode == "unavailable" else 0


if __name__ == "__main__":
    raise SystemExit(main())
