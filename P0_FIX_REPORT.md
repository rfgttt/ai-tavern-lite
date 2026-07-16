# P0 修复报告

日期：2026-07-16

## 修复范围

- 单用户生产访问控制：HTTP Basic Auth，生产环境缺失或弱密码时拒绝启动。
- Host 与浏览器安全边界：Trusted Host、CSP、HSTS、点击劫持与 MIME 嗅探防护。
- SSRF：模型 Base URL 协议、凭据、域名、DNS 解析地址与可选主机白名单校验。
- 管理面收敛：生产关闭 OpenAPI/Swagger、诊断、自检；网页模型设置可锁定为只读。
- 滥用控制：API 滑动窗口限流、模型请求单独限流、生成并发上限、请求体与消息长度上限。
- SSE：返回禁缓冲响应头，并提供 Caddy 实时转发配置。
- SQLite：WAL、busy timeout、外键校验和一致性 Backup API。
- 部署：多阶段 Dockerfile、单 worker、非 root、只读根文件系统、最小 capability、Caddy HTTPS。
- 发布脱敏：自动排除数据库、备份、日志、环境文件、node_modules、dist 和自检产物。
- 前端生产提示：服务器锁定设置时显示只读提示并隐藏诊断操作。

## 验证结果

- 后端：`139 passed`。
- 前端：TypeScript 与 Vite 生产构建成功。
- 生产烟雾测试：认证、公开健康检查、文档关闭、诊断关闭、设置锁定、404、CSP、HSTS 全部通过。
- 发布包扫描：184 个文件，未包含数据库、运行数据、日志、`.env`、node_modules 或 dist。
- Docker 镜像未在当前环境实际构建，因为当前执行环境没有 Docker 命令；Compose YAML 已完成解析检查。

## 仍需人工完成

- 在模型供应商后台轮换旧 API Key，并从旧数据库删除旧 Key。
- 把 `.env.production.example` 复制为 `.env.production`，替换真实域名和随机访问密码。
- 配置 DNS、防火墙和服务器出口规则；只对公网开放 80/443，不开放 8000。
- 需要保留旧数据时，只迁移清理后的数据库与头像。

## 当前架构限制

此版本仍是单用户、SQLite、单 worker、单应用副本。不要通过增加 Uvicorn workers 或 Compose replicas 横向扩容；多用户版本需另行加入账号归属、PostgreSQL 和 Redis。
