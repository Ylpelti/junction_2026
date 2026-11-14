from typing import Annotated

from fastapi import Query
from pydantic import AwareDatetime

from app.models.enums import ObservationType
from app.rag.extraction import StructuredSourceExtractor
from app.rag.retrieval import retrieve_context
from app.reasoning.interfaces import AnalysisPipeline
from app.reasoning.trigger_engine import evaluate_triggers


def get_analysis_pipeline() -> AnalysisPipeline:
    return AnalysisPipeline(retrieve=retrieve_context, extractor=StructuredSourceExtractor(), evaluate=evaluate_triggers)


def observation_filters(observation_type: ObservationType | None = None,
                        date_from: AwareDatetime | None = None, date_to: AwareDatetime | None = None,
                        code: Annotated[str | None, Query(max_length=100)] = None):
    return dict(observation_type=observation_type, date_from=date_from, date_to=date_to, code=code)
