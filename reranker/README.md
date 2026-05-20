# BCE Reranker Server

`bce-reranker-base_v1` 的开箱即用 Rerank 推理服务，兼容 Jina / Cohere 风格的 OpenAI API 接口格式。

---

## `local-deploy-full` 分支说明

> 本节仅适用于 **`local-deploy-full`** 分支，主分支或其他分支请忽略。

### 当前配置：GPU 模式

`local-deploy-full` 分支已切换为 **GPU 模式**，前提是已在本地完成 CUDA 镜像构建（见下方 [GPU 模式](#gpu-模式需要三步缺一不可) 章节）。当前生效配置：

| 设置项 | 当前值 | 说明 |
|--------|--------|------|
| `RERANK_DEVICE` | `cuda` | GPU 推理，需 NVIDIA 驱动和 nvidia-container-toolkit |
| `RERANK_IMAGE` | `weknora-rerank:cuda` | 含 CUDA PyTorch 的本地构建镜像 |
| docker-compose GPU 资源声明 | **已取消注释** | `deploy.resources.reservations` 块已启用 |

### 快速启动（GPU）

```bash
# 确认本地已构建 CUDA 镜像：
docker images | grep weknora-rerank
# 应看到 weknora-rerank:cuda

# 启动全栈：
docker compose --profile full up -d
```

### 回退到 CPU 模式

如需在无 GPU 的机器上运行，修改 `.env`：

```env
RERANK_IMAGE=weknora-rerank:cpu
RERANK_DEVICE=cpu
```

并将 `docker-compose.yml` 中 `rerank` service 的 `deploy` 块重新注释，然后重新 build CPU 镜像：

```bash
docker build -t weknora-rerank:cpu ./reranker
docker compose --profile full up -d rerank
```

---

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
  "meta": { "elapsed_seconds": 0.012, "device": "cuda" }
}
```

## 部署方式

### CPU 模式（默认）

直接通过 docker compose 启动即可，无需额外操作：

```bash
docker compose --profile rerank up -d rerank
```

### GPU 模式（需要三步，缺一不可）

> **为什么需要三步？**
>
> 1. **镜像层**：CPU 镜像内置的是 CPU-only 版 PyTorch，其中没有 CUDA 运行时，单靠设置环境变量 `DEVICE=cuda` 只会报错。必须用带 CUDA 版 PyTorch 的包重新构建镜像。
> 2. **容器层**：即使镜像包含 CUDA，Docker 默认不会将宿主机 GPU 挂载进容器。必须在 docker-compose.yml 中声明 `deploy.resources.reservations.devices` 才能让容器访问 GPU。
> 3. **运行时层**：前两步就绪后，再通过 `DEVICE=cuda` 告知 server.py 使用 GPU 推理。

**第一步：构建包含 CUDA PyTorch 的镜像**

```bash
# CUDA 12.1（对应 RTX 30/40 系）
docker build \
  --build-arg TORCH_INDEX_URL=https://download.pytorch.org/whl/cu121 \
  -t weknora-rerank:cuda \
  ./reranker

# CUDA 12.4（更新的驱动）
docker build \
  --build-arg TORCH_INDEX_URL=https://download.pytorch.org/whl/cu124 \
  -t weknora-rerank:cuda \
  ./reranker
```

**第二步：在 docker-compose.yml 中取消 GPU 资源声明的注释**

找到 `rerank` service 下被注释掉的 `deploy` 块，取消注释：

```yaml
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: 1
              capabilities: [gpu]
```

**第三步：在 `.env` 中配置镜像名和 device**

```env
RERANK_IMAGE=weknora-rerank:cuda
RERANK_DEVICE=cuda
```

然后启动：

```bash
docker compose --profile rerank up -d rerank
```

## 环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `RERANK_MODEL` | `maidalun1020/bce-reranker-base_v1` | HuggingFace 模型 ID |
| `RERANK_DEVICE` | `cpu` | `auto` / `cpu` / `cuda` / `cuda:0`。**GPU 模式仅在第一、二步完成后有效** |
| `RERANK_MAX_LENGTH` | `512` | 输入最大 token 长度 |
| `RERANK_PORT` | `8001` | 宿主机映射端口（容器内始终监听 8000）|
| `RERANK_IMAGE` | `weknora-rerank:cpu` | 使用的镜像名，GPU 模式需改为 `weknora-rerank:cuda` |
| `RERANK_HF_MIRROR` | `https://huggingface.co` | HuggingFace 镜像源，国内可设为 `https://hf-mirror.com` |
| `LOG_LEVEL` | `info` | 日志级别 |

> **注意**：`RERANK_DEVICE=cuda` **不能独立生效**。若未完成上方的第一步（重新 build 含 CUDA PyTorch 的镜像）和第二步（docker-compose 中声明 GPU 资源），服务将无法启动或静默回退到 CPU。

## 在 WeKnora 控制台配置

1. 进入 **Settings → Model Providers**
2. 添加一个 Provider，类型选 **Jina**
3. API Base URL 填写：`http://rerank:8000`（容器内部访问）或 `http://localhost:8001`（宿主机访问）
4. Model 填写：`bce-reranker-base_v1`
5. 保存并在 Knowledge Base 中选择该模型作为 Reranker
