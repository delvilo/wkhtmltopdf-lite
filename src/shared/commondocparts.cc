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

#include "commandlineparserbase.hh"
#include "outputter.hh"
#include <QFile>

/*!
  Output the name and version of the program
  \param o The outputter to output to
*/
void CommandLineParserBase::outputName(Outputter * o) const {
	o->beginSection("Name");
	o->paragraph(appName()+" "+appVersion());
	o->endSection();
}

/*!
  Output copyright stuff
  \param o The outputter to output to
*/
void CommandLineParserBase::outputLicense(Outputter * o) const {
	o->beginSection("License");
	o->paragraph("Copyright (c) 2010-2020 wkhtmltopdf authors");
	o->paragraph("Uses Qt5 and QtWebKit under their open source licenses. "
		"See THIRD_PARTY_NOTICES.md and the matching source archive for component "
		"notices and instructions to rebuild or relink modified libraries.");
	QFile file(":/LICENSE");
	file.open(QIODevice::ReadOnly | QIODevice::Text);
	QTextStream stream(&file);
	o->verbatim(stream.readAll());
	o->endSection();
}

/*!
  Output documentation about the proxy settings
  \param o The outputter to output to
*/
void CommandLineParserBase::outputProxyDoc(Outputter * o) const {
	o->beginSection("Specifying A Proxy");
	o->paragraph(
		"By default proxy information will be read from the environment"
		" variables: proxy, all_proxy and http_proxy, proxy options can"
		" also by specified with the -p switch");
	o->verbatim(
		"<type> := \"http://\" | \"socks5://\"\n"
		"<serif> := <username> (\":\" <password>)? \"@\"\n"
		"<proxy> := \"None\" | <type>? <string>? <host> (\":\" <port>)?\n");
	o->paragraph("Here are some examples (In case you are unfamiliar with the BNF):");
	o->verbatim("http://user:password@myproxyserver:8080\n"
				"socks5://myproxyserver\n"
				"None\n");
	o->endSection();
}
