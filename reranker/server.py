"""
BCE-Reranker-Base-v1 OpenAI-compatible inference server

Compatible endpoint:
  POST /rerank          - Jina/Cohere-style rerank (primary, used by WeKnora)
  POST /v1/rerank       - same, with /v1 prefix
  GET  /health          - health check
  GET  /                - service info

Response schema follows Jina Rerank API so WeKnora's Jina rerank provider works
out-of-the-box. Set Instance URL to http://reranker:8000 in WeKnora console.
"""
from __future__ import annotations

import gc
import logging
import os
import time
from contextlib import asynccontextmanager
from typing import List, Optional

import torch
uvicorn_import_ok = True
try:
    import uvicorn
except ImportError:
    uvicorn_import_ok = False

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from transformers import AutoModelForSequenceClassification, AutoTokenizer

# ---------------------------------------------------------------------------
# Config from environment
# ---------------------------------------------------------------------------
MODEL_NAME = os.getenv("RERANKER_MODEL", "maidalun1020/bce-reranker-base_v1")
DEVICE_ENV = os.getenv("RERANKER_DEVICE", "auto")  # auto | cpu | cuda | cuda:0 ...
MAX_LENGTH = int(os.getenv("RERANKER_MAX_LENGTH", "512"))
LOG_LEVEL = os.getenv("LOG_LEVEL", "info").upper()
HOST = os.getenv("RERANKER_HOST", "0.0.0.0")
PORT = int(os.getenv("RERANKER_PORT", "8000"))

logging.basicConfig(level=getattr(logging, LOG_LEVEL, logging.INFO),
                    format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Device selection
# ---------------------------------------------------------------------------
def resolve_device(device_env: str) -> torch.device:
    if device_env == "auto":
        if torch.cuda.is_available():
            dev = torch.device("cuda")
        else:
            dev = torch.device("cpu")
    else:
        dev = torch.device(device_env)
    return dev

# ---------------------------------------------------------------------------
# Global model state
# ---------------------------------------------------------------------------
class ModelState:
    tokenizer: Optional[AutoTokenizer] = None
    model: Optional[AutoModelForSequenceClassification] = None
    device: Optional[torch.device] = None
    model_name: str = MODEL_NAME

state = ModelState()

# ---------------------------------------------------------------------------
# Lifespan: load model on startup
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Loading model: %s", MODEL_NAME)
    state.device = resolve_device(DEVICE_ENV)
    logger.info("Device: %s", state.device)

    state.tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)
    state.model = AutoModelForSequenceClassification.from_pretrained(MODEL_NAME)
    state.model.to(state.device)
    state.model.eval()
    logger.info("Model loaded successfully on %s", state.device)
    yield
    # cleanup
    del state.model, state.tokenizer
    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()

# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------
app = FastAPI(
    title="BCE Reranker Server",
    description="OpenAI/Jina-compatible rerank inference server for bce-reranker-base_v1",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Request / Response schemas
# ---------------------------------------------------------------------------
class RerankRequest(BaseModel):
    """Jina / Cohere-compatible request schema."""
    query: str
    documents: List[str]
    top_n: Optional[int] = Field(None, description="Return top N results. Default: all.")
    return_documents: bool = Field(True, description="Include document text in response.")

class DocumentObject(BaseModel):
    text: str

class RerankResult(BaseModel):
    index: int
    relevance_score: float
    document: Optional[DocumentObject] = None

class RerankResponse(BaseModel):
    model: str
    results: List[RerankResult]
    meta: dict = Field(default_factory=dict)

# ---------------------------------------------------------------------------
# Core inference
# ---------------------------------------------------------------------------
def _infer(query: str, documents: List[str]) -> List[float]:
    pairs = [[query, doc] for doc in documents]
    inputs = state.tokenizer(
        pairs,
        padding=True,
        truncation=True,
        max_length=MAX_LENGTH,
        return_tensors="pt",
    ).to(state.device)
    with torch.no_grad():
        outputs = state.model(**inputs, return_dict=True)
        logits = outputs.logits.view(-1).float()
        scores = torch.sigmoid(logits).cpu().tolist()
    del inputs, outputs, logits
    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()
    return scores

# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------
def _handle_rerank(req: RerankRequest) -> RerankResponse:
    if state.model is None:
        raise HTTPException(status_code=503, detail="Model not loaded yet")
    if not req.documents:
        raise HTTPException(status_code=400, detail="documents must not be empty")

    t0 = time.perf_counter()
    scores = _infer(req.query, req.documents)
    elapsed = time.perf_counter() - t0

    results = [
        RerankResult(
            index=i,
            relevance_score=score,
            document=DocumentObject(text=doc) if req.return_documents else None,
        )
        for i, (doc, score) in enumerate(zip(req.documents, scores))
    ]
    results.sort(key=lambda r: r.relevance_score, reverse=True)

    if req.top_n is not None:
        results = results[: req.top_n]

    logger.info(
        "Reranked %d docs in %.3fs on %s", len(req.documents), elapsed, state.device
    )
    return RerankResponse(
        model=state.model_name,
        results=results,
        meta={"elapsed_seconds": round(elapsed, 4), "device": str(state.device)},
    )


@app.post("/rerank", response_model=RerankResponse)
def rerank(req: RerankRequest):
    return _handle_rerank(req)


@app.post("/v1/rerank", response_model=RerankResponse)
def rerank_v1(req: RerankRequest):
    return _handle_rerank(req)


@app.get("/health")
def health():
    return {
        "status": "ok" if state.model is not None else "loading",
        "model": state.model_name,
        "device": str(state.device),
    }


@app.get("/")
def root():
    return {
        "service": "bce-reranker-base_v1 inference server",
        "endpoints": ["/rerank", "/v1/rerank", "/health"],
        "model": state.model_name,
        "device": str(state.device),
    }


if __name__ == "__main__" and uvicorn_import_ok:
    uvicorn.run(app, host=HOST, port=PORT)
