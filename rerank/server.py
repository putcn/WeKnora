"""WeKnora Rerank Inference Server

Exposes two endpoint styles:

1. OpenAI-compatible (Jina/Cohere style used by most RAG frameworks):
   POST /v1/rerank
   Body:  { "model": "...", "query": "...", "documents": [...], "top_n": N }
   Reply: { "model": "...", "results": [{"index": 0, "relevance_score": 0.92, "document": {"text": "..."}}] }

2. Legacy WeKnora demo format (backward-compat):
   POST /rerank
   Body:  { "query": "...", "documents": [...] }
   Reply: { "results": [{"index": 0, "document": {"text": "..."}, "score": 0.92}] }

3. Health / info:
   GET  /health
   GET  /v1/models

Device selection via env var DEVICE: "cpu" (default) or "cuda".
Model loaded from HF Hub at build time; served from /app/model_cache.
"""

from __future__ import annotations

import gc
import logging
import os
import time
from contextlib import asynccontextmanager
from typing import Any, Dict, List, Optional, Union

import torch
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from transformers import AutoModelForSequenceClassification, AutoTokenizer

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(level=LOG_LEVEL, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("rerank")

MODEL_NAME: str = os.getenv("MODEL_NAME", "maidalun1020/bce-reranker-base_v1")
MODEL_CACHE: str = os.getenv("TRANSFORMERS_CACHE", "/app/model_cache")
DEVICE_CFG: str = os.getenv("DEVICE", "cpu").lower()
PORT: int = int(os.getenv("PORT", "8000"))
HOST: str = os.getenv("HOST", "0.0.0.0")
MAX_LENGTH: int = int(os.getenv("MAX_LENGTH", "512"))
DEFAULT_TOP_N: int = int(os.getenv("DEFAULT_TOP_N", "0"))  # 0 = return all

# ---------------------------------------------------------------------------
# Model state (loaded once at startup)
# ---------------------------------------------------------------------------
class ModelState:
    tokenizer: Any = None
    model: Any = None
    device: torch.device = None
    model_id: str = MODEL_NAME


state = ModelState()


# ---------------------------------------------------------------------------
# Lifespan: load model once
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    # --- startup ---
    if DEVICE_CFG == "cuda" and torch.cuda.is_available():
        state.device = torch.device("cuda")
        log.info("CUDA device: %s", torch.cuda.get_device_name(0))
    else:
        if DEVICE_CFG == "cuda":
            log.warning("CUDA requested but not available, falling back to CPU")
        state.device = torch.device("cpu")

    log.info("Loading model %s on %s ...", MODEL_NAME, state.device)
    t0 = time.time()
    state.tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME, cache_dir=MODEL_CACHE)
    state.model = AutoModelForSequenceClassification.from_pretrained(
        MODEL_NAME, cache_dir=MODEL_CACHE
    )
    state.model.to(state.device)
    state.model.eval()
    log.info("Model loaded in %.1fs", time.time() - t0)

    yield

    # --- shutdown ---
    del state.model
    del state.tokenizer
    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------
app = FastAPI(
    title="WeKnora Rerank Server",
    description="OpenAI-compatible rerank inference API (bce-reranker-base_v1)",
    version="1.0.0",
    lifespan=lifespan,
)


# ---------------------------------------------------------------------------
# Shared inference helper
# ---------------------------------------------------------------------------
def _infer_scores(query: str, documents: List[str]) -> List[float]:
    """Return a float score per document (higher = more relevant)."""
    if not documents:
        return []

    pairs = [[query, doc] for doc in documents]

    with torch.no_grad():
        inputs = state.tokenizer(
            pairs,
            padding=True,
            truncation=True,
            max_length=MAX_LENGTH,
            return_tensors="pt",
        ).to(state.device)
        outputs = state.model(**inputs, return_dict=True)
        logits = outputs.logits.view(-1).float()
        scores = torch.sigmoid(logits).cpu().tolist()

    # free GPU tensors immediately
    del inputs, outputs, logits
    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()

    return scores


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

# ---- OpenAI / Jina style ----
class RerankRequestV1(BaseModel):
    model: Optional[str] = MODEL_NAME
    query: str
    documents: List[Union[str, Dict[str, str]]]
    top_n: Optional[int] = None
    return_documents: Optional[bool] = True


class DocumentResult(BaseModel):
    text: str


class RerankResultV1(BaseModel):
    index: int
    relevance_score: float
    document: Optional[DocumentResult] = None


class RerankResponseV1(BaseModel):
    model: str
    results: List[RerankResultV1]
    usage: Dict[str, int] = Field(default_factory=lambda: {"total_tokens": 0})


# ---- Legacy / demo style ----
class LegacyRerankRequest(BaseModel):
    query: str
    documents: List[str]


class LegacyDocumentInfo(BaseModel):
    text: str


class LegacyRankResult(BaseModel):
    index: int
    document: LegacyDocumentInfo
    score: float


class LegacyRerankResponse(BaseModel):
    results: List[LegacyRankResult]


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/health")
def health():
    return {
        "status": "ok",
        "model": state.model_id,
        "device": str(state.device) if state.device else "loading",
    }


@app.get("/v1/models")
def list_models():
    """OpenAI models list endpoint — returns the loaded reranker model."""
    return {
        "object": "list",
        "data": [
            {
                "id": state.model_id,
                "object": "model",
                "owned_by": "weknora",
            }
        ],
    }


@app.post("/v1/rerank", response_model=RerankResponseV1)
def rerank_v1(req: RerankRequestV1):
    """OpenAI-compatible rerank endpoint.

    Documents can be plain strings or {"text": "..."} dicts.
    """
    if state.model is None:
        raise HTTPException(status_code=503, detail="Model not loaded yet")

    # Normalise documents to plain strings
    texts: List[str] = []
    for d in req.documents:
        if isinstance(d, dict):
            texts.append(d.get("text") or d.get("content") or str(d))
        else:
            texts.append(str(d))

    scores = _infer_scores(req.query, texts)

    results = [
        RerankResultV1(
            index=i,
            relevance_score=score,
            document=DocumentResult(text=texts[i]) if req.return_documents else None,
        )
        for i, score in enumerate(scores)
    ]

    # Sort descending by score
    results.sort(key=lambda x: x.relevance_score, reverse=True)

    # Apply top_n
    top_n = req.top_n or DEFAULT_TOP_N
    if top_n and top_n > 0:
        results = results[:top_n]

    model_id = req.model or state.model_id
    return RerankResponseV1(model=model_id, results=results)


@app.post("/rerank", response_model=LegacyRerankResponse)
def rerank_legacy(req: LegacyRerankRequest):
    """Legacy WeKnora demo-format endpoint (backward-compatible)."""
    if state.model is None:
        raise HTTPException(status_code=503, detail="Model not loaded yet")

    scores = _infer_scores(req.query, req.documents)

    results = [
        LegacyRankResult(
            index=i,
            document=LegacyDocumentInfo(text=text),
            score=score,
        )
        for i, (text, score) in enumerate(zip(req.documents, scores))
    ]
    results.sort(key=lambda x: x.score, reverse=True)
    return LegacyRerankResponse(results=results)


# ---------------------------------------------------------------------------
# Entry
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "server:app",
        host=HOST,
        port=PORT,
        log_level=LOG_LEVEL.lower(),
    )
