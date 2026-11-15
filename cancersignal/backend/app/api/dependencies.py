from functools import lru_cache
from pathlib import Path
from typing import Annotated

from fastapi import Query
from pydantic import AwareDatetime

from app.core.config import get_pipeline_settings
from app.models.enums import ObservationType
from app.rag.extraction import StructuredSourceExtractor
from app.services.history_retrieval import build_retriever
from app.reasoning.interfaces import AnalysisPipeline
from app.reasoning.trigger_engine import evaluate_triggers


@lru_cache
def build_extractor(extraction: str, env_file: Path | None, allow_live: bool, cache_dir: Path | None, architecture: str = "v1"):
    """One extractor per configuration, reused across requests."""
    if extraction == "off":
        return StructuredSourceExtractor()
    # Imported only when enabled, so the default API never loads the LLM provider code.
    from app.services.llm_extraction import LlmNoteExtractor, build_from_settings
    extractor = LlmNoteExtractor(StructuredSourceExtractor(),
                            build_clinical=build_from_settings(env_file, allow_live, cache_dir, architecture))
    if architecture == "v2":
        extractor.name = "structured-source-demo-v1+clinical-extraction-compact-en-3"
    return extractor


def get_analysis_pipeline() -> AnalysisPipeline:
    settings = get_pipeline_settings()
    extractor = build_extractor(settings.extraction, settings.extraction_env_file,
                                settings.extraction_allow_live, settings.extraction_cache_dir, settings.extraction_architecture)
    return AnalysisPipeline(retrieve=build_retriever(settings), extractor=extractor, evaluate=evaluate_triggers)


def observation_filters(observation_type: ObservationType | None = None,
                        date_from: AwareDatetime | None = None, date_to: AwareDatetime | None = None,
                        code: Annotated[str | None, Query(max_length=100)] = None):
    return dict(observation_type=observation_type, date_from=date_from, date_to=date_to, code=code)
