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

#include "imagecommandlineparser.hh"
#include "outputter.hh"

/*!
  \file commandlineparser.hh
  \brief Defines the ImageCommandLineParser class
*/

/*!
  Output the man page to a given file
  \param fd The file to store the man page
*/
void ImageCommandLineParser::manpage(FILE * fd) const {
	Outputter * o = Outputter::man(fd);
 	outputManName(o);
 	outputSynopsis(o);
 	outputDescripton(o);
	outputSwitches(o, true);
 	outputContact(o);
	delete o;
}

/*!
  Output usage information aka. --help
  \param fd The file to output the information to
  \param extended Should we show extended arguments
*/
void ImageCommandLineParser::usage(FILE * fd, bool extended) const {
	Outputter * o = Outputter::text(fd);
	outputName(o);
	outputSynopsis(o);
 	outputDescripton(o);
	outputSwitches(o, extended);
	if (extended) {
		outputProxyDoc(o);
	}
 	outputContact(o);
	delete o;
}

/*!
 * Parse command line arguments, and set settings accordingly.
 * \param argc the number of command line arguments
 * \param argv a NULL terminated list with the arguments
 */
void ImageCommandLineParser::parseArguments(int argc, const char * const * argv) {
	settings.in="";
    settings.out="";
	bool defaultMode=false;
	for (int i=1; i < argc; ++i) {
        if (i==argc-2 && (argv[i][0] != '-' || argv[i][1] == '\0')) { // the arg before last (in)
            settings.in = QString::fromLocal8Bit(argv[i]);
        } else if (i==argc-1 && (argv[i][0] != '-' || argv[i][1] == '\0')) { // the last arg (out)
            settings.out = QString::fromLocal8Bit(argv[i]);
		} else {
			parseArg(global, argc, argv, defaultMode, i);
		}
	}

	if (settings.in.isEmpty() || settings.out.isEmpty()) {
        fprintf(stderr, "You need to specify at least one input file, and exactly one output file\nUse - for stdin or stdout\n\n");
        usage(stderr, false);
        exit(1);
    }
}
