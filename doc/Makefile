#
# Makefile to convert Quixote docs to HTML
#

TXT_FILES = $(wildcard *.txt)
HTML_FILES = $(filter-out LICENSE_24% CHANGES_24%,$(TXT_FILES:%.txt=%.html))

RST2HTML = rst2html.py
RST2HTML_OPTS = -o us-ascii --link-stylesheet --stylesheet-path=default.css

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
