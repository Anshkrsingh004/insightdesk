"""Embedding function factory (mandated model: all-MiniLM-L6-v2).

Default `onnx-minilm` uses Chroma's bundled ONNX all-MiniLM-L6-v2 (no torch, no
compiler). `sentence-transformers` switches to the library form (same weights) if
requirements-ml.txt is installed. Justified in the README: identical model, lighter
runtime — a deliberate trade-off, not a shortcut.
"""
from __future__ import annotations

from ..config import Settings, get_settings


def get_embedding_function(settings: Settings | None = None):
    s = settings or get_settings()
    from chromadb.utils import embedding_functions

    if s.embeddings == "sentence-transformers":
        return embedding_functions.SentenceTransformerEmbeddingFunction(
            model_name=s.embedding_model
        )
    # default: bundled ONNX all-MiniLM-L6-v2
    return embedding_functions.DefaultEmbeddingFunction()
