"""The HTTP side, behind a bearer token.

    GET  /health                       {"status": "ok", "module": "media-docs"} — open
    POST /extract?name=a.docx&limit=N  the file in the body; {"text": "..."} or 415 (kind not read) / 422 (does not read)
    POST /build                        JSON description (see build.py); the file, or 422 with the reason

A file is parsed in a child process with limits on memory, CPU time and wall time; a larger body than the limit is
refused before it is read. Environment: MEDIA_DOCS_TOKEN (16+ characters), MEDIA_DOCS_PORT (8092), MEDIA_DOCS_HOST,
MEDIA_DOCS_MAX_MB (25), MEDIA_DOCS_TIMEOUT (30 s).
"""

import hmac
import json
import os
import subprocess
import sys
import tempfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from . import build as builder
from .extract import READERS

MEMORY = 768 * 1024 * 1024


def _limits() -> None:  # pragma: no cover - runs in the child
    import resource
    resource.setrlimit(resource.RLIMIT_AS, (MEMORY, MEMORY))
    resource.setrlimit(resource.RLIMIT_CPU, (60, 60))


def extract(data: bytes, name: str, limit: int, timeout: float) -> tuple[int, str]:
    """(status, text or reason): 200 text, 415 not supported, 422 does not read."""
    kind = name.rsplit('.', 1)[-1].lower() if '.' in name else ''
    if kind not in READERS:
        return 415, 'this kind of document is not read: ' + ', '.join(sorted(READERS))
    with tempfile.TemporaryDirectory(prefix='media-docs-') as folder:
        path = os.path.join(folder, 'input.' + kind)
        with open(path, 'wb') as handle:
            handle.write(data)
        try:
            done = subprocess.run(
                [sys.executable, '-m', 'media_docs.extract', path, str(limit)],
                capture_output=True, timeout=timeout, cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                preexec_fn=_limits if os.name == 'posix' else None,
                env={**os.environ, 'PYTHONIOENCODING': 'utf-8'},
            )
        except subprocess.TimeoutExpired:
            return 422, f'the document took longer than {int(timeout)} s'
    if done.returncode == 0:
        return 200, done.stdout.decode('utf-8', 'replace')
    reason = done.stderr.decode('utf-8', 'replace').strip()[-300:] or f'exit {done.returncode}'
    return (415 if done.returncode == 2 else 422), reason


class Handler(BaseHTTPRequestHandler):
    token = ''
    max_bytes = 25_000_000
    timeout_seconds = 30.0
    server_version = 'media-docs'
    sys_version = ''

    def log_message(self, format: str, *args: object) -> None:  # quiet: no file names in logs
        return

    def _send(self, status: int, body: bytes, kind: str = 'application/json') -> None:
        self.send_response(status)
        self.send_header('content-type', kind)
        self.send_header('content-length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _json(self, status: int, data: dict) -> None:
        self._send(status, json.dumps(data, ensure_ascii=False).encode('utf-8'))

    def do_GET(self) -> None:
        if urlparse(self.path).path == '/health':
            self._json(200, {'status': 'ok', 'module': 'media-docs'})
        else:
            self._send(404, b'')

    def do_POST(self) -> None:
        url = urlparse(self.path)
        try:
            length = int(self.headers.get('content-length', '0'))
        except ValueError:
            length = -1
        given = self.headers.get('authorization', '').strip()
        refused = 404 if url.path not in ('/extract', '/build') else 401 if not hmac.compare_digest(given.encode(), ('Bearer ' + self.token).encode()) else 0
        if refused:
            # a small unread body would reset the connection before the answer is read; a large one is not read
            if 0 < length <= 65536:
                self.rfile.read(length)
            self.close_connection = True
            self._send(refused, b'')
            return
        if length < 0 or length > self.max_bytes:
            self.close_connection = True
            self._json(413, {'error': f'the body is larger than {self.max_bytes // 1_000_000} MB'})
            return
        body = self.rfile.read(length) if length else b''
        if body == b'':
            self._json(400, {'error': 'the body is empty'})
            return
        query = parse_qs(url.query)
        if url.path == '/extract':
            limit = query.get('limit', ['20000'])[0]
            status, text = extract(body, query.get('name', [''])[0], int(limit) if limit.isdigit() else 20000, self.timeout_seconds)
            self._json(status, {'text': text} if status == 200 else {'error': text})
            return
        try:
            spec = json.loads(body)
            data = builder.build(spec)
        except (ValueError, builder.BadSpec) as error:
            self._json(422, {'error': str(error)[:300]})
            return
        except Exception:  # noqa: BLE001 - no details out
            self._json(500, {'error': 'internal error'})
            return
        self._send(200, data, builder.MIME[spec['format']])


def main() -> int:
    token = os.environ.get('MEDIA_DOCS_TOKEN', '')
    if len(token) < 16:
        print('MEDIA_DOCS_TOKEN is required (16+ characters)', file=sys.stderr)
        return 78
    Handler.token = token
    Handler.max_bytes = max(1, min(500, int(os.environ.get('MEDIA_DOCS_MAX_MB') or 25))) * 1_000_000
    Handler.timeout_seconds = max(5.0, min(600.0, float(os.environ.get('MEDIA_DOCS_TIMEOUT') or 30)))
    host = os.environ.get('MEDIA_DOCS_HOST') or '0.0.0.0'
    port = int(os.environ.get('MEDIA_DOCS_PORT') or 8092)
    server = ThreadingHTTPServer((host, port), Handler)
    server.daemon_threads = True
    print(f'media-docs listening on {host}:{port}', file=sys.stderr)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == '__main__':
    sys.exit(main())
