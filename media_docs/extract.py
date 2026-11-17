"""The text of a document. The server runs it as a child process with limits on memory and time, so a hostile file
can only break that one process.

    python3 -m media_docs.extract <path> <limit>

Prints UTF-8 text of at most <limit> characters. Exit 0 — text; 2 — this kind is not supported; 1 — the file does not
read (the reason on stderr). Kinds by extension: docx, pptx, xlsx, odt, pdf, rtf.
"""

import re
import subprocess
import sys
import zipfile
from xml.etree import ElementTree

# A zip bomb stops here: the XML of a document is read only up to this size unpacked.
XML_MAX = 20 * 1024 * 1024


class Enough(Exception):
    """The text reached the limit: stop reading."""


class Text:
    def __init__(self, limit: int):
        self.limit = limit
        self.parts: list[str] = []
        self.length = 0

    def add(self, line: str) -> None:
        line = line.rstrip()
        if line == '':
            return
        left = self.limit - self.length
        if left <= 0:
            raise Enough()
        piece = (line + '\n')[:left]
        self.parts.append(piece)
        self.length += len(piece)
        if self.length >= self.limit:
            raise Enough()

    def result(self) -> str:
        return ''.join(self.parts)[:self.limit]


def docx(path: str, out: Text) -> None:
    from docx import Document
    document = Document(path)
    for paragraph in document.paragraphs:
        out.add(paragraph.text)
    for table in document.tables:
        for row in table.rows:
            out.add('\t'.join(cell.text for cell in row.cells))


def pptx(path: str, out: Text) -> None:
    from pptx import Presentation
    for number, slide in enumerate(Presentation(path).slides, start=1):
        out.add(f'--- slide {number} ---')
        for shape in slide.shapes:
            if shape.has_text_frame:
                for paragraph in shape.text_frame.paragraphs:
                    out.add(''.join(run.text for run in paragraph.runs))


def xlsx(path: str, out: Text) -> None:
    from openpyxl import load_workbook
    book = load_workbook(path, read_only=True, data_only=True)
    for sheet in book.worksheets:
        out.add(f'--- {sheet.title} ---')
        for row in sheet.iter_rows(values_only=True):
            out.add('\t'.join('' if cell is None else str(cell) for cell in row))


def odt(path: str, out: Text) -> None:
    with zipfile.ZipFile(path) as archive:
        info = archive.getinfo('content.xml')
        if info.file_size > XML_MAX:
            raise ValueError('content.xml is too large')
        data = archive.read(info)
    if b'<!DOCTYPE' in data or b'<!ENTITY' in data:
        raise ValueError('entities are not read')
    text_ns = '{urn:oasis:names:tc:opendocument:xmlns:text:1.0}'
    for element in ElementTree.fromstring(data).iter():  # noqa: S314 - DOCTYPE and entities are refused above
        if element.tag in (text_ns + 'p', text_ns + 'h'):
            out.add(''.join(element.itertext()))


def pdf(path: str, out: Text) -> None:
    done = subprocess.run(['pdftotext', '-layout', '-enc', 'UTF-8', path, '-'], capture_output=True, timeout=25, check=False)  # noqa: S607 - poppler from the image
    if done.returncode != 0:
        raise ValueError(done.stderr.decode('utf-8', 'replace').strip()[:200] or 'pdftotext failed')
    for line in done.stdout.decode('utf-8', 'replace').splitlines():
        out.add(line)


def rtf(path: str, out: Text) -> None:
    with open(path, 'rb') as handle:
        raw = handle.read(XML_MAX).decode('latin-1')
    # destinations {\*...} and font and colour tables are not text
    raw = re.sub(r'\{\\\*[^{}]*(\{[^{}]*\}[^{}]*)*\}', '', raw)
    raw = re.sub(r'\{\\(fonttbl|colortbl|stylesheet|info)[^{}]*(\{[^{}]*\}[^{}]*)*\}', '', raw)
    raw = re.sub(r"\\'([0-9a-fA-F]{2})", lambda m: bytes([int(m.group(1), 16)]).decode('cp1251'), raw)
    raw = re.sub(r'\\u(-?\d+)\??', lambda m: chr(int(m.group(1)) % 65536), raw)
    raw = re.sub(r'\\(par|line)\b ?', '\n', raw)
    raw = re.sub(r'\\[a-zA-Z]+-?\d* ?', '', raw)
    raw = raw.replace('\\{', '{').replace('\\}', '}').replace('{', '').replace('}', '')
    for line in raw.splitlines():
        out.add(re.sub(r'[ \t]+', ' ', line).strip())


READERS = {'docx': docx, 'pptx': pptx, 'xlsx': xlsx, 'odt': odt, 'pdf': pdf, 'rtf': rtf}


def main() -> int:
    if len(sys.argv) != 3 or not sys.argv[2].isdigit():
        print('usage: python3 -m media_docs.extract <path> <limit>', file=sys.stderr)
        return 1
    path, limit = sys.argv[1], int(sys.argv[2])
    reader = READERS.get(path.rsplit('.', 1)[-1].lower() if '.' in path else '')
    if reader is None:
        print('this kind of document is not supported', file=sys.stderr)
        return 2
    out = Text(max(1, limit))
    try:
        reader(path, out)
    except Enough:
        pass
    except Exception as error:  # the file is someone's: any failure is a reason, not a crash
        print(f'{type(error).__name__}: {str(error)[:200]}', file=sys.stderr)
        return 1
    sys.stdout.buffer.write(out.result().encode("utf-8"))
    return 0


if __name__ == '__main__':
    sys.exit(main())
