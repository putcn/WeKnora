# 本地 Linux 部署指南 (`--profile full`)

本 branch 已预配置好 `.env`，可在无 GPU 的 Linux 服务器上通过 `docker compose --profile full` 一键启动所有组件。

## 包含的组件

| 组件 | 说明 | 端口 |
|------|------|------|
| `frontend` | WeKnora Web UI (Nginx) | 80 |
| `app` | WeKnora 后端 API | 8080 |
| `docreader` | 文档解析服务 (gRPC) | 50051 (内部) |
| `postgres` | PostgreSQL (ParadeDB) | 5432 (内部) |
| `redis` | Redis 7 | 6379 (内部) |
| `minio` | 对象存储 | 9000 / 9001 (控制台) |
| `jaeger` | 分布式追踪 UI | 16686 |
| `neo4j` | 图数据库 | 7474 / 7687 |
| `qdrant` | 向量数据库 | 6333 / 6334 |
| `searxng` | 自建网络搜索 | 8888 (仅 127.0.0.1) |
| `langfuse-web` | LLM 可观测平台 | 3000 |
| `langfuse-worker` | Langfuse 后台任务 | - |
| `langfuse-clickhouse` | Langfuse OLAP 存储 | - |
| `langfuse-minio` | Langfuse 专用 MinIO | 9100 / 9101 |
| `dex` | OIDC 身份提供者 | 5556 |
| `sandbox` | Agent 沙箱镜像 (按需启动) | - |
| `searxng-init` | SearXNG 一次性初始化 | - |
| `langfuse-db-init` | Langfuse DB 初始化 | - |

## 快速开始

### 1. 前置要求

```bash
# Docker Engine 24+ 和 Docker Compose v2
docker --version
docker compose version

# 确保 Docker 守护进程有足够磁盘空间（建议 ≥ 50GB）
df -h /var/lib/docker
```

### 2. 克隆并切换到本 branch

```bash
git clone https://github.com/putcn/WeKnora.git
cd WeKnora
git checkout local-deploy-full
```

### 3. 根据需要修改 `.env`

`.env` 已预配置好，主要按需修改以下字段：

```bash
# 必改（生产环境）：安全密钥
TENANT_AES_KEY=<openssl rand -base64 24>
SYSTEM_AES_KEY=<必须恰好 32 字节>
JWT_SECRET=<openssl rand -hex 32>

# 必改：数据库密码
DB_PASSWORD=<your_strong_password>
REDIS_PASSWORD=<your_strong_password>

# 可选：如有公网域名，设置外部访问地址
# APP_EXTERNAL_URL=http://your-server-ip:80

# 可选：设置时区
TZ=Asia/Shanghai   # 或 America/Los_Angeles 等
```

### 4. 启动所有服务

```bash
# 拉取镜像并启动（首次启动约 5-10 分钟）
docker compose --profile full up -d

# 查看启动状态
docker compose --profile full ps

# 查看日志
docker compose logs -f app
```

### 5. 访问服务

| 服务 | URL |
|------|-----|
| WeKnora 主界面 | http://localhost:80 |
| 后端 API | http://localhost:8080 |
| Jaeger 追踪 UI | http://localhost:16686 |
| Neo4j Browser | http://localhost:7474 |
| MinIO 控制台 | http://localhost:9001 |
| Langfuse UI | http://localhost:3000 |
| SearXNG 搜索 | http://127.0.0.1:8888 |

## 配置 Langfuse（可观测）

首次启动后：

1. 打开 http://localhost:3000，注册管理员账号
2. 进入 **Settings → API Keys**，生成 Public Key 和 Secret Key
3. 修改 `.env`：
   ```
   LANGFUSE_PUBLIC_KEY=pk-lf-你生成的key
   LANGFUSE_SECRET_KEY=sk-lf-你生成的key
   ```
4. 重启 app 容器：
   ```bash
   docker compose up -d app
   ```

## 配置 SearXNG（网络搜索）

控制台中：Provider 类型选 **SearXNG**，Instance URL 填 `http://searxng:8080`

## 无 GPU 注意事项

- **LLM 推理**：使用 Ollama（CPU 模式），在宿主机安装并运行：
  ```bash
  curl -fsSL https://ollama.com/install.sh | sh
  ollama pull qwen2.5:7b  # 或其他轻量模型
  ```
  `.env` 中已配置 `OLLAMA_BASE_URL=http://host.docker.internal:11434`

- **图 RAG**：已关闭 (`ENABLE_GRAPH_RAG=false`)，开启需要大量 LLM 调用

- **文档解析并发**：已限制为 1 个并发 (`DOCREADER_PDF_RENDER_MAX_WORKERS=1`)，避免 CPU 过载

- **Embedding 并发**：已调低至 3 (`CONCURRENCY_POOL_SIZE=3`)

## 停止服务

```bash
# 停止但保留数据卷
docker compose --profile full down

# 停止并删除所有数据（慎用）
docker compose --profile full down -v
```

## 常见问题

**Q: app 容器健康检查一直失败？**  
A: 等待约 60 秒让 PostgreSQL 完成初始化，或查看 `docker compose logs postgres`

**Q: langfuse-web 启动慢？**  
A: ClickHouse 首次迁移需要 1-2 分钟，属正常现象

**Q: MinIO 端口冲突？**  
A: WeKnora MinIO 用 9000/9001，Langfuse MinIO 用 9100/9101，避免冲突
