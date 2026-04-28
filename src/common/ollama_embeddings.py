from __future__ import annotations

import requests

from .config_utils import load_config


class OllamaEmbeddings:
    """LangChain-compatible embeddings backed by Ollama's local API."""

    def __init__(
        self,
        model: str | None = None,
        base_url: str | None = None,
        timeout: int = 300,
    ) -> None:
        config = load_config()
        self.model = model or config.get("OLLAMA_EMBEDDING_MODEL") or "embeddinggemma"
        self.base_url = self._normalize_base_url(
            base_url or config.get("OLLAMA_BASE_URL") or "http://localhost:11434/v1"
        )
        self.timeout = timeout

    @staticmethod
    def _normalize_base_url(url: str) -> str:
        base = url.rstrip("/")
        if base.endswith("/v1"):
            base = base[:-3]
        return base

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []

        response = requests.post(
            f"{self.base_url}/api/embed",
            json={"model": self.model, "input": texts},
            timeout=self.timeout,
        )

        if response.status_code == 404:
            return [self._embed_legacy(text) for text in texts]

        try:
            response.raise_for_status()
        except requests.HTTPError as exc:
            raise RuntimeError(f"Ollama embedding request failed for model '{self.model}': {response.text}") from exc

        data = response.json()
        embeddings = data.get("embeddings")
        if embeddings is None and "embedding" in data:
            embeddings = [data["embedding"]]
        if not isinstance(embeddings, list) or len(embeddings) != len(texts):
            raise RuntimeError(f"Unexpected Ollama embedding response for model '{self.model}': {data}")
        return embeddings

    def embed_query(self, text: str) -> list[float]:
        return self.embed_documents([text])[0]

    def _embed_legacy(self, text: str) -> list[float]:
        response = requests.post(
            f"{self.base_url}/api/embeddings",
            json={"model": self.model, "prompt": text},
            timeout=self.timeout,
        )
        try:
            response.raise_for_status()
        except requests.HTTPError as exc:
            raise RuntimeError(f"Ollama legacy embedding request failed for model '{self.model}': {response.text}") from exc

        data = response.json()
        embedding = data.get("embedding")
        if not isinstance(embedding, list):
            raise RuntimeError(f"Unexpected Ollama legacy embedding response for model '{self.model}': {data}")
        return embedding
