# BCE Reranker Server

`bce-reranker-base_v1` 的开箱即用 Rerank 推理服务，兼容 Jina / Cohere 风格的 OpenAI API 接口格式。

---

## `local-deploy-full` 分支说明

> 本节仅适用于 **`local-deploy-full`** 分支，主分支或其他分支请忽略。

### 设计目标

`local-deploy-full` 分支的目标是在**无 GPU 的 Linux 服务器**上通过 `docker compose --profile full` 一键拉起全栈，rerank 服务是其中的一个组件。为此，本分支对 rerank 做了以下约束：

| 设置项 | 本分支默认值 | 说明 |
|--------|------------|------|
| `RERANK_DEVICE` | `cpu` | 强制 CPU 推理，不依赖 NVIDIA 驱动或 CUDA 工具链 |
| `RERANK_IMAGE` | `weknora-rerank:cpu` | 使用 CPU-only PyTorch 镜像，体积更小，构建无需 CUDA |
| docker-compose GPU 资源声明 | 注释掉 | `deploy.resources.reservations` 块保持注释，确保无 GPU 环境不报错 |

### 快速启动（无 GPU）

```bash
# 在 local-deploy-full 分支，直接用 full profile 启动即可
docker compose --profile full up -d

# 若只想单独测试 rerank：
docker compose --profile rerank up -d rerank
```

无需任何额外配置，rerank 服务会以 CPU 模式启动，首次运行时 Docker 会自动 build 镜像并从 HuggingFace 下载模型（约 1 GB）。

### 国内镜像加速

如果下载模型较慢，在 `.env` 中加入：

```env
RERANK_HF_MIRROR=https://hf-mirror.com
```

### 升级到 GPU 模式

如果后续服务器配备了 GPU，升级步骤见下方 [GPU 模式](#gpu-模式需要三步缺一不可) 小节。升级后需将 `.env` 中的 `RERANK_DEVICE` 改回 `cuda` 并重新 build 镜像。

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
  "meta": { "elapsed_seconds": 0.042, "device": "cpu" }
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
| `RERANK_DEVICE` | `cpu` | `auto` / `cpu` / `cuda` / `cuda:0`。**GPU 模式仅在第一、二步完成后有效**。`local-deploy-full` 分支默认锁定为 `cpu` |
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
