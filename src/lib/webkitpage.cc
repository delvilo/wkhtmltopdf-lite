// Copyright 2026 wkhtmltopdf contributors. LGPL-3.0-or-later.
#include "webkitpage.hh"
#include "resourceloader.hh"
#include <QPaintEngine>
#include <QPainter>
#include <QPainterPath>
#include <QPrinter>
#include <QWebElement>
#include <QWebFrame>
#include <QWebPage>
#include <QWebSettings>

#include "dllbegin.inc"
namespace wkhtmltopdf {

class DLL_LOCAL WebKitElement: public DomElement::Data {
public:
	explicit WebKitElement(const QWebElement & value): element(value) {}
	bool isNull() const { return element.isNull(); }
	QString attribute(const QString & name) const { return element.attribute(name); }
	QString tagName() const { return element.tagName(); }
	QString toPlainText() const { return element.toPlainText(); }
	void setStyleProperty(const QString & name, const QString & value) {
		element.setStyleProperty(name, value);
	}
	QWebElement element;
};

class WebKitPage::Private: public DomDocument, public ImageRenderer {
public:
	explicit Private(QWebPage & p): page(p) {}
	QWebPage & page;
	QString title() const { return page.mainFrame()->title(); }
	QUrl url() const { return page.mainFrame()->url(); }
	QUrl baseUrl() const { return page.mainFrame()->baseUrl(); }
	DomElement findFirstElement(const QString & selector) const {
		return DomElement(new WebKitElement(page.mainFrame()->findFirstElement(selector)));
	}
	QList<DomElement> findAllElements(const QString & selector) const {
		QList<DomElement> elements;
		foreach (const QWebElement & element, page.mainFrame()->findAllElements(selector))
			elements.append(DomElement(new WebKitElement(element)));
		return elements;
	}
	void setViewportSize(const QSize & size) { page.setViewportSize(size); }
	QSize viewportSize() const { return page.viewportSize(); }
	QSize contentsSize() const { return page.mainFrame()->contentsSize(); }
	void setScrollBarPolicy(Qt::Orientation orientation, Qt::ScrollBarPolicy policy) {
		page.mainFrame()->setScrollBarPolicy(orientation, policy);
	}
	int scrollBarMaximum(Qt::Orientation orientation) const {
		return page.mainFrame()->scrollBarMaximum(orientation);
	}
	void setTransparentBackground() {
		QPalette palette = page.palette();
		palette.setBrush(QPalette::Base, Qt::transparent);
		page.setPalette(palette);
	}
	void render(QPainter * painter) { page.mainFrame()->render(painter); }
};

// WebKit emits URL annotations only when the paint engine reports Pdf. Forward
// ordinary painting through a custom engine so the DOM, CSS and print layout
// stay intact while no PDF links are emitted. Only public Qt5 APIs are used.
class DLL_LOCAL DocumentPaintEngine: public QPaintEngine {
public:
	explicit DocumentPaintEngine(QPrinter & target): QPaintEngine(AllFeatures), target(target) {}
	Type type() const { return User; }
	bool begin(QPaintDevice *) { return output.begin(&target); }
	bool end() { return output.end(); }
	void updateState(const QPaintEngineState & state) {
		const DirtyFlags dirty = state.state();
		if (dirty & DirtyTransform) output.setWorldTransform(state.transform());
		if (dirty & DirtyPen) output.setPen(state.pen());
		if (dirty & DirtyBrush) output.setBrush(state.brush());
		if (dirty & DirtyBrushOrigin) output.setBrushOrigin(state.brushOrigin());
		if (dirty & DirtyFont) output.setFont(state.font());
		if (dirty & DirtyBackground) output.setBackground(state.backgroundBrush());
		if (dirty & DirtyBackgroundMode) output.setBackgroundMode(state.backgroundMode());
		if (dirty & DirtyHints) {
			output.setRenderHints(output.renderHints(), false);
			output.setRenderHints(state.renderHints());
		}
		if (dirty & DirtyCompositionMode) output.setCompositionMode(state.compositionMode());
		if (dirty & DirtyOpacity) output.setOpacity(state.opacity());
		if (dirty & DirtyClipEnabled) output.setClipping(state.isClipEnabled());
		if (dirty & DirtyClipRegion) output.setClipRegion(state.clipRegion(), state.clipOperation());
		if (dirty & DirtyClipPath) output.setClipPath(state.clipPath(), state.clipOperation());
	}
	void drawRects(const QRectF * rects, int count) { output.drawRects(rects, count); }
	void drawRects(const QRect * rects, int count) { output.drawRects(rects, count); }
	void drawLines(const QLineF * lines, int count) { output.drawLines(lines, count); }
	void drawLines(const QLine * lines, int count) { output.drawLines(lines, count); }
	void drawEllipse(const QRectF & rect) { output.drawEllipse(rect); }
	void drawEllipse(const QRect & rect) { output.drawEllipse(rect); }
	void drawPath(const QPainterPath & path) { output.drawPath(path); }
	void drawPoints(const QPointF * points, int count) { output.drawPoints(points, count); }
	void drawPoints(const QPoint * points, int count) { output.drawPoints(points, count); }
	void drawPolygon(const QPointF * points, int count, PolygonDrawMode mode) { polygon(points, count, mode); }
	void drawPolygon(const QPoint * points, int count, PolygonDrawMode mode) { polygon(points, count, mode); }
	void drawPixmap(const QRectF & rect, const QPixmap & pixmap, const QRectF & source) { output.drawPixmap(rect, pixmap, source); }
	void drawImage(const QRectF & rect, const QImage & image, const QRectF & source, Qt::ImageConversionFlags flags) {
		output.drawImage(rect, image, source, flags);
	}
	void drawTextItem(const QPointF & point, const QTextItem & text) { output.drawTextItem(point, text); }
	void drawTiledPixmap(const QRectF & rect, const QPixmap & pixmap, const QPointF & source) { output.drawTiledPixmap(rect, pixmap, source); }
private:
	template<typename Point> void polygon(const Point * points, int count, PolygonDrawMode mode) {
		if (mode == PolylineMode) output.drawPolyline(points, count);
		else if (mode == ConvexMode) output.drawConvexPolygon(points, count);
		else output.drawPolygon(points, count, mode == WindingMode ? Qt::WindingFill : Qt::OddEvenFill);
	}
	QPrinter & target;
	QPainter output;
};

class DLL_LOCAL DocumentPrinter: public QPrinter {
public:
	DocumentPrinter(QPrinter & target, QPaintEngine & painting): QPrinter(HighResolution) {
		// QPrinter borrows both engines. Paper settings and newPage() are supplied
		// by the real printer; painting is forwarded by DocumentPaintEngine.
		setEngines(target.printEngine(), &painting);
	}
};

class DLL_LOCAL WebKitPagePrinter: public PagePrinter {
public:
	WebKitPagePrinter(QWebPage & page, QPrinter * printer): page(page), printer(printer) {}
	void printDocument() {
		DocumentPaintEngine painting(*printer);
		DocumentPrinter document(*printer, painting);
		page.mainFrame()->print(&document);
	}
private:
	QWebPage & page;
	QPrinter * printer;
};

WebKitPage::WebKitPage(QWebPage & page): d(new Private(page)) {}
WebKitPage::~WebKitPage() { delete d; }
DomDocument & WebKitPage::dom() { return *d; }
ImageRenderer & WebKitPage::image() { return *d; }
PagePrinter * WebKitPage::createPrinter(QPrinter * printer) {
	return new WebKitPagePrinter(d->page, printer);
}

void WebKitPage::applySettings(const settings::Web & s) {
	QWebSettings * ws = d->page.settings();
	if (!s.defaultEncoding.isEmpty())
		ws->setDefaultTextEncoding(s.defaultEncoding);
	ws->setAttribute(QWebSettings::JavaEnabled, false);
	ws->setAttribute(QWebSettings::JavascriptEnabled, s.enableJavascript);
	ws->setAttribute(QWebSettings::JavascriptCanOpenWindows, false);
	ws->setAttribute(QWebSettings::JavascriptCanAccessClipboard, false);
	ws->setFontSize(QWebSettings::MinimumFontSize, s.minimumFontSize);
	ws->setAttribute(QWebSettings::PrintElementBackgrounds, s.background);
	ws->setAttribute(QWebSettings::AutoLoadImages, s.loadImages);
	ws->setAttribute(QWebSettings::PluginsEnabled, false);
	if (!s.userStyleSheet.isEmpty())
		ws->setUserStyleSheetUrl(ResourceLoader::guessUrlFromString(s.userStyleSheet));
	d->page.mainFrame()->setZoomFactor(s.zoomFactor);
}

}
