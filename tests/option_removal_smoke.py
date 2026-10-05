#!/usr/bin/env python3
"""Exercise the reduced CLI and C API using freshly built binaries."""

import argparse
import os
from pathlib import Path
import re
import struct
import subprocess
import tempfile
import unittest


SHARED_REMOVED = {
    'quiet', 'readme', 'htmldoc', 'enable-plugins', 'disable-plugins',
    'use-xserver', 'checkbox-svg', 'checkbox-checked-svg',
    'radiobutton-svg', 'radiobutton-checked-svg',
}
PDF_REMOVED = SHARED_REMOVED | {
    'default-header', 'lowquality', 'copies', 'collate', 'no-collate',
    'no-pdf-compression', 'enable-forms', 'disable-forms',
    'read-args-from-stdin', 'dump-outline', 'dump-default-toc-xsl',
    'image-quality', 'image-dpi', 'outline', 'no-outline', 'outline-depth',
    'viewport-size', 'include-in-outline', 'exclude-from-outline',
    'disable-smart-shrinking', 'enable-smart-shrinking', 'print-media-type',
    'no-print-media-type', 'disable-internal-links', 'enable-internal-links',
    'disable-external-links', 'enable-external-links', 'resolve-relative-links',
    'keep-relative-links', 'enable-toc-back-links', 'disable-toc-back-links',
    'page-offset', 'replace', 'xsl-style-sheet', 'toc-header-text',
    'disable-toc-links', 'disable-dotted-lines', 'toc-text-size-shrink',
    'toc-level-indentation',
    *{prefix + suffix for prefix in ['header-', 'footer-']
      for suffix in ['center', 'font-name', 'font-size', 'left', 'line', 'right', 'spacing', 'html']},
    'no-header-line', 'no-footer-line',
}
HTML = b'''<!doctype html><html><head><meta charset="utf-8"></head>
<body><h1>Conversion smoke test</h1><p>Text remains visible.</p>
<input value="Static form value"><input type="checkbox" checked>
<input type="radio" checked></body></html>'''


class OptionRemovalSmoke(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix='wkhtmltox-smoke-')
        cls.work = Path(cls.temp.name)
        cls.source = cls.work / 'input.html'
        cls.source.write_bytes(HTML)
        cls.env = os.environ.copy()
        cls.env.setdefault('QT_QPA_PLATFORM', 'offscreen')

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    @classmethod
    def run_cli(cls, name, *args, data=None):
        executable = BIN_DIR / name
        return subprocess.run(
            [str(executable), *map(str, args)], input=data,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            env=cls.env, timeout=40,
        )

    def assert_success(self, result):
        self.assertEqual(result.returncode, 0, result.stderr.decode(errors='replace'))

    def assert_pdf(self, data, pages=None):
        self.assertTrue(data.startswith(b'%PDF-'), data[:120])
        self.assertIn(b'%%EOF', data[-100:])
        if pages is not None:
            self.assertEqual(len(re.findall(rb'/Type\s*/Page(?=[\s/>])', data)), pages)
        self.assertNotIn(b'/AcroForm', data)
        self.assertNotIn(b'/Outlines', data)
        self.assertIsNone(re.search(rb'/Subtype\s*/Link', data), 'PDF must not contain clickable link annotations')

    def test_removed_cli_options_and_short_aliases(self):
        for name, options in [('wkhtmltopdf', PDF_REMOVED), ('wkhtmltoimage', SHARED_REMOVED)]:
            for option in sorted(options):
                with self.subTest(program=name, option=option):
                    result = self.run_cli(name, '--' + option)
                    self.assertNotEqual(result.returncode, 0)
                    self.assertIn(('Unknown long argument --' + option).encode(), result.stderr)
            aliases = ['-q', '-l'] if name == 'wkhtmltopdf' else ['-q']
            for alias in aliases:
                with self.subTest(program=name, alias=alias):
                    result = self.run_cli(name, alias)
                    self.assertNotEqual(result.returncode, 0)
                    self.assertIn(b'Unknown switch', result.stderr)

    def test_help_and_manpage(self):
        for name, options in [('wkhtmltopdf', PDF_REMOVED), ('wkhtmltoimage', SHARED_REMOVED)]:
            for switch in ['--extended-help', '--manpage']:
                with self.subTest(program=name, switch=switch):
                    result = self.run_cli(name, switch)
                    self.assert_success(result)
                    output = (result.stdout + result.stderr).replace(b'\\-', b'-')
                    advertised = set(re.findall(rb'--([a-z][a-z-]*)', output))
                    self.assertFalse(advertised.intersection(option.encode() for option in options))
                    self.assertIn(b'log-level', advertised)

    def test_error_handling_values(self):
        for name in ['wkhtmltopdf', 'wkhtmltoimage']:
            for value in ['abort', 'ignore']:
                with self.subTest(program=name, policy=value):
                    self.assert_success(self.run_cli(name, '--load-media-error-handling', value, '--version'))
            result = self.run_cli(name, '--load-media-error-handling', 'skip', '--version')
            self.assertNotEqual(result.returncode, 0)
            self.assertIn(b'Invalid argument(s)', result.stderr)
            self.assert_success(self.run_cli(name, '--load-error-handling', 'skip', '--version'))

    def test_pdf_file_and_stdin_stdout(self):
        target = self.work / 'output.pdf'
        self.assert_success(self.run_cli('wkhtmltopdf', '--log-level', 'none', self.source, target))
        self.assert_pdf(target.read_bytes(), pages=1)
        result = self.run_cli('wkhtmltopdf', '--log-level', 'none', '-', '-', data=HTML)
        self.assert_success(result)
        self.assert_pdf(result.stdout, pages=1)

    def test_image_stdin_stdout_and_crop(self):
        result = self.run_cli(
            'wkhtmltoimage', '--log-level', 'none', '--format', 'png',
            '--width', '320', '--height', '180', '--crop-w', '160', '--crop-h', '90',
            '-', '-', data=HTML,
        )
        self.assert_success(result)
        self.assertEqual(result.stdout[:8], b'\x89PNG\r\n\x1a\n')
        self.assertEqual(struct.unpack('>II', result.stdout[16:24]), (160, 90))

    def test_rejects_multiple_inputs_and_object_commands(self):
        target = self.work / 'rejected.pdf'
        for inputs in [[], [self.source, self.source], ['cover', self.source],
                       ['toc', self.source], ['page', self.source]]:
            with self.subTest(inputs=inputs):
                target.write_bytes(b'original')
                result = self.run_cli('wkhtmltopdf', *inputs, target)
                self.assertEqual(result.returncode, 1)
                self.assertNotIn(b'Loading', result.stderr)
                self.assertEqual(target.read_bytes(), b'original')

    def test_one_html_can_produce_multiple_pages_without_pdf_links(self):
        html = b'''<html><head><title>Single input</title></head><body>
        <h1 id="first">First page</h1><a href="#last">Internal link text</a>
        <a href="https://example.org/">External link text</a>
        <div style="page-break-before:always">Second page</div>
        <div id="last" style="page-break-before:always">Third page</div>
        </body></html>'''
        result = self.run_cli('wkhtmltopdf', '--log-level', 'none', '-', '-', data=html)
        self.assert_success(result)
        self.assert_pdf(result.stdout, pages=3)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bin-dir', type=Path, default=Path(__file__).resolve().parents[1] / 'bin')
    args = parser.parse_args()
    BIN_DIR = args.bin_dir.resolve()
    unittest.main(argv=[__file__], verbosity=2)
