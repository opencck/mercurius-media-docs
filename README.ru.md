[English](README.md) | **Русский**

# mercurius-media-docs

Небольшой HTTP-сервис на Python: текст офисных документов и PDF и новые файлы `docx`, `xlsx` и `pptx` по простому
описанию в JSON. Модуль [Меркурия](https://github.com/opencck/mercurius), работает и сам по себе. С модулем агент читает
присланные документы и делает документы по просьбе; без него агент тоже работает — просто без инструмента документов, а
библиотеки не лежат в его песочнице.

## API

Все пути, кроме `/health`, требуют `Authorization: Bearer <MEDIA_DOCS_TOKEN>`.

| Путь | Тело | Ответ |
|---|---|---|
| `GET /health` | — | `{"status":"ok","module":"media-docs"}` |
| `POST /extract?name=a.docx&limit=20000` | файл | `{"text": "..."}`, не больше `limit` символов. Виды: docx, pptx, xlsx, odt, pdf, rtf |
| `POST /build` | описание в JSON | файл (`docx`, `xlsx` или `pptx`) |

Ошибки: `401` без токена, `413` — тело больше предела, `415` — такой вид не читается, `422` с `error` — файл не
читается или описание не складывается в документ, `500` — без подробностей.

Файл разбирается в дочернем процессе с пределами памяти (768 МБ), процессорного и общего времени — враждебный файл
сломает только этот процесс. ODT с `DOCTYPE` или сущностями отклоняется; XML внутри документа читается не больше 20 МБ в
распакованном виде.

### Описания

```json
{"format": "docx", "title": "Отчёт", "blocks": [
  {"type": "heading", "text": "Итоги", "level": 1},
  {"type": "paragraph", "text": "Всё хорошо."},
  {"type": "bullets", "items": ["раз", "два"]},
  {"type": "numbers", "items": ["первое", "второе"]},
  {"type": "table", "rows": [["Имя", "Сумма"], ["Иван", "10"]], "header": true},
  {"type": "page_break"}]}

{"format": "xlsx", "sheets": [{"name": "Расход", "rows": [["Статья", "Сумма"], ["Хлеб", 50], ["Итого", "=SUM(B2:B2)"]],
  "header": true, "widths": [20, 10]}]}

{"format": "pptx", "title": "План", "subtitle": "2026", "slides": [
  {"title": "Цели", "bullets": ["рост", "качество"], "notes": "заметки докладчика"},
  {"title": "Цифры", "table": [["Q1", "Q2"], ["1", "2"]]}]}
```

Ячейка `xlsx`, которая начинается с `=`, — формула. Пределы: 2000 блоков, 200 слайдов, 50 листов, 20 000 строк, 200
столбцов, 20 000 символов в тексте.

## Настройки

| Переменная | По умолчанию | Смысл |
|---|---|---|
| `MEDIA_DOCS_TOKEN` | — | обязательна, от 16 символов |
| `MEDIA_DOCS_PORT` | `8092` | порт |
| `MEDIA_DOCS_HOST` | `0.0.0.0` | адрес |
| `MEDIA_DOCS_MAX_MB` | `25` | наибольшее тело |
| `MEDIA_DOCS_TIMEOUT` | `30` | секунд на чтение одного файла |

## Запуск

```sh
docker build -t mercurius-media-docs .
docker run --rm -e MEDIA_DOCS_TOKEN=$(openssl rand -hex 32) -p 8092:8092 mercurius-media-docs
```

В Меркурии сервис — в профиле compose `media-docs`: добавьте его в `COMPOSE_PROFILES` и задайте `MEDIA_DOCS_TOKEN` в
`.env`.

## Разработка

```sh
pip install -r requirements-dev.txt
sh check.sh   # unittest и ruff
```

## Лицензия

MIT
