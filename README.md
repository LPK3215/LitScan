# LitScan 学术文献多库检索工具

给关键词，自动从多个学术数据库拉取文章信息，输出标准化结果。

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.9%2B-blue.svg)](https://www.python.org/)

## 快速开始

```bash
pip install -r requirements.txt
python litscan.py --serve     # 启动服务，访问 http://127.0.0.1:8000
```

## 三种使用方式

### 1. Web 页面（推荐）

```bash
python litscan.py --serve     # 打开浏览器访问 http://127.0.0.1:8000
```

页面:
- `/` — 检索页面（输入关键词、选数据源、看结果，支持 SSE 流式进度）
- `/history` — 检索历史（查看/重跑/删除）
- `/sources` — 数据源列表
- `/logs` — 操作日志（查看运行日志与统计）

### 2. CLI 模式

```bash
python litscan.py                          # 用 config.yaml
python litscan.py -k "my research topic"   # 命令行指定关键词
python litscan.py -k "LLM agent" -y 2023 -l 20
python litscan.py --history                # 查看搜索历史
python litscan.py --sources                # 列出检索源
```

### 3. API 模式

```bash
python litscan.py --serve                   # http://127.0.0.1:8000
```

API 接口:

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | /api/sources | 列出检索源 |
| POST | /api/search | 多库检索 |
| POST | /api/search/{source} | 单库检索 |
| GET | /api/articles | 最近一次结果 |
| GET | /api/history | 搜索历史 |
| POST | /api/history/search | 搜索历史记录 |
| POST | /api/history/retry/{id} | 从历史重新检索 |
| DELETE | /api/history/{id} | 删除历史记录 |
| DELETE | /api/history | 清空历史 |

调用示例:

```bash
curl -X POST http://127.0.0.1:8000/api/search \
  -H "Content-Type: application/json" \
  -d '{"keywords": "LLM agent evaluation", "limit_per_source": 10}'
```

## 支持检索源

| 库 | 格式 | 说明 |
|---|---|---|
| arXiv | XML | 预印本, 免费无上限 |
| Semantic Scholar | JSON | 429限流, 自动重试 |
| Crossref | JSON | DOI注册库 |
| OpenReview | JSON | 顶会评审 |
| OpenAIRE | JSON | 欧盟开放科学 |
| DOAJ | JSON | 开放获取期刊 |
| Europe PMC | JSON | 生物医学 |

## 输出

```
out/
├── raw/              # 各库原始响应
├── articles.csv      # 统一格式文章列表
├── log.md            # 检索日志
└── history.json      # 搜索历史
```

## 代理配置

配置文件 config.yaml:
```yaml
request:
  proxy: "http://127.0.0.1:7897"   # 你的代理地址
```

或不配，自动读取系统环境变量 http_proxy / https_proxy。
加 `--no-proxy` 参数可强制不走代理。

### 常见代理问题

**SSL 握手失败 / Connection reset**
- Clash 代理开启了 SSL 拦截但证书不被信任
- 解决方法:
  1. Clash 里开启 "跳过 TLS 验证" (Skip TLS Verification)
  2. 或安装 Clash 的 root 证书到系统信任区
  3. 或把代理模式从 "Global" 切到 "Rule"，避免学术流量走代理

## 项目结构

```
LitScan/
├── litscan.py           # CLI 入口
├── config.yaml          # 配置文件
├── requirements.txt
├── core/
│   ├── fetcher.py       # HTTP + 重试 + 限流处理
│   ├── adapters.py      # 各库适配器
│   ├── scanner.py       # 调度器
│   ├── history.py       # 搜索历史
│   └── output.py        # CSV/日志输出
├── server/
│   └── main.py          # FastAPI 后端 + 模板路由
├── templates/           # Jinja2 模板
│   ├── base.html
│   ├── index.html
│   ├── history.html
│   └── sources.html
└── static/
    └── style.css        # 样式
```

## 后续可加

- 跨库去重 (DOI主键匹配)
- 检索结果引用数排序
- 导出 BibTeX / EndNote
