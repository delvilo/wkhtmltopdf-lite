// -*- mode: c++; tab-width: 4; indent-tabs-mode: t; eval: (progn (c-set-style "stroustrup") (c-set-offset 'innamespace 0)); -*-
// vi:set ts=4 sts=4 sw=4 noet :
//
// Copyright 2010-2020 wkhtmltopdf authors
//
// This file is part of wkhtmltopdf.
//
// wkhtmltopdf is free software: you can redistribute it and/or modify
// it under the terms of the GNU Lesser General Public License as published by
// the Free Software Foundation, either version 3 of the License, or
// (at your option) any later version.
//
// wkhtmltopdf is distributed in the hope that it will be useful,
// but WITHOUT ANY WARRANTY; without even the implied warranty of
// MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
// GNU General Public License for more details.
//
// You should have received a copy of the GNU Lesser General Public License
// along with wkhtmltopdf.  If not, see <http://www.gnu.org/licenses/>.

#ifndef __WEBSETTINGS_HH__
#define __WEBSETTINGS_HH__

#include <QNetworkProxy>
#include <QString>

#include <dllbegin.inc>
namespace wkhtmltopdf {
namespace settings {

struct DLL_PUBLIC Web {
	Web();

	//! Should we print background images
	bool background;

	//! Should we load images
	bool loadImages;

	//! Should we enable Javascript
	bool enableJavascript;


	//! Minimum font size
	int minimumFontSize;

	//! Encoding used to enterpit a document with do supplied encoding
	QString defaultEncoding;

	//! Stylesheet supplied by the user
	QString userStyleSheet;

	//! What zoom factor should we apply when printing
	float zoomFactor;

};

}
}
#include <dllend.inc>
#endif //__WEBSETTINGS_HH__
