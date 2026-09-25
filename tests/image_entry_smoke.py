#!/usr/bin/env python3
"""Regression checks for CLI startup, image validation and transactional output."""

import argparse
import ctypes
import os
from pathlib import Path
import signal
import struct
import subprocess
import tempfile
import unittest
import zlib
import xml.etree.ElementTree as ET


HTML = b'''<!doctype html><html><body style="margin:0;background:#abcdef">
<h1>Image conversion</h1><div style="width:300px;height:100px">Content</div>
</body></html>'''
ORIGINAL = b'original output file'


class ImageEntrySmoke(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.env = os.environ.copy()
        cls.env.setdefault('QT_QPA_PLATFORM', 'offscreen')

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='image-entry-smoke-')
        self.addCleanup(self.temp.cleanup)
        self.work = Path(self.temp.name)
        self.source = self.work / 'input.html'
        self.source.write_bytes(HTML)

    def executable(self, name):
        return str(BIN_DIR / name)

    def run_image(self, *options, target='-', source=None, env=None, **kwargs):
        source = self.source if source is None else source
        return subprocess.run(
            [self.executable('wkhtmltoimage'), *map(str, options), str(source), str(target)],
            input=HTML if str(source) == '-' else None,
            stdout=kwargs.pop('stdout', subprocess.PIPE), stderr=subprocess.PIPE,
            env=self.env if env is None else env, timeout=20, **kwargs,
        )

    def assert_ok(self, result):
        self.assertEqual(result.returncode, 0, result.stderr.decode(errors='replace'))

    def assert_failed(self, result):
        self.assertEqual(result.returncode, 1, result.stderr.decode(errors='replace'))
        self.assertNotIn(b'Done', result.stderr)

    def png_size(self, data):
        self.assertEqual(data[:8], b'\x89PNG\r\n\x1a\n')
        return struct.unpack('>II', data[16:24])

    def test_help_does_not_initialize_qt(self):
        env = self.env.copy()
        env['QT_QPA_PLATFORM'] = 'deliberately-unavailable-platform'
        for name in ['wkhtmltoimage', 'wkhtmltopdf']:
            for option in ['--help', '--version']:
                with self.subTest(program=name, option=option):
                    result = subprocess.run([self.executable(name), option], env=env,
                                            capture_output=True, timeout=10)
                    self.assert_ok(result)

    def test_default_headless_platform_and_auto_height(self):
        env = self.env.copy()
        for key in ['DISPLAY', 'WAYLAND_DISPLAY', 'QT_QPA_PLATFORM']:
            env.pop(key, None)
        result = self.run_image('--format', 'png', '--width', '400', env=env)
        self.assert_ok(result)
        width, height = self.png_size(result.stdout)
        self.assertEqual(width, 400)
        self.assertGreater(height, 0)

    def test_smart_width_and_transparency_on_standard_qt(self):
        help_result = subprocess.run([self.executable('wkhtmltoimage'), '--extended-help'],
                                     env=self.env, capture_output=True, timeout=10)
        self.assert_ok(help_result)
        for flag in [b'--enable-smart-width', b'--disable-smart-width', b'--transparent']:
            self.assertIn(flag, help_result.stdout)
        self.source.write_text('<html><body style="margin:0"><div style="width:640px;height:80px"></div></body></html>')
        for flag, wide in [('--enable-smart-width', True), ('--disable-smart-width', False)]:
            result = self.run_image('--format', 'png', '--width', '200', flag)
            self.assert_ok(result)
            self.assertNotIn(b'ignored', result.stderr)
            width, _ = self.png_size(result.stdout)
            if wide:
                self.assertGreaterEqual(width, 640)
            else:
                self.assertEqual(width, 200)
        result = self.run_image('--format', 'png', '--width', '100', '--height', '100',
                                '--disable-smart-width', '--transparent')
        self.assert_ok(result)
        self.assertNotIn(b'ignored', result.stderr)
        self.assertEqual(result.stdout[25], 6)  # RGBA PNG
        self.assertEqual(result.stdout[28], 0)  # Non-interlaced
        chunks, position = [], 8
        while position < len(result.stdout):
            size = struct.unpack('>I', result.stdout[position:position + 4])[0]
            if result.stdout[position + 4:position + 8] == b'IDAT':
                chunks.append(result.stdout[position + 8:position + 8 + size])
            position += size + 12
        # At the first pixel of the first row every PNG filter predicts zero.
        first_row = zlib.decompress(b''.join(chunks))
        self.assertEqual(first_row[4], 0)  # Transparent alpha, not just RGBA encoding.

    def test_zoom_changes_image_layout(self):
        self.source.write_text('<html><body style="margin:0"><div style="height:100px">Zoom</div></body></html>')
        heights = []
        for zoom in ['1', '2']:
            result = self.run_image('--format', 'png', '--width', '400', '--zoom', zoom)
            self.assert_ok(result)
            heights.append(self.png_size(result.stdout)[1])
        self.assertEqual(heights, [100, 200])

    def test_invalid_settings_fail_before_loading_or_overwriting(self):
        target = self.work / 'keep.png'
        cases = [
            ('--width', '0', b'width'), ('--width', '-1', b'width'),
            ('--height', '-1', b'height'), ('--quality', '101', b'quality'),
            ('--quality', '-2', b'quality'), ('--crop-x', '-2', b'offset'),
            ('--crop-y', '-2', b'offset'), ('--crop-w', '0', b'Crop dimensions'),
            ('--crop-h', '-2', b'Crop dimensions'),
            ('--format', 'unsupported-format', b'Unsupported output image format'),
        ]
        for option, value, message in cases:
            with self.subTest(option=option, value=value):
                target.write_bytes(ORIGINAL)
                result = self.run_image(option, value, target=target,
                                        source=self.work / 'does-not-exist.html')
                self.assert_failed(result)
                self.assertIn(message, result.stderr)
                self.assertEqual(target.read_bytes(), ORIGINAL)

    def test_format_inference_and_encoder_default(self):
        target = self.work / 'output.PNG'
        result = self.run_image('--quality', '-1', target=target)
        self.assert_ok(result)
        self.png_size(target.read_bytes())
        for fmt, signature in [('PNG', b'\x89PNG'), ('JPEG', b'\xff\xd8'), ('bmp', b'BM')]:
            with self.subTest(format=fmt):
                result = self.run_image('--format', fmt)
                self.assert_ok(result)
                self.assertTrue(result.stdout.startswith(signature))

    def test_missing_format_is_reported(self):
        target = self.work / 'no-extension'
        result = self.run_image(target=target)
        self.assert_failed(result)
        self.assertIn(b'Cannot determine the output image format', result.stderr)
        self.assertFalse(target.exists())

    def test_stdin_crop_and_large_crop_values(self):
        result = self.run_image('--format', 'png', '--width', '400', '--height', '200',
                                '--crop-x', '10', '--crop-y', '20', '--crop-w', '160',
                                '--crop-h', '90', source='-')
        self.assert_ok(result)
        self.assertEqual(self.png_size(result.stdout), (160, 90))
        result = self.run_image('--format', 'png', '--width', '400', '--height', '200',
                                '--crop-x', '10', '--crop-y', '20',
                                '--crop-w', '2147483647', '--crop-h', '2147483647')
        self.assert_ok(result)
        self.assertEqual(self.png_size(result.stdout), (390, 180))

    def test_empty_crop_preserves_existing_file(self):
        target = self.work / 'keep.png'
        target.write_bytes(ORIGINAL)
        result = self.run_image('--crop-x', '2147483647', target=target)
        self.assert_failed(result)
        self.assertIn(b'Will not output an empty image', result.stderr)
        self.assertEqual(target.read_bytes(), ORIGINAL)

    def test_successful_file_replacement_and_svg(self):
        target = self.work / 'replace.png'
        target.write_bytes(ORIGINAL)
        target.chmod(0o640)
        before = set(self.work.iterdir())
        self.assert_ok(self.run_image(target=target))
        self.png_size(target.read_bytes())
        self.assertEqual(set(self.work.iterdir()), before)
        self.assertEqual(target.stat().st_mode & 0o777, 0o640)
        target = self.work / 'vector.svg'
        self.assert_ok(self.run_image(target=target))
        self.assertEqual(ET.fromstring(target.read_bytes()).tag, '{http://www.w3.org/2000/svg}svg')

    def test_invalid_output_destinations(self):
        directory = self.work / 'directory'
        directory.mkdir()
        marker = directory / 'keep'
        marker.write_bytes(ORIGINAL)
        for target in [directory, self.work / 'missing-parent' / 'output.png']:
            with self.subTest(target=target):
                result = self.run_image('--format', 'png', target=target)
                self.assert_failed(result)
                self.assertIn(b'Could not open image output', result.stderr)
        self.assertEqual(marker.read_bytes(), ORIGINAL)

    def test_write_failure_preserves_file_and_removes_temporary_output(self):
        import resource

        def limit_output_size():
            signal.signal(signal.SIGXFSZ, signal.SIG_IGN)
            resource.setrlimit(resource.RLIMIT_FSIZE, (32, 32))

        for extension in ['png', 'svg']:
            with self.subTest(format=extension):
                target = self.work / ('keep.' + extension)
                target.write_bytes(ORIGINAL)
                before = set(self.work.iterdir())
                result = self.run_image(target=target, preexec_fn=limit_output_size)
                self.assert_failed(result)
                self.assertEqual(target.read_bytes(), ORIGINAL)
                self.assertEqual(set(self.work.iterdir()), before)

    @unittest.skipUnless(Path('/dev/full').exists(), 'Requires /dev/full')
    def test_stdout_write_failure(self):
        for fmt in ['png', 'svg']:
            with self.subTest(format=fmt):
                with open('/dev/full', 'wb') as sink:
                    result = self.run_image('--format', fmt, stdout=sink)
                self.assert_failed(result)

    def test_existing_symlink_is_preserved(self):
        target = self.work / 'target.png'
        target.write_bytes(ORIGINAL)
        alias = self.work / 'alias.png'
        alias.symlink_to(target.name)
        self.assert_ok(self.run_image(target=alias))
        self.assertTrue(alias.is_symlink())
        self.png_size(target.read_bytes())

    def test_c_api_finishes_once_for_success_and_failure(self):
        path = BIN_DIR / 'libwkhtmltox.so'
        self.assertTrue(path.exists())
        lib = ctypes.CDLL(str(path))
        ptr, text = ctypes.c_void_p, ctypes.c_char_p
        callback_type = ctypes.CFUNCTYPE(None, ptr, ctypes.c_int)

        def bind(name, args, result):
            fn = getattr(lib, 'wkhtmltoimage_' + name)
            fn.argtypes, fn.restype = args, result
            return fn

        initialize = bind('init', [ctypes.c_int], ctypes.c_int)
        deinitialize = bind('deinit', [], ctypes.c_int)
        create_settings = bind('create_global_settings', [], ptr)
        set_setting = bind('set_global_setting', [ptr, text, text], ctypes.c_int)
        create_converter = bind('create_converter', [ptr, text], ptr)
        destroy = bind('destroy_converter', [ptr], None)
        set_finished = bind('set_finished_callback', [ptr, callback_type], None)
        convert = bind('convert', [ptr], ctypes.c_int)
        get_output = bind('get_output', [ptr, ctypes.POINTER(ptr)], ctypes.c_long)
        self.assertEqual(initialize(0), 1)
        try:
            cases = [({'fmt': 'png'}, True, b'\x89PNG'), ({}, True, b'\xff\xd8'),
                     ({'fmt': 'svg'}, True, b'<?xml'),
                     ({'fmt': 'unsupported-format'}, False, b''),
                     ({'fmt': 'png', 'out': str(self.work)}, False, b''),
                     ({'fmt': 'png', 'screenWidth': '0'}, False, b'')]
            for settings, success, signature in cases:
                with self.subTest(settings=settings):
                    gs = create_settings()
                    for key, value in dict(settings, logLevel='none').items():
                        self.assertEqual(set_setting(gs, key.encode(), value.encode()), 1)
                    converter = create_converter(gs, HTML)
                    finished = []
                    callback = callback_type(lambda _, result: finished.append(result))
                    set_finished(converter, callback)
                    try:
                        self.assertEqual(convert(converter), int(success))
                        self.assertEqual(finished, [int(success)])
                        data = ptr()
                        length = get_output(converter, ctypes.byref(data))
                        if success:
                            self.assertGreater(length, 0)
                            self.assertTrue(ctypes.string_at(data, length).startswith(signature))
                        else:
                            self.assertEqual(length, 0)
                    finally:
                        destroy(converter)
        finally:
            deinitialize()

    def test_c_api_get_setting_bounds_check(self):
        path = BIN_DIR / 'libwkhtmltox.so'
        self.assertTrue(path.exists())
        lib = ctypes.CDLL(str(path))
        ptr, text = ctypes.c_void_p, ctypes.c_char_p

        img_create_gs = getattr(lib, 'wkhtmltoimage_create_global_settings')
        img_create_gs.argtypes, img_create_gs.restype = [], ptr
        img_destroy_gs = getattr(lib, 'wkhtmltoimage_destroy_global_settings')
        img_destroy_gs.argtypes, img_destroy_gs.restype = [ptr], None
        img_set_gs = getattr(lib, 'wkhtmltoimage_set_global_setting')
        img_set_gs.argtypes, img_set_gs.restype = [ptr, text, text], ctypes.c_int
        img_get_gs = getattr(lib, 'wkhtmltoimage_get_global_setting')
        img_get_gs.argtypes, img_get_gs.restype = [ptr, text, text, ctypes.c_int], ctypes.c_int

        pdf_create_gs = getattr(lib, 'wkhtmltopdf_create_global_settings')
        pdf_create_gs.argtypes, pdf_create_gs.restype = [], ptr
        pdf_destroy_gs = getattr(lib, 'wkhtmltopdf_destroy_global_settings')
        pdf_destroy_gs.argtypes, pdf_destroy_gs.restype = [ptr], None
        pdf_set_gs = getattr(lib, 'wkhtmltopdf_set_global_setting')
        pdf_set_gs.argtypes, pdf_set_gs.restype = [ptr, text, text], ctypes.c_int
        pdf_get_gs = getattr(lib, 'wkhtmltopdf_get_global_setting')
        pdf_get_gs.argtypes, pdf_get_gs.restype = [ptr, text, text, ctypes.c_int], ctypes.c_int

        pdf_create_os = getattr(lib, 'wkhtmltopdf_create_object_settings')
        pdf_create_os.argtypes, pdf_create_os.restype = [], ptr
        pdf_destroy_os = getattr(lib, 'wkhtmltopdf_destroy_object_settings')
        pdf_destroy_os.argtypes, pdf_destroy_os.restype = [ptr], None
        pdf_set_os = getattr(lib, 'wkhtmltopdf_set_object_setting')
        pdf_set_os.argtypes, pdf_set_os.restype = [ptr, text, text], ctypes.c_int
        pdf_get_os = getattr(lib, 'wkhtmltopdf_get_object_setting')
        pdf_get_os.argtypes, pdf_get_os.restype = [ptr, text, text, ctypes.c_int], ctypes.c_int

        # Image global settings
        gs = img_create_gs()
        try:
            self.assertEqual(img_set_gs(gs, b'fmt', b'png'), 1)
            buf = ctypes.create_string_buffer(64)
            # Valid call
            self.assertEqual(img_get_gs(gs, b'fmt', buf, 64), 1)
            self.assertEqual(buf.value, b'png')
            # Null value buffer pointer
            self.assertEqual(img_get_gs(gs, b'fmt', None, 64), 0)
            # Zero buffer size
            self.assertEqual(img_get_gs(gs, b'fmt', buf, 0), 0)
            # Negative buffer size
            self.assertEqual(img_get_gs(gs, b'fmt', buf, -1), 0)
        finally:
            img_destroy_gs(gs)

        # PDF global settings
        gs = pdf_create_gs()
        try:
            self.assertEqual(pdf_set_gs(gs, b'orientation', b'Landscape'), 1)
            buf = ctypes.create_string_buffer(64)
            # Valid call
            self.assertEqual(pdf_get_gs(gs, b'orientation', buf, 64), 1)
            self.assertEqual(buf.value, b'Landscape')
            # Null value buffer pointer
            self.assertEqual(pdf_get_gs(gs, b'orientation', None, 64), 0)
            # Zero buffer size
            self.assertEqual(pdf_get_gs(gs, b'orientation', buf, 0), 0)
            # Negative buffer size
            self.assertEqual(pdf_get_gs(gs, b'orientation', buf, -1), 0)
        finally:
            pdf_destroy_gs(gs)

        # PDF object settings
        os_obj = pdf_create_os()
        try:
            self.assertEqual(pdf_set_os(os_obj, b'page', b'http://example.com'), 1)
            buf = ctypes.create_string_buffer(64)
            # Valid call
            self.assertEqual(pdf_get_os(os_obj, b'page', buf, 64), 1)
            self.assertEqual(buf.value, b'http://example.com')
            # Null value buffer pointer
            self.assertEqual(pdf_get_os(os_obj, b'page', None, 64), 0)
            # Zero buffer size
            self.assertEqual(pdf_get_os(os_obj, b'page', buf, 0), 0)
            # Negative buffer size
            self.assertEqual(pdf_get_os(os_obj, b'page', buf, -1), 0)
        finally:
            pdf_destroy_os(os_obj)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bin-dir', type=Path, default=Path(__file__).resolve().parents[1] / 'bin')
    BIN_DIR = parser.parse_args().bin_dir.resolve()
    unittest.main(argv=[__file__], verbosity=2)
