# WeKnora Rerank Server

轻量级 Rerank 推理服务，基于 [maidalun1020/bce-reranker-base_v1](https://huggingface.co/maidalun1020/bce-reranker-base_v1)，支持 CPU / GPU，提供 OpenAI 兼容的 Rerank API。

## API 接口

### OpenAI 兼容格式（推荐）

```
POST /v1/rerank
```

```json
{
  "model": "bce-reranker-base_v1",
  "query": "什么是向量数据库",
  "documents": [
    "向量数据库是专门用于存储和检索高维向量的数据库",
    "关系型数据库使用 SQL 进行查询"
  ],
  "top_n": 2,
  "return_documents": true
}
```

响应：

```json
{
  "model": "bce-reranker-base_v1",
  "results": [
    {"index": 0, "relevance_score": 0.94, "document": {"text": "向量数据库是..."}},
    {"index": 1, "relevance_score": 0.12, "document": {"text": "关系型数据库..."}}
  ]
}
```

### Legacy 格式（向后兼容）

```
POST /rerank
```

```json
{"query": "...", "documents": ["...", "..."]}
```

响应字段为 `score`（兼容旧版 WeKnora demo）。

### 其他端点

| 端点 | 说明 |
|------|------|
| `GET /health` | 健康检查 |
| `GET /v1/models` | 返回已加载的模型信息 |

## 在 docker compose 中使用

`docker-compose.yml` 已内置 `rerank` service，包含在 `--profile rerank` 和 `--profile full` 中。

```bash
# 仅启动 rerank 服务（CPU）
docker compose --profile rerank up -d rerank

# 启动所有服务（包含 rerank CPU 版）
docker compose --profile full up -d
```

### 使用 GPU

```bash
# 先构建 CUDA 镜像
docker build -f rerank/Dockerfile.cuda -t weknora-rerank:cuda ./rerank

# 修改 .env
RERANK_DEVICE=cuda
RERANK_IMAGE=weknora-rerank:cuda

# 启动（需要 NVIDIA Container Toolkit）
docker compose --profile rerank up -d rerank
```

## 环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `DEVICE` | `cpu` | 推理设备：`cpu` 或 `cuda` |
| `MODEL_NAME` | `maidalun1020/bce-reranker-base_v1` | HuggingFace 模型 ID |
| `PORT` | `8000` | 监听端口 |
| `MAX_LENGTH` | `512` | tokenizer 最大 token 数 |
| `DEFAULT_TOP_N` | `0` | 默认返回结果数，0 为全部返回 |
| `HF_ENDPOINT` | `https://huggingface.co` | HuggingFace 镜像地址（国内可改为 `https://hf-mirror.com`）|
| `LOG_LEVEL` | `INFO` | 日志级别 |

## 在 WeKnora 控制台中配置

1. 进入 **Settings → Model Providers**
2. 添加 Rerank Provider，类型选 **Jina** 或自定义（URL 兼容）
3. API URL 填：`http://rerank:8000`（Docker 内部访问）
4. 模型名称填：`bce-reranker-base_v1`

## 单独构建测试

```bash
cd rerank

# 构建 CPU 镜像（首次构建会下载模型，约 1GB）
docker build -t weknora-rerank:cpu .

# 启动
docker run -p 8000:8000 weknora-rerank:cpu

# 测试
curl -X POST http://localhost:8000/v1/rerank \
  -H 'Content-Type: application/json' \
  -d '{"query":"向量数据库","documents":["向量数据库专用于高维向量检索","MySQL是关系型数据库"]}'
```

## 国内镜像加速

构建时通过 `--build-arg` 设置 HF 镜像源：

```bash
docker build \
  --build-arg HF_MIRROR=https://hf-mirror.com \
  -t weknora-rerank:cpu .
```

或在 `.env` 中设置 `RERANK_HF_MIRROR=https://hf-mirror.com` 后重新 build。
