#
# Makefile to convert Quixote docs to HTML
#
# $Id: Makefile 20217 2003-01-16 20:51:53Z akuchlin $
#

TXT_FILES = $(wildcard *.txt)
HTML_FILES = $(filter-out ZPL%,$(TXT_FILES:%.txt=%.html))

RST2HTML = /www/python/bin/rst2html
RST2HTML_OPTS = -o us-ascii

DEST_HOST = staging.mems-exchange.org
DEST_DIR = /www/www-docroot/software/quixote/doc

SS = default.css

%.html: %.txt
	$(RST2HTML) $(RST2HTML_OPTS) $< $@

all: $(HTML_FILES)

clean:
	rm -f $(HTML_FILES)

install:
	rsync -vptgo *.html $(SS) $(DEST_HOST):$(DEST_DIR)

local-install:
	dir=`pwd` ; \
	cd $(DEST_DIR) && ln -sf $$dir/*.html $$dir/$(SS) .
