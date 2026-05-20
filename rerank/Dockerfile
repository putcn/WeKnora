# =============================================================
# WeKnora Rerank Server
# Model: maidalun1020/bce-reranker-base_v1
# Compatible with OpenAI rerank API format
# Supports CPU and GPU (CUDA) device selection
# =============================================================

ARG CUDA_VERSION=12.1.0
ARG BASE_IMAGE=python:3.11-slim

# Use CUDA base if DEVICE=cuda, otherwise plain python
FROM ${BASE_IMAGE}

ARG DEVICE=cpu
ARG MODEL_NAME=maidalun1020/bce-reranker-base_v1
ARG HF_MIRROR=https://huggingface.co

ENV DEVICE=${DEVICE} \
    MODEL_NAME=${MODEL_NAME} \
    HF_ENDPOINT=${HF_MIRROR} \
    # Cache model inside image layer so first boot is instant
    TRANSFORMERS_CACHE=/app/model_cache \
    HF_HOME=/app/model_cache \
    PYTHONUNBUFFERED=1 \
    PORT=8000

WORKDIR /app

# ---------- system deps ----------
RUN apt-get update && apt-get install -y --no-install-recommends \
        curl \
    && rm -rf /var/lib/apt/lists/*

# ---------- python deps ----------
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# ---------- pre-download model ----------
# Model is baked into the image so the container starts immediately.
# Override MODEL_NAME build-arg to use a different checkpoint.
RUN python - <<'EOF'
import os
from transformers import AutoTokenizer, AutoModelForSequenceClassification
m = os.environ["MODEL_NAME"]
print(f"[rerank] downloading {m} ...")
AutoTokenizer.from_pretrained(m, cache_dir="/app/model_cache")
AutoModelForSequenceClassification.from_pretrained(m, cache_dir="/app/model_cache")
print("[rerank] model downloaded.")
EOF

# ---------- app ----------
COPY server.py ./

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:${PORT}/health || exit 1

CMD ["python", "server.py"]
