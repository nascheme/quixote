
BASIC_FORM_CSS = """\
form.quixote div.title {
    font-weight: bold;
}

form.quixote br.submit,
form.quixote br.widget,
br.quixoteform {
    clear: left;
}

form.quixote div.submit br.widget {
    display: none;
}

form.quixote div.widget {
    float: left;
    padding: 4px;
    padding-right: 1em;
    margin-bottom: 6px;
}

/* pretty forms (attribute selector hides from broken browsers (e.g. IE) */
form.quixote[action] {
    float: left;
}

form.quixote[action] > div.widget {
    float: none;
}

form.quixote[action] > br.widget {
    display: none;
}

form.quixote div.widget div.widget {
    padding: 0;
    margin-bottom: 0;
}

form.quixote div.SubmitWidget {
    float: left
}

form.quixote div.content {
    margin-left: 0.6em; /* indent content */
}

form.quixote div.content div.content {
    margin-left: 0; /* indent content only for top-level widgets */
}

form.quixote div.error {
    color: #c00;
    font-size: small;
    margin-top: .1em;
}

form.quixote div.hint {
    font-size: small;
    font-style: italic;
    margin-top: .1em;
}

form.quixote div.errornotice {
    color: #c00;
    padding: 0.5em;
    margin: 0.5em;
}

form.quixote div.FormTokenWidget,
form.quixote.div.HiddenWidget {
    display: none;
}
"""
