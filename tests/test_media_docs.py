import json
import socket
import threading
import unittest
import urllib.error
import urllib.request
import zipfile
from http.server import ThreadingHTTPServer
from io import BytesIO

from media_docs import build as builder
from media_docs.server import Handler, extract

TOKEN = 'token-0123456789abcdef'


class BuildAndExtract(unittest.TestCase):
    def test_docx_round_trip(self) -> None:
        data = builder.build({'format': 'docx', 'title': 'Отчёт', 'blocks': [
            {'type': 'heading', 'text': 'Итоги', 'level': 2},
            {'type': 'paragraph', 'text': 'Всё хорошо.'},
            {'type': 'bullets', 'items': ['раз', 'два']},
            {'type': 'table', 'rows': [['Имя', 'Сумма'], ['Иван', '10']]},
            {'type': 'page_break'},
        ]})
        status, text = extract(data, 'report.docx', 20000, 30)
        self.assertEqual(200, status, text)
        for piece in ('Отчёт', 'Итоги', 'Всё хорошо.', 'раз', 'Иван\t10'):
            self.assertIn(piece, text)

    def test_xlsx_round_trip_with_a_formula(self) -> None:
        rows = [['Статья', 'Сумма'], ['Хлеб', 50], ['Итого', '=SUM(B2:B2)']]
        data = builder.build({'format': 'xlsx', 'sheets': [{'name': 'Расход/2026', 'rows': rows, 'widths': [20, 10]}]})
        with zipfile.ZipFile(BytesIO(data)) as archive:
            sheet = archive.read('xl/worksheets/sheet1.xml').decode()
        self.assertIn('SUM(B2:B2)', sheet)
        status, text = extract(data, 'a.xlsx', 20000, 30)
        self.assertEqual(200, status, text)
        self.assertIn('Расход 2026', text)
        self.assertIn('Хлеб\t50', text)

    def test_pptx_round_trip(self) -> None:
        data = builder.build({'format': 'pptx', 'title': 'План', 'subtitle': '2026', 'slides': [
            {'title': 'Цели', 'bullets': ['рост', 'качество'], 'notes': 'сказать про сроки'},
            {'title': 'Цифры', 'table': [['Q1', 'Q2'], ['1', '2']]},
        ]})
        status, text = extract(data, 'deck.pptx', 20000, 30)
        self.assertEqual(200, status, text)
        for piece in ('План', 'Цели', 'рост', 'Цифры'):
            self.assertIn(piece, text)

    def test_limit_cuts_the_text(self) -> None:
        data = builder.build({'format': 'docx', 'blocks': [{'type': 'paragraph', 'text': 'x' * 500}]})
        status, text = extract(data, 'a.docx', 100, 30)
        self.assertEqual(200, status)
        self.assertLessEqual(len(text), 100)

    def test_unknown_kind_and_broken_file(self) -> None:
        self.assertEqual(415, extract(b'data', 'a.exe', 100, 30)[0])
        status, reason = extract(b'not a zip', 'a.docx', 100, 30)
        self.assertEqual(422, status)
        self.assertTrue(reason)

    def test_odt_with_entities_is_refused(self) -> None:
        out = BytesIO()
        with zipfile.ZipFile(out, 'w') as archive:
            archive.writestr('content.xml', '<!DOCTYPE x [<!ENTITY a "b">]><x/>')
        status, reason = extract(out.getvalue(), 'a.odt', 100, 30)
        self.assertEqual(422, status)
        self.assertIn('entities', reason)

    def test_bad_descriptions(self) -> None:
        for spec, says in (
            ([], 'object'),
            ({'format': 'exe'}, 'format'),
            ({'format': 'docx', 'blocks': [{'type': 'video'}]}, 'type'),
            ({'format': 'docx', 'blocks': [{'type': 'paragraph', 'text': {'a': 1}}]}, 'text'),
            ({'format': 'xlsx', 'sheets': [{'rows': [['a'] * 500]}]}, 'cells'),
            ({'format': 'pptx'}, 'title or slides'),
        ):
            with self.assertRaises(builder.BadSpec) as caught:
                builder.build(spec)
            self.assertIn(says, str(caught.exception))


class Http(unittest.TestCase):
    server: ThreadingHTTPServer

    @classmethod
    def setUpClass(cls) -> None:
        Handler.token = TOKEN
        Handler.max_bytes = 2_000_000
        cls.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.shutdown()
        cls.server.server_close()

    def call(self, path: str, body: bytes | None = None, token: str | None = TOKEN) -> tuple[int, bytes, str]:
        request = urllib.request.Request(f'http://127.0.0.1:{self.server.server_address[1]}{path}', data=body, method='GET' if body is None else 'POST')
        if token is not None:
            request.add_header('authorization', 'Bearer ' + token)
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                return response.status, response.read(), response.headers.get('content-type', '')
        except urllib.error.HTTPError as error:
            return error.code, error.read(), error.headers.get('content-type', '')

    def test_health_is_open(self) -> None:
        status, body, _ = self.call('/health', token=None)
        self.assertEqual(200, status)
        self.assertEqual('ok', json.loads(body)['status'])

    def test_token_is_required(self) -> None:
        self.assertEqual(401, self.call('/build', b'{}', token=None)[0])
        self.assertEqual(401, self.call('/build', b'{}', token='wrong-token-0123456789')[0])
        self.assertEqual(404, self.call('/shell', b'x')[0])

    def test_too_large(self) -> None:
        # only the headers: the answer comes before a byte of the body is read
        with socket.create_connection(('127.0.0.1', self.server.server_address[1]), timeout=10) as sock:
            head = f'POST /extract?name=a.docx HTTP/1.1|Host: x|Authorization: Bearer {TOKEN}|Content-Length: 2000001||'
            sock.sendall(head.replace('|', chr(13) + chr(10)).encode())
            self.assertTrue(sock.recv(100).startswith(b'HTTP/1.0 413'))

    def test_build_then_extract(self) -> None:
        status, data, kind = self.call('/build', json.dumps({'format': 'docx', 'blocks': [{'type': 'paragraph', 'text': 'Привет'}]}).encode())
        self.assertEqual(200, status)
        self.assertEqual(builder.MIME['docx'], kind)
        status, body, _ = self.call('/extract?name=hello.docx&limit=1000', data)
        self.assertEqual(200, status)
        self.assertIn('Привет', json.loads(body)['text'])

    def test_bad_description_is_unprocessable(self) -> None:
        status, body, _ = self.call('/build', b'{"format": "exe"}')
        self.assertEqual(422, status)
        self.assertIn('format', json.loads(body)['error'])


if __name__ == '__main__':
    unittest.main()
