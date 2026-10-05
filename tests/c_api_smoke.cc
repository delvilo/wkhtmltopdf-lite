// SPDX-License-Identifier: LGPL-3.0-or-later
// Native equivalents of the C API regressions, linked to libwkhtmltox.a.
#include "image.h"
#include "pdf.h"

#include <cstdlib>
#include <cstring>
#include <initializer_list>
#include <iostream>
#include <memory>
#include <regex>
#include <stdexcept>
#include <string>
#include <vector>
#include <unistd.h>

#define CHECK(condition) do { if (!(condition)) throw std::runtime_error( \
    std::string("line ") + std::to_string(__LINE__) + ": " #condition); } while (false)

namespace {
const char html[] = "<!doctype html><html><head><meta charset='utf-8'></head>"
    "<body><h1>Conversion smoke test</h1><p>Text remains visible.</p>"
    "<input value='Static form value'><input type='checkbox' checked>"
    "<input type='radio' checked></body></html>";

template<class T>
std::unique_ptr<T, void (*)(T*)> own(T* pointer, void (*destroy)(T*)) {
    CHECK(pointer);
    return std::unique_ptr<T, void (*)(T*)>(pointer, destroy);
}

struct Application {
    int (*deinit)();
    Application(int (*init)(int), int (*cleanup)()) : deinit(cleanup) {
        CHECK(init(0) == 1);
    }
    ~Application() { deinit(); }
};

struct TemporaryDirectory {
    std::string path;
    TemporaryDirectory() {
        char pattern[] = "/tmp/wkhtmltox-c-api-XXXXXX";
        const char* created = mkdtemp(pattern);
        CHECK(created);
        path = created;
    }
    ~TemporaryDirectory() { rmdir(path.c_str()); }
};

std::vector<int> finished;
template<class Converter>
void onFinished(Converter*, int result) { finished.push_back(result); }

template<class Settings>
void checkBounds(Settings* settings,
                 int (*set)(Settings*, const char*, const char*),
                 int (*get)(Settings*, const char*, char*, int),
                 const char* key, const char* expected) {
    char buffer[64] = {};
    CHECK(set(settings, key, expected) == 1);
    CHECK(get(settings, key, buffer, sizeof(buffer)) == 1);
    CHECK(std::strcmp(buffer, expected) == 0);
    CHECK(get(settings, key, nullptr, sizeof(buffer)) == 0);
    CHECK(get(settings, key, buffer, 0) == 0);
    CHECK(get(settings, key, buffer, -1) == 0);
}

void settingsBounds() {
    auto image = own(wkhtmltoimage_create_global_settings(), wkhtmltoimage_destroy_global_settings);
    checkBounds(image.get(), wkhtmltoimage_set_global_setting, wkhtmltoimage_get_global_setting, "fmt", "png");
    auto pdf = own(wkhtmltopdf_create_global_settings(), wkhtmltopdf_destroy_global_settings);
    checkBounds(pdf.get(), wkhtmltopdf_set_global_setting, wkhtmltopdf_get_global_setting, "orientation", "Landscape");
    auto object = own(wkhtmltopdf_create_object_settings(), wkhtmltopdf_destroy_object_settings);
    checkBounds(object.get(), wkhtmltopdf_set_object_setting, wkhtmltopdf_get_object_setting, "page", "http://example.com");
}

template<class Settings>
void removedSettings(Settings* settings,
                     int (*set)(Settings*, const char*, const char*),
                     int (*get)(Settings*, const char*, char*, int),
                     std::initializer_list<const char*> removed) {
    char buffer[100] = {};
    for (const char* key : removed) {
        CHECK(get(settings, key, buffer, sizeof(buffer)) == 0);
        CHECK(set(settings, key, "true") == 0);
    }
    CHECK(set(settings, "logLevel", "none") == 1);
    CHECK(get(settings, "logLevel", buffer, sizeof(buffer)) == 1);
    CHECK(std::strcmp(buffer, "none") == 0);
}

void checkPdf(const unsigned char* bytes, long length) {
    CHECK(bytes && length > 0);
    const std::string data(reinterpret_cast<const char*>(bytes), length);
    CHECK(data.compare(0, 5, "%PDF-") == 0);
    CHECK(data.substr(data.size() > 100 ? data.size() - 100 : 0).find("%%EOF") != std::string::npos);
    CHECK(data.find("/AcroForm") == std::string::npos);
    CHECK(data.find("/Outlines") == std::string::npos);
    CHECK(!std::regex_search(data, std::regex("/Subtype\\s*/Link")));
    const std::regex page("/Type\\s*/Page(?=[\\s/>])");
    CHECK(std::distance(std::sregex_iterator(data.begin(), data.end(), page), std::sregex_iterator()) == 1);
}

void pdfSettingsAndConversion() {
    Application app(wkhtmltopdf_init, wkhtmltopdf_deinit);
    TemporaryDirectory work;
    auto pdf = own(wkhtmltopdf_create_global_settings(), wkhtmltopdf_destroy_global_settings);
    removedSettings(pdf.get(), wkhtmltopdf_set_global_setting, wkhtmltopdf_get_global_setting,
        {"quiet", "useGraphics", "resolution", "copies", "collate", "dumpOutline", "useCompression",
         "resolveRelativeLinks", "pageOffset", "outline", "outlineDepth", "viewportSize", "imageDPI", "imageQuality"});
    auto image = own(wkhtmltoimage_create_global_settings(), wkhtmltoimage_destroy_global_settings);
    removedSettings(image.get(), wkhtmltoimage_set_global_setting, wkhtmltoimage_get_global_setting,
        {"quiet", "useGraphics", "loadPage.checkboxSvg", "loadPage.checkboxCheckedSvg",
         "loadPage.radiobuttonSvg", "loadPage.radiobuttonCheckedSvg", "loadPage.printMediaType",
         "web.enableIntelligentShrinking"});
    auto object = own(wkhtmltopdf_create_object_settings(), wkhtmltopdf_destroy_object_settings);
    for (const char* key : {"produceForms", "web.enablePlugins", "load.checkboxSvg", "load.checkboxCheckedSvg",
            "load.radiobuttonSvg", "load.radiobuttonCheckedSvg", "header.left", "footer.right", "toc.captionText",
            "tocXsl", "isTableOfContent", "includeInOutline", "pagesCount", "useExternalLinks", "useLocalLinks",
            "replacements", "web.enableIntelligentShrinking", "web.printMediaType", "load.printMediaType"}) {
        CHECK(wkhtmltopdf_set_object_setting(object.get(), key, "true") == 0);
    }
    CHECK(wkhtmltopdf_set_object_setting(object.get(), "web.enableJavascript", "false") == 1);
    CHECK(wkhtmltopdf_set_object_setting(object.get(), "load.loadErrorHandling", "skip") == 1);
    CHECK(wkhtmltopdf_extended_qt() == 0);

    struct Case { int count; std::string output; bool success; };
    const Case cases[] = {{0, "", false}, {2, "", false}, {1, "", true},
                          {1, work.path + "/missing/output.pdf", false}};
    for (const auto& test : cases) {
        auto settings = own(wkhtmltopdf_create_global_settings(), wkhtmltopdf_destroy_global_settings);
        CHECK(wkhtmltopdf_set_global_setting(settings.get(), "logLevel", "none") == 1);
        CHECK(wkhtmltopdf_set_global_setting(settings.get(), "out", test.output.c_str()) == 1);
        auto converter = own(wkhtmltopdf_create_converter(settings.release()), wkhtmltopdf_destroy_converter);
        for (int i = 0; i < test.count; ++i) {
            auto input = own(wkhtmltopdf_create_object_settings(), wkhtmltopdf_destroy_object_settings);
            wkhtmltopdf_add_object(converter.get(), input.release(), html);
        }
        finished.clear();
        wkhtmltopdf_set_finished_callback(converter.get(), onFinished<wkhtmltopdf_converter>);
        CHECK(wkhtmltopdf_convert(converter.get()) == int(test.success));
        CHECK(finished == std::vector<int>{int(test.success)});
        const unsigned char* output = nullptr;
        const long length = wkhtmltopdf_get_output(converter.get(), &output);
        if (test.success) checkPdf(output, length);
        else CHECK(length == 0);
    }
}

void imageConversion() {
    Application app(wkhtmltoimage_init, wkhtmltoimage_deinit);
    TemporaryDirectory work;
    struct Case { const char* format; const char* output; const char* width; bool success; const char* signature; };
    const Case cases[] = {
        {"png", nullptr, nullptr, true, "\x89PNG"},
        {nullptr, nullptr, nullptr, true, "\xff\xd8"},
        {"svg", nullptr, nullptr, true, "<?xml"},
        {"unsupported-format", nullptr, nullptr, false, ""},
        {"png", work.path.c_str(), nullptr, false, ""},
        {"png", nullptr, "0", false, ""}
    };
    for (const auto& test : cases) {
        auto settings = own(wkhtmltoimage_create_global_settings(), wkhtmltoimage_destroy_global_settings);
        CHECK(wkhtmltoimage_set_global_setting(settings.get(), "logLevel", "none") == 1);
        if (test.format) CHECK(wkhtmltoimage_set_global_setting(settings.get(), "fmt", test.format) == 1);
        if (test.output) CHECK(wkhtmltoimage_set_global_setting(settings.get(), "out", test.output) == 1);
        if (test.width) CHECK(wkhtmltoimage_set_global_setting(settings.get(), "screenWidth", test.width) == 1);
        auto converter = own(wkhtmltoimage_create_converter(settings.release(), html), wkhtmltoimage_destroy_converter);
        finished.clear();
        wkhtmltoimage_set_finished_callback(converter.get(), onFinished<wkhtmltoimage_converter>);
        CHECK(wkhtmltoimage_convert(converter.get()) == int(test.success));
        CHECK(finished == std::vector<int>{int(test.success)});
        const unsigned char* output = nullptr;
        const long length = wkhtmltoimage_get_output(converter.get(), &output);
        if (test.success) {
            CHECK(output && length >= long(std::strlen(test.signature)));
            CHECK(std::memcmp(output, test.signature, std::strlen(test.signature)) == 0);
        } else CHECK(length == 0);
    }
}
} // namespace

int main(int argc, char** argv) {
    try {
        CHECK(argc == 2);
        const std::string suite(argv[1]);
        if (suite == "settings") settingsBounds();
        else if (suite == "pdf") pdfSettingsAndConversion();
        else if (suite == "image") imageConversion();
        else throw std::runtime_error("Unknown C API test suite: " + suite);
        std::cout << "C API " << suite << " passed\n";
        return 0;
    } catch (const std::exception& error) {
        std::cerr << "C API test failed: " << error.what() << '\n';
        return 1;
    }
}
