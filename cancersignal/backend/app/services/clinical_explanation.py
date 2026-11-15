"""Presentation boundary; the independent engine owns all English rendering."""
from app.core.config import get_pipeline_settings


def explain_analysis(response, note):
    from app.explanation import ExplanationEngine
    settings = get_pipeline_settings()
    try:
        provider = None
        if settings.explanation == "llm":
            from app.explanation.providers import ChatProvider, ProviderSettings
            provider = ChatProvider(ProviderSettings(_env_file=settings.explanation_env_file),
                                    allow_live=settings.explanation_allow_live)
        engine = ExplanationEngine(provider, cache_dir=settings.explanation_cache_dir)
        result = engine.explain_api(response, input_note=note)
        return result.model_dump(mode="json"), None
    except Exception:
        # Provider/configuration failures must not discard validated clinical outputs.
        # The existing engine handles provider errors; construction failures use its
        # same deterministic path. Invalid input is rejected by both attempts.
        try:
            result = ExplanationEngine().explain_api(response, input_note=note)
            return result.model_dump(mode="json"), "clinical_explanation_provider_unavailable"
        except Exception:
            return None, "clinical_explanation_unavailable"
