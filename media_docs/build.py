"""New documents from a plain description: the agent says what goes in, the module makes the file.

    docx: {"format": "docx", "title": "...", "blocks": [
              {"type": "heading", "text": "...", "level": 1},
              {"type": "paragraph", "text": "..."},
              {"type": "bullets", "items": ["...", "..."]},
              {"type": "numbers", "items": ["...", "..."]},
              {"type": "table", "rows": [["a", "b"], ["1", "2"]], "header": true},
              {"type": "page_break"}]}
    xlsx: {"format": "xlsx", "sheets": [{"name": "...", "rows": [["a", 1], ["b", 2.5]], "header": true,
                                          "widths": [20, 10]}]}
    pptx: {"format": "pptx", "title": "...", "subtitle": "...", "slides": [
              {"title": "...", "bullets": ["...", "..."], "text": "...", "notes": "...",
               "table": [["a", "b"], ["1", "2"]]}]}

A cell of xlsx that starts with "=" is a formula. Limits keep a description small: see LIMITS.
"""

from io import BytesIO
from typing import Any

FORMATS = ('docx', 'xlsx', 'pptx')
LIMITS = {'blocks': 2000, 'slides': 200, 'sheets': 50, 'rows': 20000, 'columns': 200, 'text': 20000}
MIME = {
    'docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    'xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    'pptx': 'application/vnd.openxmlformats-officedocument.presentationml.presentation',
}


class BadSpec(ValueError):
    """The description does not make a document; the message says why, for the agent."""


def build(spec: Any) -> bytes:
    if not isinstance(spec, dict):
        raise BadSpec('the description is a JSON object')
    kind = spec.get('format')
    if kind not in FORMATS:
        raise BadSpec('format is one of: ' + ', '.join(FORMATS))
    return {'docx': _docx, 'xlsx': _xlsx, 'pptx': _pptx}[kind](spec)


def _text(value: Any, what: str) -> str:
    if value is None:
        return ''
    if isinstance(value, bool) or not isinstance(value, (str, int, float)):
        raise BadSpec(f'{what} is text')
    text = str(value)
    if len(text) > LIMITS['text']:
        raise BadSpec(f'{what} is longer than {LIMITS["text"]} characters')
    return text


def _list(value: Any, what: str, limit: int) -> list:
    if value is None:
        return []
    if not isinstance(value, list):
        raise BadSpec(f'{what} is a list')
    if len(value) > limit:
        raise BadSpec(f'{what}: at most {limit}')
    return value


def _rows(value: Any, what: str) -> list[list[Any]]:
    rows = _list(value, what, LIMITS['rows'])
    for row in rows:
        if not isinstance(row, list) or len(row) > LIMITS['columns']:
            raise BadSpec(f'{what}: each row is a list of at most {LIMITS["columns"]} cells')
    return rows


def _save(document: Any) -> bytes:
    out = BytesIO()
    document.save(out)
    return out.getvalue()


def _docx(spec: dict) -> bytes:
    from docx import Document
    from docx.enum.text import WD_BREAK
    document = Document()
    title = _text(spec.get('title'), 'title')
    if title:
        document.core_properties.title = title
        document.add_heading(title, level=0)
    for number, block in enumerate(_list(spec.get('blocks'), 'blocks', LIMITS['blocks']), start=1):
        if not isinstance(block, dict):
            raise BadSpec(f'block {number} is an object')
        kind = block.get('type')
        if kind == 'heading':
            level = block.get('level', 1)
            document.add_heading(_text(block.get('text'), f'block {number} text'), level=level if isinstance(level, int) and 1 <= level <= 6 else 1)
        elif kind == 'paragraph':
            document.add_paragraph(_text(block.get('text'), f'block {number} text'))
        elif kind in ('bullets', 'numbers'):
            style = 'List Bullet' if kind == 'bullets' else 'List Number'
            for item in _list(block.get('items'), f'block {number} items', LIMITS['rows']):
                document.add_paragraph(_text(item, f'block {number} item'), style=style)
        elif kind == 'table':
            rows = _rows(block.get('rows'), f'block {number} rows')
            if rows:
                width = max(len(row) for row in rows) or 1
                table = document.add_table(rows=len(rows), cols=width)
                table.style = 'Table Grid'
                for r, row in enumerate(rows):
                    for c, cell in enumerate(row):
                        table.cell(r, c).text = _text(cell, f'block {number} cell')
                        if r == 0 and block.get('header', True):
                            for run in table.cell(r, c).paragraphs[0].runs:
                                run.bold = True
        elif kind == 'page_break':
            document.add_paragraph().add_run().add_break(WD_BREAK.PAGE)
        else:
            raise BadSpec(f'block {number}: type is heading, paragraph, bullets, numbers, table or page_break')
    return _save(document)


def _xlsx(spec: dict) -> bytes:
    from openpyxl import Workbook
    from openpyxl.styles import Font
    book = Workbook()
    book.remove(book.active)
    sheets = _list(spec.get('sheets'), 'sheets', LIMITS['sheets']) or [{'name': 'Sheet1', 'rows': []}]
    total = 0
    for number, sheet in enumerate(sheets, start=1):
        if not isinstance(sheet, dict):
            raise BadSpec(f'sheet {number} is an object')
        name = _text(sheet.get('name'), f'sheet {number} name')[:31] or f'Sheet{number}'
        for bad in '[]:*?/\\':
            name = name.replace(bad, ' ')
        page = book.create_sheet(name)
        rows = _rows(sheet.get('rows'), f'sheet {number} rows')
        total += len(rows)
        if total > LIMITS['rows']:
            raise BadSpec(f'at most {LIMITS["rows"]} rows in all')
        for row in rows:
            page.append([cell if isinstance(cell, (int, float)) and not isinstance(cell, bool) else _text(cell, f'sheet {number} cell') for cell in row])
        if rows and sheet.get('header', True):
            for cell in page[1]:
                cell.font = Font(bold=True)
            page.freeze_panes = 'A2'
        for index, width in enumerate(_list(sheet.get('widths'), f'sheet {number} widths', LIMITS['columns']), start=1):
            if isinstance(width, (int, float)) and 1 <= width <= 255:
                from openpyxl.utils import get_column_letter
                page.column_dimensions[get_column_letter(index)].width = width
    return _save(book)


def _pptx(spec: dict) -> bytes:
    from pptx import Presentation
    from pptx.util import Inches
    deck = Presentation()
    deck.slide_width = Inches(13.333)
    deck.slide_height = Inches(7.5)
    title = _text(spec.get('title'), 'title')
    if title:
        slide = deck.slides.add_slide(deck.slide_layouts[0])
        slide.shapes.title.text = title
        slide.placeholders[1].text = _text(spec.get('subtitle'), 'subtitle')
    for number, item in enumerate(_list(spec.get('slides'), 'slides', LIMITS['slides']), start=1):
        if not isinstance(item, dict):
            raise BadSpec(f'slide {number} is an object')
        table = _rows(item.get('table'), f'slide {number} table')
        layout = deck.slide_layouts[5 if table else 1]
        slide = deck.slides.add_slide(layout)
        slide.shapes.title.text = _text(item.get('title'), f'slide {number} title')
        if table:
            width = max(len(row) for row in table) or 1
            shape = slide.shapes.add_table(len(table), width, Inches(0.6), Inches(1.6), Inches(12.1), Inches(0.4) * len(table))
            for r, row in enumerate(table):
                for c, cell in enumerate(row):
                    shape.table.cell(r, c).text = _text(cell, f'slide {number} cell')
        else:
            body = slide.placeholders[1].text_frame
            lines = [_text(line, f'slide {number} bullet') for line in _list(item.get('bullets'), f'slide {number} bullets', 50)]
            text = _text(item.get('text'), f'slide {number} text')
            lines = lines or ([text] if text else [])
            for index, line in enumerate(lines):
                paragraph = body.paragraphs[0] if index == 0 else body.add_paragraph()
                paragraph.text = line
        notes = _text(item.get('notes'), f'slide {number} notes')
        if notes:
            slide.notes_slide.notes_text_frame.text = notes
    if len(deck.slides) == 0:
        raise BadSpec('a presentation needs a title or slides')
    return _save(deck)
