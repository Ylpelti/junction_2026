"""Optional local embedding adapter and source-preserving token-budgeted chunks."""
from dataclasses import dataclass
from hashlib import sha256
import json
import math
from pathlib import Path
from typing import Protocol

from app.contracts.clinical_context import SourceObservation

MODEL_NAME = "intfloat/multilingual-e5-small"
MODEL_REVISION = "614241f622f53c4eeff9890bdc4f31cfecc418b3"
PREPARATION_VERSION = "e5-source-chunks-v1"


class EmbeddingError(RuntimeError):
    pass


class Embedder(Protocol):
    model_key: str
    max_tokens: int
    def token_count(self, text: str) -> int: ...
    def passages(self, texts: list[str]) -> list[list[float]]: ...
    def query(self, text: str) -> list[float]: ...


def checked_vector(values) -> list[float]:
    vector = [float(value) for value in values]
    if len(vector) != 384 or not all(math.isfinite(value) for value in vector):
        raise EmbeddingError("Embedding must contain 384 finite values.")
    norm = math.sqrt(sum(value * value for value in vector))
    if norm <= 1e-12:
        raise EmbeddingError("A zero vector cannot be used for cosine retrieval.")
    return [value / norm for value in vector]


def source_digest(source: SourceObservation) -> str:
    payload = {"preparation": PREPARATION_VERSION, "source": source.model_dump(mode="json")}
    if source.numeric_value is not None:
        payload["source"]["numeric_value"] = str(source.numeric_value.normalize())
    return sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def source_header(source: SourceObservation) -> str:
    return (f"type: {source.observation_type.value}; code: {source.code or ''}; "
            f"value: {source.numeric_value if source.numeric_value is not None else ''}; unit: {source.unit or ''}\n")


@dataclass(frozen=True)
class Chunk:
    start: int | None
    end: int | None
    passage: str


def chunk_source(source: SourceObservation, embedder: Embedder, overlap_chars: int = 100) -> list[Chunk]:
    """Binary-search safe spans against the actual tokenizer, never silently truncate."""
    header = source_header(source)
    if embedder.token_count("passage: " + header) >= embedder.max_tokens:
        raise EmbeddingError("Source metadata exceeds the embedding token budget.")
    if not source.text:
        return [Chunk(None, None, header)]
    chunks, start = [], 0
    while start < len(source.text):
        low, high = start + 1, len(source.text)
        best = start
        while low <= high:
            end = (low + high) // 2
            if embedder.token_count("passage: " + header + source.text[start:end]) <= embedder.max_tokens:
                best, low = end, end + 1
            else:
                high = end - 1
        if best == start:
            raise EmbeddingError("Cannot fit a source character into the embedding window.")
        chunks.append(Chunk(start, best, header + source.text[start:best]))
        if best == len(source.text):
            break
        start = best - min(overlap_chars, (best - start) // 4)
    return chunks


class LocalE5Embedder:
    max_tokens = 512

    def __init__(self, *, revision: str, cache_dir: str | Path, local_files_only=True, device="cpu"):
        if len(revision) != 40 or any(character not in "0123456789abcdef" for character in revision):
            raise EmbeddingError("Pin the Hugging Face model to a 40-character commit revision.")
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError:
            raise EmbeddingError("Install app/rag/requirements-local.txt for local dense embeddings.") from None
        self.model_key = f"{MODEL_NAME}@{revision}:{PREPARATION_VERSION}"
        try:
            self.model = SentenceTransformer(MODEL_NAME, revision=revision, cache_folder=str(cache_dir),
                device=device, local_files_only=local_files_only, trust_remote_code=False)
        except OSError:
            raise EmbeddingError("Pinned local weights are unavailable. Run the CLI index command with --download once, or check --model-cache.") from None
        dimension = getattr(self.model, "get_embedding_dimension", self.model.get_sentence_embedding_dimension)()
        if dimension != 384:
            raise EmbeddingError("The pinned model does not have the expected 384 dimensions.")

    def token_count(self, text):
        return len(self.model.tokenizer.encode(text, add_special_tokens=True, truncation=False, verbose=False))

    def _encode(self, texts):
        if any(self.token_count(text) > self.max_tokens for text in texts):
            raise EmbeddingError("Embedding input exceeds 512 tokens; chunk it instead of truncating.")
        values = self.model.encode(texts, batch_size=16, normalize_embeddings=True, show_progress_bar=False)
        return [checked_vector(value) for value in values]

    def passages(self, texts):
        return self._encode(["passage: " + text for text in texts])

    def query(self, text):
        if self.token_count("query: " + text) <= self.max_tokens:
            return self._encode(["query: " + text])[0]
        # A long clinical query must not be silently cut at the model's first 512 tokens.
        passages, start = [], 0
        while start < len(text):
            low, high, best = start + 1, len(text), start
            while low <= high:
                end = (low + high) // 2
                if self.token_count("query: " + text[start:end]) <= self.max_tokens:
                    best, low = end, end + 1
                else:
                    high = end - 1
            if best == start:
                raise EmbeddingError("Cannot fit a query character into the embedding window.")
            passages.append("query: " + text[start:best])
            start = best
        vectors = self._encode(passages)
        return checked_vector([sum(vector[index] for vector in vectors) / len(vectors) for index in range(384)])
