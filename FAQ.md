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

## 全文下载

### Q: 为什么有些文献能直接下载 PDF、有些不能？

只走正规接口，能下的都下，不能下的明确放弃：

- **稳定可下**：arXiv、OpenReview（源自身提供 PDF 直链）
- **视情况可下**：Semantic Scholar / Europe PMC / DOAJ（取决于论文或期刊是否开放获取）
- **DOI 兜底**：任何带 DOI 的条目（包括 Crossref）都会依次尝试 **Unpaywall → OpenAlex**，
  命中作者自存档 / 预印本等「已公开标注为开放获取」的版本即可下载
- **不能下**：付费墙后没有 OA 版本的（IEEE / Elsevier 订阅论文等）——不下载、不绕过，回退到「原文」链接；
  以及连程序化检索都不开放的平台（如中国知网 CNKI），无从下载

已登录用户的订阅权限属于账号行为，本工具**不使用、也不复用**任何登录会话。
各源的具体原因可在页面上点「⬇ PDF」查看，或访问 `GET /api/download/supported`。

> 兜底通道（Unpaywall / OpenAlex）需要联系邮箱进入免费礼貌池，默认沿用 `request.user_agent` 里的地址，
> 可用环境变量 `LITSCAN_CONTACT_EMAIL` 覆盖。

### Q: 下载的 PDF 存在哪？能断点续传吗？

默认存在 `out/pdf/`（可用 `--pdf-dir` 或 `config.yaml` 的 `download.dir` 修改）。
已下载且体积 ≥ `download.min_bytes`（默认 20KB）的文件会自动跳过，因此中断后重跑同一命令即可续传：

```bash
python litscan.py --download                      # 检索后下载
python litscan.py --download-csv out/articles.csv # 从已有结果下载（可反复运行）
```

单次最多下载 `download.limit`（默认 20）篇，相邻下载间有 `download.delay`（默认 1.5s）礼貌间隔，可自行调整。

## 使用

### Q: 历史记录能重跑吗？

能。Web 端在 `/history` 页面点击重跑；CLI 用 `python litscan.py --retry <记录ID>`；API 用 `POST /api/history/retry/{id}`。

### Q: 输出文件在哪里？

统一在 `out/` 目录：`articles.csv`（统一格式结果）、`log.md`（检索日志）、`history.json`（历史）、`raw/`（各库原始响应）。该目录已在 `.gitignore` 中忽略。

### Q: Windows 下终端中文乱码？

`litscan.py` 已内置 UTF-8 输出修复（GBK 环境自动包装 stdout/stderr），如仍出现乱码，可先执行 `chcp 65001` 再运行。
