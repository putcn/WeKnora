# =============================================================================
# BCE-Reranker-Base-v1 OpenAI-compatible inference server
# Supports CPU and GPU (CUDA).  Default device: auto (GPU if available, else CPU)
#
# Build args:
#   TORCH_INDEX_URL  - PyTorch index URL (default: CPU wheel index)
#                      For CUDA 12.1: https://download.pytorch.org/whl/cu121
#                      For CUDA 12.4: https://download.pytorch.org/whl/cu124
# =============================================================================
ARG TORCH_INDEX_URL=https://download.pytorch.org/whl/cpu

# ---------- Stage 1: dependency builder ----------
FROM python:3.11-slim AS builder

ARG TORCH_INDEX_URL

WORKDIR /build

COPY requirements.txt .

RUN pip install --upgrade pip \
 && pip install --no-cache-dir \
        --extra-index-url ${TORCH_INDEX_URL} \
        -r requirements.txt

# ---------- Stage 2: model downloader ----------
# Pre-download HuggingFace model into the image so the container starts
# without network access (air-gapped deployments) and starts up fast.
FROM builder AS model-downloader

ENV HF_HOME=/model_cache

RUN python - <<'EOF'
from transformers import AutoTokenizer, AutoModelForSequenceClassification
model_id = "maidalun1020/bce-reranker-base_v1"
print(f"Downloading {model_id} ...")
AutoTokenizer.from_pretrained(model_id)
AutoModelForSequenceClassification.from_pretrained(model_id)
print("Download complete.")
EOF

# ---------- Stage 3: runtime ----------
FROM python:3.11-slim AS runtime

# Copy installed packages from builder
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy pre-downloaded model
COPY --from=model-downloader /model_cache /model_cache

ENV HF_HOME=/model_cache

# Runtime config (overridable via env in compose)
ENV RERANKER_MODEL=maidalun1020/bce-reranker-base_v1 \
    RERANKER_DEVICE=auto \
    RERANKER_MAX_LENGTH=512 \
    RERANKER_HOST=0.0.0.0 \
    RERANKER_PORT=8000 \
    LOG_LEVEL=info

WORKDIR /app
COPY server.py .

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --retries=3 --start-period=60s \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" \
  || exit 1

CMD ["python", "-m", "uvicorn", "server:app", \
     "--host", "0.0.0.0", "--port", "8000", \
     "--workers", "1"]
