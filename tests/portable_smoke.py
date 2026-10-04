#!/usr/bin/env python3
"""Exercise relocated executables, static image plugins, CJK fonts and HTTPS.

SPDX-License-Identifier: LGPL-3.0-or-later
"""
import argparse
import base64
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import os
from pathlib import Path
import shutil
import ssl
import subprocess
import tempfile
import threading
import unittest
import zlib
import struct


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


class PortableSmoke(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix='wkhtmltox-relocated-')
        cls.work = Path(cls.temp.name)
        cls.env = {k: v for k, v in os.environ.items() if not (
            k.startswith(('QT_', 'QML', 'LD_')) or k.lower().endswith('_proxy') or
            k in ('DISPLAY', 'WAYLAND_DISPLAY', 'QTDIR'))}
        cls.env.update(LANG='C.UTF-8', LC_ALL='C.UTF-8')
        for app in ('wkhtmltopdf', 'wkhtmltoimage'):
            shutil.copy2(BIN_DIR / app, cls.work / app)
        cls.page = cls.work / 'page.html'
        cls.page.write_text('<!doctype html><meta charset="utf-8">'
                           '<body style="font-family:DejaVu Sans,Noto Sans CJK TC">'
                           '<h1>Portable PDF 中文測試</h1><p>Static QtWebKit</p></body>')

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def run_tool(self, app, *args, data=None):
        result = subprocess.run([str(self.work / app), *map(str, args)], input=data,
                                cwd=self.work, env=self.env, capture_output=True, timeout=45)
        self.assertEqual(result.returncode, 0, result.stderr.decode(errors='replace'))
        return result.stdout

    def test_fonts_and_paginated_pdf(self):
        target = self.work / 'text.pdf'
        self.run_tool('wkhtmltopdf', self.page, target)
        extracted = subprocess.check_output(['pdftotext', str(target), '-'], text=True)
        self.assertIn('Portable PDF', extracted)
        self.assertIn('中文測試', extracted)
        fonts = subprocess.check_output(['pdffonts', str(target)], text=True)
        self.assertIn('Noto', fonts)
        source = self.work / 'pages.html'
        source.write_text('<div>First page</div><div style="page-break-before:always">Second page</div>')
        self.run_tool('wkhtmltopdf', source, target)
        info = subprocess.check_output(['pdfinfo', str(target)], text=True, env=self.env)
        self.assertRegex(info, r'Pages:\s+2\b')

    def test_jpeg_plugin_and_svg_image_input(self):
        jpeg = self.run_tool('wkhtmltoimage', '--format', 'jpg', '--width', '32', '--height', '32', '-', '-',
                             data=b'<body style="margin:0;background:red"></body>')
        self.assertTrue(jpeg.startswith(b'\xff\xd8\xff'))
        source = self.work / 'images.html'
        source.write_text('<body style="margin:0"><img style="position:absolute;left:0;top:0" src="data:image/jpeg;base64,' +
                          base64.b64encode(jpeg).decode() + '"><img style="position:absolute;left:32px;top:0" src="data:image/svg+xml;base64,' +
                          base64.b64encode(b'<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16">'
                                           b'<rect width="16" height="16" fill="blue"/></svg>').decode() + '"></body>')
        png = self.run_tool('wkhtmltoimage', '--format', 'png', '--width', '64', '--height', '32', source, '-')
        self.assertTrue(png.startswith(b'\x89PNG\r\n\x1a\n'))
        # Decode the first PNG row to prove the JPEG and SVG pixels rendered.
        self.assertIn(png[25], (2, 6))
        bpp = 3 if png[25] == 2 else 4
        data, offset = b'', 8
        while offset < len(png):
            size = struct.unpack('>I', png[offset:offset + 4])[0]
            if png[offset + 4:offset + 8] == b'IDAT':
                data += png[offset + 8:offset + 8 + size]
            offset += size + 12
        row = zlib.decompress(data)
        mode, pixels = row[0], bytearray(row[1:1 + 64 * bpp])
        for i in range(len(pixels)):
            left = pixels[i - bpp] if i >= bpp else 0
            prediction = (0, left, 0, left // 2, left)[mode]
            pixels[i] = (pixels[i] + prediction) & 255
        red = pixels[8 * bpp:8 * bpp + 3]
        self.assertGreater(red[0], 240)
        self.assertLess(max(red[1:]), 15)
        self.assertEqual(pixels[40 * bpp:40 * bpp + 3], b'\x00\x00\xff')
        svg = self.run_tool('wkhtmltoimage', '--format', 'svg', '--width', '100', '--height', '80', self.page, '-')
        self.assertIn(b'<svg', svg)

    def test_https_and_dns_after_relocation(self):
        cert, key = self.work / 'server.crt', self.work / 'server.key'
        subprocess.run(['openssl', 'req', '-x509', '-newkey', 'rsa:2048', '-nodes', '-days', '1',
                        '-subj', '/CN=localhost', '-addext', 'subjectAltName=DNS:localhost',
                        '-keyout', str(key), '-out', str(cert)], check=True, capture_output=True)
        server = ThreadingHTTPServer(('127.0.0.1', 0), partial(QuietHandler, directory=str(self.work)))
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(cert, key)
        server.socket = context.wrap_socket(server.socket, server_side=True)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            url = f'https://localhost:{server.server_port}/page.html'
            self.assertTrue(self.run_tool('wkhtmltopdf', url, '-').startswith(b'%PDF-'))
            self.assertTrue(self.run_tool('wkhtmltoimage', '--format', 'png', '--width', '200',
                                          '--height', '100', url, '-').startswith(b'\x89PNG'))
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)
        # This checks TLS loading, not peer verification: the existing loader
        # ignores certificate errors. Changing that policy is a separate change.


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bin-dir', type=Path, required=True)
    BIN_DIR = parser.parse_args().bin_dir.resolve()
    unittest.main(argv=[__file__], verbosity=2)
