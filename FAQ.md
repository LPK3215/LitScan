# FAQ

## 网络 / 代理

### Q: 请求报 SSL 握手失败 / Connection reset？

Clash 等代理开启 SSL 拦截但证书不被系统信任导致。

解决方法（任选其一）：
1. 代理客户端里开启"跳过 TLS 验证"（Skip TLS Verification）
2. 安装代理客户端的 root 证书到系统信任区
3. 把代理模式从 Global 切到 Rule，避免学术站点流量走代理

### Q: 不想走代理怎么办？

三种方式：
- `config.yaml` 中 `request.proxy` 设为 `"none"`
- 命令行加 `--no-proxy`
- 什么都不配时自动读取环境变量 `http_proxy` / `https_proxy`，环境变量没配就不走代理

## 检索源

### Q: Semantic Scholar 报 429 限流？

该库有免费额度限流。LitScan 已内置自动重试与退避（`config.yaml` 中 `max_retries: 4`），如仍频繁触发，建议：
- 降低 `limit_per_source`
- 或在 `config.yaml` 中将该源 `enabled: false` 临时禁用

### Q: Europe PMC 默认没开？

生物医学方向倾向明显，默认关闭。需要时在 `config.yaml` 中改为 `enabled: true`。

## 使用

### Q: 历史记录能重跑吗？

能。Web 端在 `/history` 页面点击重跑；CLI 用 `python litscan.py --retry <记录ID>`；API 用 `POST /api/history/retry/{id}`。

### Q: 输出文件在哪里？

统一在 `out/` 目录：`articles.csv`（统一格式结果）、`log.md`（检索日志）、`history.json`（历史）、`raw/`（各库原始响应）。该目录已在 `.gitignore` 中忽略。

### Q: Windows 下终端中文乱码？

`litscan.py` 已内置 UTF-8 输出修复（GBK 环境自动包装 stdout/stderr），如仍出现乱码，可先执行 `chcp 65001` 再运行。
