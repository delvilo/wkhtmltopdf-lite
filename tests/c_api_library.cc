// LGPL-3.0-or-later. Test-only shared facade for ctypes C API regressions.
// --whole-archive retains every public C entry point from libwkhtmltox.a.
namespace { const int wkhtmltox_c_api_test_library = 1; }
