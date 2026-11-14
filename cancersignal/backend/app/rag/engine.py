"""Independent retrieval engine; imports no extraction or reasoning implementation."""
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from hashlib import sha256
import json
import math
from typing import Literal
from uuid import UUID

from app.contracts.clinical_context import RelevanceScore, RetrievedContext, RetrievedObservation
from app.contracts.common import ComponentProvenance, Coverage, MissingInformation
from app.rag.embeddings import checked_vector, source_digest


class RetrievalError(RuntimeError):
    pass


@dataclass(frozen=True)
class RetrievalOptions:
    mode: Literal["auto", "complete", "lexical", "dense", "hybrid"] = "auto"
    top_k: int = 5
    max_source_chars: int = 32000
    expand_timeline: bool = True
    rrf_constant: int = 60

    def __post_init__(self):
        if self.mode not in ("auto", "complete", "lexical", "dense", "hybrid"):
            raise ValueError("Unknown retrieval mode.")
        if self.top_k < 1 or self.max_source_chars < 1 or self.rrf_constant < 1:
            raise ValueError("Retrieval limits must be positive.")


@dataclass
class RetrievalDiagnostics:
    requested_mode: str
    effective_mode: str
    primary_ranked_ids: list[str] = field(default_factory=list)
    lexical_scores: dict[str, float] = field(default_factory=dict)
    semantic_scores: dict[str, float] = field(default_factory=dict)
    fused_scores: dict[str, float] = field(default_factory=dict)
    expansion_reasons: dict[str, list[str]] = field(default_factory=dict)
    best_chunk_offsets: dict[str, tuple[int | None, int | None]] = field(default_factory=dict)
    embedding_model: str | None = None
    missing_embedding_ids: list[str] = field(default_factory=list)
    source_chars: int = 0
    eligible_count: int = 0


@dataclass
class RetrievalOutput:
    context: RetrievedContext
    diagnostics: RetrievalDiagnostics


def rank(scores, sources):
    return sorted(scores, key=lambda identifier: (-scores[identifier], sources[identifier].observed_at, str(identifier)))


def source_size(source):
    return len(source.model_dump_json())


def expand(seed, sources):
    """Conservative chronology, not clinical interpretation or inferred resolution."""
    related = {seed.id: ["primary_match"]}
    later_contacts = sorted((row for row in sources if row.observed_at > seed.observed_at
                             and row.observation_type == "clinical_note"), key=lambda row: (row.observed_at, str(row.id)))
    contact_ids = {row.id for row in (*later_contacts[:2], *later_contacts[-1:])}
    for row in sources:
        reasons = []
        if seed.code and row.code == seed.code:
            reasons.append("same_code_history")
        if seed.encounter_id and row.encounter_id == seed.encounter_id:
            reasons.append("same_encounter")
        if row.id in contact_ids:
            reasons.append("next_or_latest_contact")
        if row.observed_at > seed.observed_at and (
                row.observation_type == "investigation" or row.status in ("negated", "resolved", "uncertain")):
            reasons.append("later_investigation_or_state")
        if reasons:
            related.setdefault(row.id, []).extend(reasons)
    return related


class RetrievalEngine:
    def __init__(self, repository, *, embedder=None, options=None):
        self.repository = repository
        self.embedder = embedder
        self.options = options or RetrievalOptions()

    def __call__(self, *, scope, query):
        return self.search(scope=scope, query=query).context

    def search(self, *, scope, query) -> RetrievalOutput:
        if not isinstance(query, str):
            raise ValueError("query must be a string")
        sources = self.repository.sources(scope)
        if any(not scope.permits(source) for source in sources):
            raise RetrievalError("Repository returned a source outside patient/time scope.")
        by_id = {row.id: row for row in sources}
        if len(by_id) != len(sources):
            raise RetrievalError("Repository returned duplicate original observation IDs.")
        options = self.options
        size = sum(source_size(row) for row in sources)
        mode = options.mode
        if mode == "auto":
            mode = "complete" if size <= options.max_source_chars else ("hybrid" if self.embedder else "lexical")
        debug = RetrievalDiagnostics(requested_mode=options.mode, effective_mode=mode, eligible_count=len(sources))
        messages = []
        scores = {}
        lexical, semantic = {}, {}
        if mode == "complete":
            if size > options.max_source_chars:
                raise RetrievalError("Complete history exceeds max_source_chars; select a retrieval mode or raise the budget.")
            chosen = set(by_id)
            ordered = [row.id for row in sources]
            debug.primary_ranked_ids = [str(identifier) for identifier in ordered]
        else:
            if mode in ("lexical", "hybrid"):
                lexical = self.repository.lexical_scores(scope, query)
                if not set(lexical).issubset(by_id):
                    raise RetrievalError("Lexical ranking contains out-of-scope IDs.")
                debug.lexical_scores = {str(key): value for key, value in lexical.items()}
            if mode in ("dense", "hybrid"):
                if self.embedder is None:
                    raise RetrievalError("Dense/hybrid retrieval requires an explicit embedding adapter.")
                debug.embedding_model = self.embedder.model_key
                if query.strip():
                    rows = self.repository.dense_chunks(scope, checked_vector(self.embedder.query(query)), self.embedder.model_key)
                    for row in rows:
                        source = by_id.get(row.observation_id)
                        if source is None:
                            raise RetrievalError("Dense ranking contains an out-of-scope ID.")
                        if row.source_digest != source_digest(source):
                            continue  # Changed source: never reuse stale embeddings.
                        if not math.isfinite(float(row.distance)):
                            raise RetrievalError("Cached cosine distance is invalid; reindex this profile.")
                        if source.id not in semantic:
                            semantic[source.id] = 1.0 - float(row.distance)
                            debug.best_chunk_offsets[str(source.id)] = (row.start_offset, row.end_offset)
                debug.semantic_scores = {str(key): value for key, value in semantic.items()}
                debug.missing_embedding_ids = sorted(str(key) for key in set(by_id) - set(semantic))
                if debug.missing_embedding_ids:
                    messages.append(MissingInformation(code="missing_or_stale_embeddings",
                        description=f"{len(debug.missing_embedding_ids)} eligible records lack current embeddings for this profile."))
            if mode == "hybrid":
                for branch in (lexical, semantic):
                    for position, identifier in enumerate(rank(branch, by_id), 1):
                        scores[identifier] = scores.get(identifier, 0.0) + 1.0 / (options.rrf_constant + position)
                debug.fused_scores = {str(key): value for key, value in scores.items()}
            else:
                scores = lexical if mode == "lexical" else semantic
            ordered = rank(scores, by_id)
            debug.primary_ranked_ids = [str(identifier) for identifier in ordered]
            chosen, used = set(), 0
            for identifier in ordered[:options.top_k]:
                group = expand(by_id[identifier], sources) if options.expand_timeline else {identifier: ["primary_match"]}
                extra = set(group) - chosen
                cost = sum(source_size(by_id[key]) for key in extra)
                if used + cost > options.max_source_chars:
                    messages.append(MissingInformation(code="timeline_group_exceeds_budget",
                        description="A match and its timeline context could not fit together; the group was omitted."))
                    continue
                chosen.update(extra)
                used += cost
                for key, reasons in group.items():
                    debug.expansion_reasons.setdefault(str(key), []).extend(reasons)
            if len(chosen) < len(sources):
                messages.append(MissingInformation(code="selective_history",
                    description="This is selected history, not the complete numerical or clinical record."))
        # Always provide originals in chronological order, including negative and resolved states.
        selected = sorted((by_id[key] for key in chosen), key=lambda row: (row.observed_at, row.recorded_at, str(row.id)))
        debug.source_chars = sum(source_size(row) for row in selected)
        if len(selected) == len(sources):
            coverage = Coverage(status="complete", eligible_count=len(sources), missing_information=tuple(messages))
        else:
            coverage = Coverage(status="partial", eligible_count=len(sources), missing_information=tuple(messages))
        method = "structured" if mode == "complete" else ("full_text" if mode == "lexical" else "semantic" if mode == "dense" else "hybrid")
        metric = "reciprocal_rank_fusion" if mode == "hybrid" else "postgres_fts_plus_exact_value" if mode == "lexical" else "cosine_similarity"
        configuration = {**asdict(options), "effective_mode": mode, "model": debug.embedding_model}
        context = RetrievedContext(patient_id=scope.patient_id, as_of=scope.as_of, observed_since=scope.observed_since,
            recorded_before=scope.recorded_before, query=query, coverage=coverage,
            generated_at=datetime.now(timezone.utc),
            retrieval=ComponentProvenance(name="cancersignal-patient-retrieval", version="1.0", method=method,
                model=debug.embedding_model, configuration_digest=sha256(json.dumps(configuration, sort_keys=True).encode()).hexdigest()),
            retrieved_observations=tuple(RetrievedObservation(source=row, retrieval_method=method,
                relevance=RelevanceScore(value=scores[row.id], metric=metric) if row.id in scores else None) for row in selected))
        return RetrievalOutput(context=context, diagnostics=debug)
