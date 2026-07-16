# P0 安全验收脚本

脚本位置：`scripts/test_p0_security.py`。

## 测试范围

- 生产安全配置的 fail-closed 行为
- SSRF：回环、私网、云元数据地址和 DNS 解析到私网的地址
- `/api/health` 可用于健康检查
- 私有 API 必须通过 HTTP Basic 登录
- 错误密码不能访问
- Swagger、ReDoc、OpenAPI、诊断和自测接口在生产环境关闭
- 不存在的 `/api/*` 返回 HTTP 404
- 生产环境不能由客户端提交临时模型地址
- 超大 JSON 请求返回 HTTP 413
- 安全响应头存在
- 可选的 HTTP 429 限流压测

## Windows PowerShell

先启动生产服务，然后在项目根目录执行：

```powershell
.\test-p0-security.ps1 `
  -BaseUrl "https://你的域名" `
  -Username "admin" `
  -Password "你的访问密码"
```

## Linux / macOS

```bash
./test-p0-security.sh \
  'https://你的域名' \
  'admin' \
  '你的访问密码'
```

## 仅测试代码，不连接服务器

```bash
python scripts/test_p0_security.py --skip-live
```

## 开启限流压测

限流测试会连续请求服务器，并可能让当前 IP 在一个限流窗口内收到 429。建议最后单独执行：

```bash
python scripts/test_p0_security.py \
  --base-url 'https://你的域名' \
  --username admin \
  --password '你的访问密码' \
  --skip-pytest \
  --test-rate-limit
```

默认尝试 200 次。若服务器阈值更高，可增加 `--rate-limit-attempts`。

## 判定方式

- 所有必测项显示 `PASS`，脚本退出码为 `0`：验收通过。
- 任一项显示 `FAIL`，脚本退出码为 `1`：不要上线。
- `SKIP` 不计为失败；默认只跳过会影响当前 IP 的限流压测。

注意：黑盒测试中的“生产环境禁止提交临时模型地址”验证的是公网接口无法利用任意 URL。更底层的 DNS/私网 SSRF 规则由代码级 pytest 测试覆盖。
