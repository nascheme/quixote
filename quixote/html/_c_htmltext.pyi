from string.templatelib import Template

from quixote.html._py_htmltext import (
    TemplateIO as TemplateIO,
)
from quixote.html._py_htmltext import (
    htmlescape as htmlescape,
)
from quixote.html._py_htmltext import (
    htmltext as htmltext,
)
from quixote.html._py_htmltext import (
    stringify as stringify,
)

# Present only on Python versions with t-string support at runtime.
def htmlformat(template: Template) -> htmltext: ...
