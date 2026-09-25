#!/usr/bin/env python3
"""Exercise the loading/rendering boundary against a local HTTP fixture."""

import argparse
import base64
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import os
from pathlib import Path
import subprocess
import tempfile
import threading
import unittest
from urllib.parse import parse_qs


HTML = b'<html><body style="margin:0;background:#123456"></body></html>'
AUTHORIZATION = 'Basic ' + base64.b64encode(b'reader:secret').decode()


class FixtureHandler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_GET(self):
        self.respond()

    def do_POST(self):
        self.respond()

    def respond(self):
        data = self.rfile.read(int(self.headers.get('Content-Length', 0)))
        self.server.requests.append((self.command, self.path, self.headers, data))
        status, headers, body = 200, {'Content-Type': 'text/html'}, HTML
        if self.path == '/redirect':
            status, body = 302, b''
            headers.update(Location='/page', **{'Set-Cookie': 'session=baseline; Path=/'})
        elif self.path == '/page':
            body = b'<html><head><link rel="stylesheet" href="/asset.css"></head><body></body></html>'
        elif self.path == '/asset.css':
            headers['Content-Type'] = 'text/css'
            body = b'body { margin:0; background:#123456; }'
        elif self.path == '/auth' and self.headers.get('Authorization') != AUTHORIZATION:
            status, body = 401, b'Authentication required'
            headers['WWW-Authenticate'] = 'Basic realm="renderer-fixture"'
        elif self.path == '/missing':
            status, body = 404, b'Not found'
        self.send_response(status)
        for name, value in headers.items():
            self.send_header(name, value)
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class RenderingBackendSmoke(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(('127.0.0.1', 0), FixtureHandler)
        cls.server.requests = []
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base = 'http://127.0.0.1:' + str(cls.server.server_port)
        cls.env = os.environ.copy()
        cls.env.setdefault('QT_QPA_PLATFORM', 'offscreen')
        for name in ['http_proxy', 'https_proxy', 'all_proxy', 'HTTP_PROXY', 'HTTPS_PROXY', 'ALL_PROXY']:
            cls.env.pop(name, None)
        cls.env['no_proxy'] = cls.env['NO_PROXY'] = '127.0.0.1,localhost'

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=5)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='rendering-backend-')
        self.addCleanup(self.temp.cleanup)
        self.work = Path(self.temp.name)
        self.server.requests.clear()

    def convert(self, program, *options, source=None, data=None):
        args = [str(BIN_DIR / program), '--log-level', 'warn']
        if program == 'wkhtmltoimage':
            args += ['--format', 'png', '--width', '100', '--height', '80']
        args += list(map(str, options)) + [str(source if source is not None else '-'), '-']
        return subprocess.run(args, input=data, env=self.env, capture_output=True, timeout=20)

    def assert_ok(self, result, program):
        self.assertEqual(result.returncode, 0, result.stderr.decode(errors='replace'))
        signature = b'%PDF-' if program == 'wkhtmltopdf' else b'\x89PNG\r\n\x1a\n'
        self.assertTrue(result.stdout.startswith(signature))

    def test_redirect_cookie_headers_and_stylesheet(self):
        for program in ['wkhtmltopdf', 'wkhtmltoimage']:
            with self.subTest(program=program):
                self.server.requests.clear()
                jar = self.work / (program + '.cookies')
                result = self.convert(program, '--custom-header', 'X-Renderer', 'webkit',
                                      '--custom-header-propagation', '--cookie', 'extra', 'one',
                                      '--cookie-jar', jar, source=self.base + '/redirect')
                self.assert_ok(result, program)
                for path in ['/page', '/asset.css']:
                    request = next(item for item in self.server.requests if item[1] == path)
                    self.assertEqual(request[2].get('X-Renderer'), 'webkit')
                    self.assertIn('session=baseline', request[2].get('Cookie', ''))
                    self.assertIn('extra=one', request[2].get('Cookie', ''))
                self.assertIn('session=baseline', jar.read_text())
                if program == 'wkhtmltoimage':
                    reference = self.convert(program, data=HTML)
                    self.assert_ok(reference, program)
                    self.assertEqual(result.stdout, reference.stdout)

    def test_authentication_and_post(self):
        for program in ['wkhtmltopdf', 'wkhtmltoimage']:
            with self.subTest(program=program):
                result = self.convert(program, '--username', 'reader', '--password', 'secret',
                                      source=self.base + '/auth')
                self.assert_ok(result, program)
                self.assertTrue(any(item[2].get('Authorization') == AUTHORIZATION
                                    for item in self.server.requests))
                result = self.convert(program, '--post', 'name', 'two words', source=self.base + '/post')
                self.assert_ok(result, program)
                request = next(item for item in reversed(self.server.requests) if item[1] == '/post')
                self.assertEqual(request[0], 'POST')
                self.assertEqual(parse_qs(request[3].decode()), {'name': ['two words']})

    def test_authentication_failures(self):
        for program in ['wkhtmltopdf', 'wkhtmltoimage']:
            with self.subTest(program=program, case='missing_credentials'):
                result = self.convert(program, '--load-error-handling', 'abort', source=self.base + '/auth')
                self.assertEqual(result.returncode, 1, result.stderr.decode(errors='replace'))
                self.assertIn(b'Authentication Required', result.stderr)

            with self.subTest(program=program, case='invalid_credentials'):
                result = self.convert(program, '--username', 'invalid', '--password', 'wrong',
                                      '--load-error-handling', 'abort', source=self.base + '/auth')
                self.assertEqual(result.returncode, 1, result.stderr.decode(errors='replace'))
                self.assertIn(b'Invalid username or password', result.stderr)

    def test_javascript_status_and_disabled_scripts(self):
        program = 'wkhtmltoimage'
        red = b'<html><body style="margin:0;background:red"></body></html>'
        script = "window.setTimeout(function(){document.body.style.backgroundColor='#123456';window.status='ready';},100)"
        result = self.convert(program, '--run-script', script, '--window-status', 'ready',
                              '--javascript-delay', '20', data=red)
        self.assert_ok(result, program)
        reference = self.convert(program, data=HTML)
        self.assert_ok(reference, program)
        self.assertEqual(result.stdout, reference.stdout)
        scripted = red.replace(b'</body>', b'<script>document.body.style.backgroundColor="blue";</script></body>')
        disabled = self.convert(program, '--disable-javascript', data=scripted)
        self.assert_ok(disabled, program)
        reference = self.convert(program, data=red)
        self.assert_ok(reference, program)
        self.assertEqual(disabled.stdout, reference.stdout)

    def test_user_stylesheet(self):
        stylesheet = self.work / 'style.css'
        stylesheet.write_text('body { margin:0 !important; background:#123456 !important; }')
        result = self.convert('wkhtmltoimage', '--user-style-sheet', stylesheet,
                              '--enable-local-file-access', data=b'<html><body></body></html>')
        self.assert_ok(result, 'wkhtmltoimage')
        reference = self.convert('wkhtmltoimage', data=HTML)
        self.assert_ok(reference, 'wkhtmltoimage')
        self.assertEqual(result.stdout, reference.stdout)

    def test_http_failure_propagates(self):
        for program in ['wkhtmltopdf', 'wkhtmltoimage']:
            with self.subTest(program=program):
                result = self.convert(program, '--load-error-handling', 'abort', source=self.base + '/missing')
                self.assertEqual(result.returncode, 1, result.stderr.decode(errors='replace'))
                self.assertIn(b'http status code 404', result.stderr)
                self.assertIn(b'ContentNotFoundError', result.stderr)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bin-dir', type=Path, default=Path(__file__).resolve().parents[1] / 'bin')
    BIN_DIR = parser.parse_args().bin_dir.resolve()
    unittest.main(argv=[__file__], verbosity=2)
