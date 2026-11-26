# AgentScope Web

React + Vite 前端通过 FastAPI 调用 AgentScope 服务。MySQL 保存账号和旧工作区映射，Redis 保存业务数据和登录会话，本地 Qdrant 保存知识库向量。

## 本地启动

需要 Python 3.11+、Node.js 22.15+、pnpm 12.21.0、MySQL 8.0+ 和 Redis。先在 MySQL 创建用于账号的数据库，并为连接账号授予该库的权限。建表需要 `CREATE`，日常运行账号库需要 `SELECT`、`INSERT` 和 `UPDATE`。

```sql
CREATE DATABASE agentscope_auth CHARACTER SET utf8mb4;
```

以下命令从项目根目录运行。已有 Redis 时使用现有实例即可。连接串中的密码含有特殊字符时，先对密码部分做 URL 编码。

后端启动和账号管理命令都会读取 `backend/.env`，终端里设置的同名环境变量优先。默认本机 Redis 启用了密码时，在该文件中设置 `AGENTSCOPE_REDIS_PASSWORD`。如果显式设置了 `AGENTSCOPE_REDIS_URL`，请把 Redis 凭据写在该连接串里。

```powershell
docker run -d --name agentscope-redis -p 127.0.0.1:6379:6379 -v agentscope-redis:/data redis:7 redis-server --appendonly yes
Set-Location backend
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
$env:AUTH_MYSQL_URL = 'mysql+asyncmy://root:YOUR_PASSWORD@127.0.0.1:3306/agentscope_auth'
.\.venv\Scripts\python.exe -m auth.manage init-db
.\.venv\Scripts\python.exe -m uvicorn main:app --host 127.0.0.1 --port 8088
```

在另一个终端，从项目根目录运行前端。

```powershell
pnpm install --frozen-lockfile
pnpm dev:frontend
```

打开 `http://localhost:5173`，设置页默认使用 `http://localhost:5173/api`。Vite 把 `/api/` 转发到 `127.0.0.1:8088`。也可以填写 `http://localhost:8088` 直连。登录后在凭据页面配置模型，再创建智能体和会话。

## 配置与部署

| 变量 | 用途 |
| --- | --- |
| `AGENTSCOPE_REDIS_URL` | 业务 Redis，默认 `redis://localhost:6379/0` |
| `AGENTSCOPE_REDIS_PASSWORD` | 默认本机业务 Redis 的密码，使用显式 `AGENTSCOPE_REDIS_URL` 时由连接串提供 |
| `AUTH_REDIS_URL` | 登录会话 Redis，默认跟随业务 Redis |
| `AUTH_MYSQL_URL` | 必填，账号库的 `mysql+asyncmy://` 连接串 |
| `AGENTSCOPE_QDRANT_PATH` | 本地向量目录，默认 `backend/data/qdrant` |
| `AGENTSCOPE_QDRANT_URL` / `AGENTSCOPE_QDRANT_API_KEY` | 连接独立 Qdrant 服务 |
| `AGENTSCOPE_WORKSPACES_DIR` / `AGENTSCOPE_BLOB_DIR` | 工作区和知识库原文，默认 `backend/workspaces`、`backend/blobs` |
| `AUTH_ALLOWED_ORIGINS` | 逗号分隔的完整前端来源，默认允许 `http://localhost:5173` 和 `http://127.0.0.1:5173` |
| `AUTH_COOKIE_SECURE` | HTTPS 生产环境设为 `true` |
| `AUTH_REGISTRATION_OPEN` | 控制开放注册，默认 `true` |

在根目录执行 `pnpm install --frozen-lockfile` 和 `pnpm build:frontend`。把 `frontend/dist` 部署到 HTTPS 静态站点，并配置 SPA 回退。将 `/api/` 反代到后端的 `/`，为 SSE 关闭缓冲，为实时语音启用 WebSocket 转发。把 `AUTH_ALLOWED_ORIGINS` 设为站点的 HTTPS 来源。

后端运行 `python -m uvicorn main:app --app-dir backend --host 127.0.0.1 --port 8088 --workers 1`。当前消息总线和本地 Qdrant 使用单进程。持久化 Redis、MySQL、向量目录、工作区和原文目录。以前仅保存在内存中的向量需要从原文重新索引。`GET /auth/ready` 检查 MySQL 账号表、认证 Redis 和业务 Redis。默认 Playwright MCP 依赖 `npx`。面向不可信用户开放本机工具前，需要隔离 Shell 和 MCP 执行环境。

### 导入旧账号

若有原先的 SQLite 账号库，先停止后端写入，保留源库备份。完成 `init-db` 后，在 `backend` 目录执行以下命令。以前配置过 `AUTH_DB_PATH` 的部署应将 `--source` 改为实际文件。

```powershell
.\.venv\Scripts\python.exe -m auth.manage import-sqlite --source .\data\auth.sqlite3
```

该命令只向空的 MySQL 账号表写入账号和旧工作区映射，保留账号 ID、密码哈希和业务身份，可继续使用原密码和已有资源。全新部署完成 `init-db` 后即可注册。

有旧的业务身份时，在 `backend` 下运行 `python -m auth.manage list-legacy` 查看，再用 `python -m auth.manage bind-legacy --username <账号> --legacy-id <旧标识>` 预览。确认后使用同一命令加 `--apply`。

## 验证

```powershell
pnpm --filter frontend test
pnpm --filter frontend lint
pnpm --filter frontend build
Set-Location backend
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

设置 `AGENTSCOPE_TEST_MYSQL_URL` 指向专用 MySQL 测试库，可运行账号存储测试。再设置 `AGENTSCOPE_TEST_REDIS_URL` 指向独立测试 Redis，可运行包含登录和跨账号隔离的集成测试。这些测试会在测试库创建账号和业务记录。
