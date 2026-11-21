**English** | [Русский](README.ru.md) | [中文](README.cn.md)

# mercurius-media-docs

A small HTTP service in Python: the text of office documents and PDF, and new `docx`, `xlsx` and `pptx` files made
from a plain JSON description. It is a module of [Mercurius](https://github.com/opencck/mercurius) and can be used on
its own. With the module the agent reads documents it receives and makes documents on request; without it the agent
works too, it just has no documents tool, and the libraries stay out of the agent's sandbox.

## API

Every route except `/health` needs `Authorization: Bearer <MEDIA_DOCS_TOKEN>`.

| Route | Body | Answer |
|---|---|---|
| `GET /health` | — | `{"status":"ok","module":"media-docs"}` |
| `POST /extract?name=a.docx&limit=20000` | the file | `{"text": "..."}`, at most `limit` characters. Kinds: docx, pptx, xlsx, odt, pdf, rtf |
| `POST /build` | JSON description | the file (`docx`, `xlsx` or `pptx`) |

Errors: `401` without the token, `413` for a body over the limit, `415` for a kind that is not read, `422` with
`error` when a file does not read or a description does not make a document, `500` without details.

A file is parsed in a child process with limits on memory (768 MB), CPU time and wall time, so a hostile file can only
break that process. ODT with `DOCTYPE` or entities is refused; XML inside a document is read only up to 20 MB unpacked.

### Descriptions

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

A cell of `xlsx` that starts with `=` is a formula. Limits: 2000 blocks, 200 slides, 50 sheets, 20 000 rows, 200
columns, 20 000 characters per text.

## Settings

| Variable | Default | Meaning |
|---|---|---|
| `MEDIA_DOCS_TOKEN` | — | required, 16+ characters |
| `MEDIA_DOCS_PORT` | `8092` | port |
| `MEDIA_DOCS_HOST` | `0.0.0.0` | address |
| `MEDIA_DOCS_MAX_MB` | `25` | the largest body |
| `MEDIA_DOCS_TIMEOUT` | `30` | seconds to read one file |

## Run

```sh
docker build -t mercurius-media-docs .
docker run --rm -e MEDIA_DOCS_TOKEN=$(openssl rand -hex 32) -p 8092:8092 mercurius-media-docs
```

In Mercurius the service is in the compose profile `media-docs`: add it to `COMPOSE_PROFILES` and set
`MEDIA_DOCS_TOKEN` in `.env`.

## Development

```sh
pip install -r requirements-dev.txt
sh check.sh   # unittest and ruff
```

## License

MIT
