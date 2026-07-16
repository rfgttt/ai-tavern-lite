# P0 上线安全说明

本版本按“单用户私有服务”加固，不是多租户 SaaS。生产环境必须只运行一个 Uvicorn worker 和一个应用副本。

## 已实施

- 生产环境必须启用 HTTP Basic 登录，密码少于 12 个字符时拒绝启动。
- 生产环境必须配置明确的可信 Host，禁止 `*`。
- `/docs`、`/redoc`、`/openapi.json` 在生产环境关闭。
- 诊断和自检路由在生产 Compose 中关闭。
- 模型设置在生产 Compose 中只读；Base URL、Key 和模型通过环境变量提供。
- 模型 Base URL 仅允许 HTTP/HTTPS，禁止 URL 凭据，并拒绝本机、内网、链路本地、云元数据等非公网解析结果。
- API 滑动窗口限流、AI 请求单独限流、最多并发生成数限制。
- JSON、普通请求和上传请求均有请求体大小上限。
- SSE 返回 `X-Accel-Buffering: no`，Caddy 同时禁用流缓冲。
- 安全响应头、CSP、HSTS、可信 Host 校验。
- SQLite 使用 WAL、30 秒 busy timeout 和一致性 Backup API。
- Docker 使用非 root 用户、只读根文件系统、删除 Linux capabilities；应用端口不直接暴露。
- 发布脚本自动排除数据库、备份、日志、`.env`、`node_modules`、构建产物和自检包。

## 首次部署

```bash
cp .env.production.example .env.production
# 编辑 DOMAIN、登录密码和模型配置
docker compose --env-file .env.production up -d --build
```

示例域名和示例密码会被程序拒绝；请先改成真实值。域名 DNS 必须指向服务器，防火墙只开放 80/443。不要开放应用容器的 8000 端口。

## 模型地址

默认只允许解析结果全部为公网地址的模型域名。建议进一步设置：

```env
AI_TAVERN_LLM_ALLOWED_HOSTS=api.example.com
```

如果确实需要访问内网模型，必须显式设置 `AI_TAVERN_ALLOW_PRIVATE_LLM_HOSTS=true`，同时用防火墙阻断 `169.254.169.254`、本机管理端口和其他敏感网段。公网部署不建议启用。

## 数据迁移

旧数据需要保留时，只把确认过的 `ai_tavern.db` 和头像导入 Docker 的 `app_data` 数据卷。不要复制旧备份、日志或诊断包。导入前先删除数据库中的旧 API Key，并在供应商后台轮换。

## 发布包

```bash
python scripts/build_release.py --output AI-Tavern-Lite-release.zip
```

### 导入旧 SQLite 数据（可选）

先停止应用，再把清理后的数据库复制进数据卷：

```bash
docker compose --env-file .env.production stop app
docker compose --env-file .env.production run --rm --user 0 \
  -v "$PWD:/backup:ro" app \
  sh -c 'cp /backup/ai_tavern.db /app/backend/data/ai_tavern.db && chown 10001:10001 /app/backend/data/ai_tavern.db'
docker compose --env-file .env.production start app
```

头像目录可用同样方式复制到 `/app/backend/data/avatars/`。
