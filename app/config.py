"""Central configuration (pydantic-settings). All runtime knobs in one place.

Design note: policy *thresholds* that the business owns (refund window, critic
groundedness floor, SLAs) live in the SQLite `policy_registry` and are cited to a
policy article. The values here are infra defaults / fallbacks only.
"""
from __future__ import annotations

from datetime import date
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# Repo root = parent of the app/ package.
ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # ---- LLM ----
    llm_provider: str = "mock"  # mock | ollama | cloud
    ollama_host: str = "http://localhost:11434"
    ollama_model: str = "qwen2.5:7b-instruct"
    cloud_base_url: str = "https://api.openai.com/v1"
    cloud_api_key: str = ""
    cloud_model: str = "gpt-4o-mini"

    # ---- Embeddings ----
    embeddings: str = "onnx-minilm"  # onnx-minilm | sentence-transformers
    embedding_model: str = "all-MiniLM-L6-v2"

    # ---- Storage ----
    sqlite_path: str = "storage/insightdesk.db"
    chroma_dir: str = "storage/chroma"

    # ---- Retrieval / policy ----
    top_k: int = 5
    # best-chunk cosine distance above this => KB does not cover the question (not_found),
    # so we never invent an answer from an irrelevant chunk (R2). A config we can tune.
    relevance_max_distance: float = 0.58
    critic_min_groundedness: float = 0.6
    # critic groundedness: deterministic overlap (default — reliable, fast) or LLM
    # self-critique. On small local models the LLM judge over-escalates grounded
    # answers; we quantify this trade-off in the Phase 6 evaluation.
    critic_llm: bool = False

    @property
    def sqlite_abspath(self) -> Path:
        p = ROOT / self.sqlite_path
        p.parent.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def chroma_abspath(self) -> Path:
        p = ROOT / self.chroma_dir
        p.mkdir(parents=True, exist_ok=True)
        return p


@lru_cache
def get_settings() -> Settings:
    return Settings()


def today_str() -> str:
    return date.today().isoformat()
