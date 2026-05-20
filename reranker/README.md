# BCE Reranker Server

`bce-reranker-base_v1` 的开筱即用 Rerank 推理服务，兄容 Jina / Cohere 风格的 OpenAI API 接口格式。

## 接口

| Method | Path | 说明 |
|--------|------|------|
| POST | `/rerank` | 主接口 |
| POST | `/v1/rerank` | 带版本前缀 |
| GET | `/health` | 健康检查 |
| GET | `/` | 服务信息 |

## 请求格式

```json
POST /rerank
{
  "query": "你的搜索问题",
  "documents": ["doc1", "doc2", "doc3"],
  "top_n": 3,
  "return_documents": true
}
```

## 响应格式

```json
{
  "model": "maidalun1020/bce-reranker-base_v1",
  "results": [
    {
      "index": 1,
      "relevance_score": 0.923,
      "document": { "text": "doc2" }
    }
  ],
  "meta": { "elapsed_seconds": 0.042, "device": "cpu" }
}
```

## 部署方式

### 透过 docker compose

```bash
# CPU 模式（默认）
docker compose --profile reranker up -d reranker

# GPU 模式（需要 NVIDIA Container Toolkit）
# 在 .env 中设置: RERANKER_DEVICE=cuda
docker compose --profile reranker up -d reranker
```

### 单独构建

```bash
# CPU
docker build -t weknora-reranker ./reranker

# GPU (CUDA 12.1)
docker build \
  --build-arg TORCH_INDEX_URL=https://download.pytorch.org/whl/cu121 \
  -t weknora-reranker-gpu ./reranker
```

## 环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `RERANKER_MODEL` | `maidalun1020/bce-reranker-base_v1` | HuggingFace 模型 ID |
| `RERANKER_DEVICE` | `auto` | `auto` / `cpu` / `cuda` / `cuda:0` |
| `RERANKER_MAX_LENGTH` | `512` | 输入最大 token 长度 |
| `RERANKER_PORT` | `8000` | 监听端口 |
| `LOG_LEVEL` | `info` | 日志级别 |

## 在 WeKnora 控制台配置

1. 进入 **Settings → Model Providers**
2. 添加一个 Provider，类型选 **Jina**
3. API Base URL 填写：`http://reranker:8000`（容器内部）或：`http://localhost:8000`（宿主机访问）
4. Model 填写：`bce-reranker-base_v1`
5. 保存并在 Knowledge Base 中选择该模型作为 Reranker
