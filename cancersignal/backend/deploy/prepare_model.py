"""Explicit one-time download/validation of the pinned E5 assets; no DB or LLM calls."""
import os
from app.rag.embeddings import LocalE5Embedder, MODEL_REVISION

LocalE5Embedder(revision=MODEL_REVISION,
               cache_dir=os.environ['CANCERSIGNAL_RETRIEVAL_MODEL_CACHE'],
               local_files_only=False)
print('Pinned E5 model cached and validated.')
