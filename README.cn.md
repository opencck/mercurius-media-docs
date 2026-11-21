[English](README.md) | [Русский](README.ru.md) | **中文**

> 本文由模型翻译，尚未经人工审校；如有出入，以英文版为准。

# mercurius-media-docs

一个用 Python 编写的小型 HTTP 服务：提取办公文档和 PDF 的文本，并根据纯 JSON 描述生成新的 `docx`、`xlsx` 和 `pptx` 文件。它是 [Mercurius](https://github.com/opencck/mercurius) 的一个模块，也可以单独使用。有了该模块，智能体可以读取收到的文档，并按需制作文档；没有它智能体照样能工作，
只是没有文档工具，而且这些库不会进入智能体的沙箱。

## API

除 `/health` 外，每个路由都需要 `Authorization: Bearer <MEDIA_DOCS_TOKEN>`。

| 路由 | 请求体 | 响应 |
|---|---|---|
| `GET /health` | — | `{"status":"ok","module":"media-docs"}` |
| `POST /extract?name=a.docx&limit=20000` | 文件 | `{"text": "..."}`，最多 `limit` 个字符。支持的类型：docx、pptx、xlsx、odt、pdf、rtf |
| `POST /build` | JSON 描述 | 文件（`docx`、`xlsx` 或 `pptx`） |

错误：没有令牌返回 `401`，请求体超过限制返回 `413`，不支持读取的类型返回 `415`，文件无法读取或描述无法生成文档时返回带 `error` 的 `422`，`500` 不附带细节。

文件在子进程中解析，并限制内存（768 MB）、CPU 时间和实际耗时，因此恶意文件最多只能破坏该进程。含有 `DOCTYPE` 或实体的 ODT 会被拒绝；文档内部的 XML 解压后最多只读取 20 MB。

### 描述

```json
{"format": "docx", "title": "Report", "blocks": [
  {"type": "heading", "text": "Results", "level": 1},
  {"type": "paragraph", "text": "All is well."},
  {"type": "bullets", "items": ["one", "two"]},
  {"type": "numbers", "items": ["first", "second"]},
  {"type": "table", "rows": [["Name", "Sum"], ["Ivan", "10"]], "header": true},
  {"type": "page_break"}]}

{"format": "xlsx", "sheets": [{"name": "Costs", "rows": [["Item", "Sum"], ["Bread", 50], ["Total", "=SUM(B2:B2)"]],
  "header": true, "widths": [20, 10]}]}

{"format": "pptx", "title": "Plan", "subtitle": "2026", "slides": [
  {"title": "Goals", "bullets": ["growth", "quality"], "notes": "speaker notes"},
  {"title": "Numbers", "table": [["Q1", "Q2"], ["1", "2"]]}]}
```

`xlsx` 中以 `=` 开头的单元格是公式。限制：2000 个块、200 张幻灯片、50 个工作表、20 000 行、200
列、每段文本 20 000 个字符。

## 设置

| 变量 | 默认值 | 含义 |
|---|---|---|
| `MEDIA_DOCS_TOKEN` | — | 必填，至少 16 个字符 |
| `MEDIA_DOCS_PORT` | `8092` | 端口 |
| `MEDIA_DOCS_HOST` | `0.0.0.0` | 地址 |
| `MEDIA_DOCS_MAX_MB` | `25` | 请求体的最大大小 |
| `MEDIA_DOCS_TIMEOUT` | `30` | 读取单个文件的秒数 |

## 运行

```sh
docker build -t mercurius-media-docs .
docker run --rm -e MEDIA_DOCS_TOKEN=$(openssl rand -hex 32) -p 8092:8092 mercurius-media-docs
```

在 Mercurius 中，该服务位于 compose 配置 `media-docs` 下：把它加入 `COMPOSE_PROFILES`，并在 `.env` 中设置
`MEDIA_DOCS_TOKEN`。

## 开发

```sh
pip install -r requirements-dev.txt
sh check.sh   # unittest and ruff
```

## 许可证

MIT
