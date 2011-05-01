/* htmltext type and the htmlescape function  */

#include "Python.h"
#include "structmember.h"

#if PY_VERSION_HEX < 0x02050000
typedef int Py_ssize_t;
typedef intargfunc ssizeargfunc; 
typedef inquiry lenfunc;
#endif

typedef struct {
	PyObject_HEAD
	PyObject *s;
} htmltextObject;

static PyTypeObject htmltext_Type;

#define htmltextObject_Check(v)	PyType_IsSubtype((v)->ob_type, &htmltext_Type)

#define htmltext_STR(v) ((PyObject *)(((htmltextObject *)v)->s))

typedef struct {
	PyObject_HEAD
	PyObject *obj;
} QuoteWrapperObject;

static PyTypeObject QuoteWrapper_Type;

#define QuoteWrapper_Check(v)	((v)->ob_type == &QuoteWrapper_Type)

typedef struct {
	PyUnicodeObject escaped;
	PyObject *raw;
} UnicodeWrapperObject;

static PyTypeObject UnicodeWrapper_Type;

#define UnicodeWrapper_Check(v)	((v)->ob_type == &UnicodeWrapper_Type)

typedef struct {
	PyObject_HEAD
	PyObject *data; /* PyList_Object */
	int html;
} TemplateIO_Object;

static PyTypeObject TemplateIO_Type;

#define TemplateIO_Check(v)	((v)->ob_type == &TemplateIO_Type)


static PyObject *
type_error(const char *msg)
{
	PyErr_SetString(PyExc_TypeError, msg);
	return NULL;
}

static int
string_check(PyObject *v)
{
	return PyUnicode_Check(v) || PyString_Check(v);
}

static PyObject *
stringify(PyObject *obj)
{
	static PyObject *unicodestr = NULL;
	PyObject *res, *func;
	if (string_check(obj)) {
		Py_INCREF(obj);
		return obj;
	}
	if (unicodestr == NULL) {
		unicodestr = PyString_InternFromString("__unicode__");
		if (unicodestr == NULL)
			return NULL;
	}
	func = PyObject_GetAttr(obj, unicodestr);
	if (func != NULL) {
		res = PyEval_CallObject(func, (PyObject *)NULL);
		Py_DECREF(func);
	}
	else {
		PyErr_Clear();
		if (obj->ob_type->tp_str != NULL)
			res = (*obj->ob_type->tp_str)(obj);
		else
			res = PyObject_Repr(obj);
	}
	if (res == NULL)
                return NULL;
	if (!string_check(res)) {
		Py_DECREF(res);
		return type_error("string object required");
	}
	return res;
}

static PyObject *
escape_string(PyObject *obj)
{
	char *s;
	PyObject *newobj;
	Py_ssize_t i, j, extra_space, size, new_size;
	assert (PyString_Check(obj));
	size = PyString_GET_SIZE(obj);
	extra_space = 0;
	for (i=0; i < size; i++) {
		switch (PyString_AS_STRING(obj)[i]) {
		case '&':
			extra_space += 4;
			break;
		case '<':
		case '>':
			extra_space += 3;
			break;
		case '"':
			extra_space += 5;
			break;
		}
	}
	if (extra_space == 0) {
		Py_INCREF(obj);
		return (PyObject *)obj;
	}
	new_size = size + extra_space;
	newobj = PyString_FromStringAndSize(NULL, new_size);
	if (newobj == NULL)
		return NULL;
	s = PyString_AS_STRING(newobj);
	for (i=0, j=0; i < size; i++) {
		switch (PyString_AS_STRING(obj)[i]) {
		case '&':
			s[j++] = '&';
			s[j++] = 'a';
			s[j++] = 'm';
			s[j++] = 'p';
			s[j++] = ';';
			break;
		case '<':
			s[j++] = '&';
			s[j++] = 'l';
			s[j++] = 't';
			s[j++] = ';';
			break;
		case '>':
			s[j++] = '&';
			s[j++] = 'g';
			s[j++] = 't';
			s[j++] = ';';
			break;
		case '"':
			s[j++] = '&';
			s[j++] = 'q';
			s[j++] = 'u';
			s[j++] = 'o';
			s[j++] = 't';
			s[j++] = ';';
			break;
		default:
			s[j++] = PyString_AS_STRING(obj)[i];
			break;
		}
	}
	assert (j == new_size);
	return (PyObject *)newobj;
}

static PyObject *
escape_unicode(PyObject *obj)
{
	Py_UNICODE *u;
	PyObject *newobj;
	Py_ssize_t i, j, extra_space, size, new_size;
	assert (PyUnicode_Check(obj));
	size = PyUnicode_GET_SIZE(obj);
	extra_space = 0;
	for (i=0; i < size; i++) {
		switch (PyUnicode_AS_UNICODE(obj)[i]) {
		case '&':
			extra_space += 4;
			break;
		case '<':
		case '>':
			extra_space += 3;
			break;
		case '"':
			extra_space += 5;
			break;
		}
	}
	if (extra_space == 0) {
		Py_INCREF(obj);
		return (PyObject *)obj;
	}
	new_size = size + extra_space;
	newobj = PyUnicode_FromUnicode(NULL, new_size);
	if (newobj == NULL) {
		return NULL;
	}
	u = PyUnicode_AS_UNICODE(newobj);
	for (i=0, j=0; i < size; i++) {
		switch (PyUnicode_AS_UNICODE(obj)[i]) {
		case '&':
			u[j++] = '&';
			u[j++] = 'a';
			u[j++] = 'm';
			u[j++] = 'p';
			u[j++] = ';';
			break;
		case '<':
			u[j++] = '&';
			u[j++] = 'l';
			u[j++] = 't';
			u[j++] = ';';
			break;
		case '>':
			u[j++] = '&';
			u[j++] = 'g';
			u[j++] = 't';
			u[j++] = ';';
			break;
		case '"':
			u[j++] = '&';
			u[j++] = 'q';
			u[j++] = 'u';
			u[j++] = 'o';
			u[j++] = 't';
			u[j++] = ';';
			break;
		default:
			u[j++] = PyUnicode_AS_UNICODE(obj)[i];
			break;
		}
	}
	assert (j == new_size);
	return (PyObject *)newobj;
}

static PyObject *
escape(PyObject *obj)
{
	if (PyString_Check(obj)) {
		return escape_string(obj);
	}
	else if (PyUnicode_Check(obj)) {
		return escape_unicode(obj);
	}
	else {
		return type_error("string object required");
	}
}

static PyObject *
quote_wrapper_new(PyObject *o)
{
	QuoteWrapperObject *self;
	if (htmltextObject_Check(o)) {
            /* Necessary to work around a PyString_Format bug.  Should be
	     * fixed in Python 2.5. */
            o = htmltext_STR(o);
            Py_INCREF(o);
            return o;
        }
	if (PyUnicode_Check(o)) {
	    /* again, work around PyString_Format bug */
            return PyObject_CallFunctionObjArgs(
                        (PyObject *)&UnicodeWrapper_Type, o, NULL);
        }
	if (PyInt_Check(o) ||
	    PyFloat_Check(o) ||
	    PyLong_Check(o)) {
		/* no need for wrapper */
		Py_INCREF(o);
		return o;
	}
	self = PyObject_New(QuoteWrapperObject, &QuoteWrapper_Type);
	if (self == NULL)
		return NULL;
	Py_INCREF(o);
	self->obj = o;
	return (PyObject *)self;
}

static void
quote_wrapper_dealloc(QuoteWrapperObject *self)
{
	Py_DECREF(self->obj);
	PyObject_Del(self);
}

static PyObject *
quote_wrapper_repr(QuoteWrapperObject *self)
{
	PyObject *qs;
	PyObject *s = PyObject_Repr(self->obj);
	if (s == NULL)
		return NULL;
	qs = escape(s);
	Py_DECREF(s);
	return qs;
}

static PyObject *
quote_wrapper_str(QuoteWrapperObject *self)
{
	PyObject *qs;
	PyObject *s = stringify(self->obj);
	if (s == NULL)
		return NULL;
	qs = escape(s);
	Py_DECREF(s);
	return qs;
}

static PyObject *
quote_wrapper_subscript(QuoteWrapperObject *self, PyObject *key)
{
	PyObject *v, *w;;
	v = PyObject_GetItem(self->obj, key);
	if (v == NULL) {
		return NULL;
	}
	w = quote_wrapper_new(v); 
	Py_DECREF(v);
	return w;
}

static PyObject *
unicode_wrapper_new(PyTypeObject *type, PyObject *args, PyObject *kwds)
{
	PyObject *result;
	PyObject *raw = NULL, *escaped = NULL, *newargs = NULL;
	if (!PyArg_ParseTuple(args, "O", &raw))
		goto error;
	escaped = escape(raw);
	if (escaped == NULL)
		goto error;
	newargs = PyTuple_New(1);
	if (newargs == NULL)
		goto error;
	PyTuple_SET_ITEM(newargs, 0, escaped);
	result = PyUnicode_Type.tp_new(type, newargs, kwds);
	if (result == NULL)
		goto error;
	Py_DECREF(newargs);
	Py_INCREF(raw);
	((UnicodeWrapperObject *)result)->raw = raw;
	return result;

error:
	Py_XDECREF(raw);
	Py_XDECREF(escaped);
	Py_XDECREF(newargs);
	return NULL;
}

static void
unicode_wrapper_dealloc(UnicodeWrapperObject *self)
{
	Py_XDECREF(self->raw);
	PyUnicode_Type.tp_dealloc((PyObject *) self);
}

static PyObject *
unicode_wrapper_repr(UnicodeWrapperObject *self)
{
	PyObject *qr;
	PyObject *r = PyObject_Repr(self->raw);
	if (r == NULL)
		return NULL;
	qr = escape(r);
	Py_DECREF(r);
	return qr;
}

static PyObject *
htmltext_from_string(PyObject *s)
{
	/* note, this steals a reference */
	PyObject *self;
	if (s == NULL)
		return NULL;
	assert (string_check(s));
	self = PyType_GenericAlloc(&htmltext_Type, 0);
	if (self == NULL) {
		Py_DECREF(s);
		return NULL;
	}
	((htmltextObject *)self)->s = s;
	return self;
}

static PyObject *
htmltext_new(PyTypeObject *type, PyObject *args, PyObject *kwds)
{
	htmltextObject *self;
	PyObject *s;
	static char *kwlist[] = {"s", 0};
	if (!PyArg_ParseTupleAndKeywords(args, kwds, "O:htmltext", kwlist,
					 &s))
		return NULL;
	s = stringify(s);
	if (s == NULL)
		return NULL;
	self = (htmltextObject *)type->tp_alloc(type, 0);
	if (self == NULL) {
		Py_DECREF(s);
		return NULL;
	}
	self->s = s;
	return (PyObject *)self;
}

/* htmltext methods */

static void
htmltext_dealloc(htmltextObject *self)
{
	Py_DECREF(self->s);
	self->ob_type->tp_free((PyObject *)self);
}

static long
htmltext_hash(PyObject *self)
{
	return PyObject_Hash(htmltext_STR(self));
}

static PyObject *
htmltext_str(htmltextObject *self)
{
	Py_INCREF(self->s);
	return (PyObject *)self->s;
}

static PyObject *
htmltext_repr(htmltextObject *self)
{
	PyObject *sr, *rv;
	sr = PyObject_Repr((PyObject *)self->s);
	if (sr == NULL)
		return NULL;
	rv = PyString_FromFormat("<htmltext %s>", PyString_AsString(sr));
	Py_DECREF(sr);
	return rv;
}

static PyObject *
htmltext_richcompare(PyObject *a, PyObject *b, int op)
{
	if (htmltextObject_Check(a)) {
		a = htmltext_STR(a);
	}
	if (htmltextObject_Check(b)) {
		b = htmltext_STR(b);
	}
	return PyObject_RichCompare(a, b, op);
}

static Py_ssize_t
htmltext_length(htmltextObject *self)
{
	return PyObject_Size(htmltext_STR(self));
}


static PyObject *
htmltext_format(htmltextObject *self, PyObject *args)
{
	/* wrap the format arguments with QuoteWrapperObject */
	int is_unicode;
	PyObject *rv, *wargs;
	if (PyUnicode_Check(self->s)) {
		is_unicode = 1;
	}
	else {
		is_unicode = 0;
		assert (PyString_Check(self->s));
	}
	if (PyTuple_Check(args)) {
		Py_ssize_t i, n = PyTuple_GET_SIZE(args);
		wargs = PyTuple_New(n);
		for (i=0; i < n; i++) {
			PyObject *v = PyTuple_GET_ITEM(args, i);
			v = quote_wrapper_new(v);
			if (v == NULL) {
				Py_DECREF(wargs);
				return NULL;
			}
			PyTuple_SetItem(wargs, i, v);
		}
	}
	else {
		wargs = quote_wrapper_new(args);
		if (wargs == NULL)
			return NULL;
	}
	if (is_unicode)
		rv = PyUnicode_Format(self->s, wargs);
	else
		rv = PyString_Format(self->s, wargs);
	Py_DECREF(wargs);
	return htmltext_from_string(rv);
}

static PyObject *
htmltext_add(PyObject *v, PyObject *w)
{
	PyObject *qv, *qw, *rv;
	if (htmltextObject_Check(v) && htmltextObject_Check(w)) {
		qv = htmltext_STR(v);
		qw = htmltext_STR(w);
		Py_INCREF(qv);
		Py_INCREF(qw);
	}
	else if (string_check(w)) {
		assert (htmltextObject_Check(v));
		qv = htmltext_STR(v);
		qw = escape(w);
		if (qw == NULL)
			return NULL;
		Py_INCREF(qv);
	}
	else if (string_check(v)) {
		assert (htmltextObject_Check(w));
		qv = escape(v);
		if (qv == NULL)
			return NULL;
		qw = htmltext_STR(w);
		Py_INCREF(qw);
	}
	else {
		Py_INCREF(Py_NotImplemented);
		return Py_NotImplemented;
	}
        if (PyString_Check(qv)) {
            PyString_ConcatAndDel(&qv, qw);
            rv = qv;
        }
        else {
            assert (PyUnicode_Check(qv));
            rv = PyUnicode_Concat(qv, qw);
            Py_DECREF(qv);
            Py_DECREF(qw);
        }
	return htmltext_from_string(rv);
}

static PyObject *
htmltext_repeat(htmltextObject *self, Py_ssize_t n)
{
	PyObject *s = PySequence_Repeat(htmltext_STR(self), n);
	if (s == NULL)
		return NULL;
	return htmltext_from_string(s);
}

static PyObject *
htmltext_join(PyObject *self, PyObject *args)
{
	Py_ssize_t i;
	PyObject *quoted_args, *rv;

	quoted_args = PySequence_List(args);
	if (quoted_args == NULL)
		return NULL;
	for (i=0; i < PyList_Size(quoted_args); i++) {
		PyObject *value, *qvalue;
		value = PyList_GET_ITEM(quoted_args, i);
		if (value == NULL) {
			goto error;
		}
		if (htmltextObject_Check(value)) {
			qvalue = htmltext_STR(value);
			Py_INCREF(qvalue);
		}
		else {
			if (!string_check(value)) {
				type_error("join requires a list of strings");
				goto error;
			}
			qvalue = escape(value);
			if (qvalue == NULL)
				goto error;
		}
		if (PyList_SetItem(quoted_args, i, qvalue) < 0) {
			goto error;
		}
	}
	if (PyUnicode_Check(htmltext_STR(self))) {
		rv = PyUnicode_Join(htmltext_STR(self), quoted_args);
	}
	else {
		rv = _PyString_Join(htmltext_STR(self), quoted_args);
	}
	Py_DECREF(quoted_args);
	return htmltext_from_string(rv);

error:
	Py_DECREF(quoted_args);
	return NULL;
}

static PyObject *
quote_arg(PyObject *s)
{
	PyObject *ss;
	if (string_check(s)) {
		ss = escape(s);
		if (ss == NULL)
			return NULL;
	}
	else if (htmltextObject_Check(s)) {
		ss = htmltext_STR(s);
		Py_INCREF(ss);
	}
	else {
		return type_error("string object required");
	}
	return ss;
}

static PyObject *
htmltext_call_method1(PyObject *self, PyObject *s, char *method)
{
	PyObject *ss, *rv;
	ss = quote_arg(s);
	if (ss == NULL)
		return NULL;
	rv = PyObject_CallMethod(htmltext_STR(self), method, "O", ss);
	Py_DECREF(ss);
	return rv;
}

#if PY_VERSION_HEX >= 0x02060000
static PyObject *
call_method_kwargs(PyObject *self, char *method, PyObject *args,
		   PyObject *kwargs)
{
	PyObject *m, *rv;
	m = PyObject_GetAttrString(self, method);
	if (m == NULL)
		return NULL;
	rv = PyObject_Call(m, args, kwargs);
	Py_DECREF(m);
	return rv;
}
#endif

static PyObject *
htmltext_startswith(PyObject *self, PyObject *s)
{
	return htmltext_call_method1(self, s, "startswith");
}

static PyObject *
htmltext_endswith(PyObject *self, PyObject *s)
{
	return htmltext_call_method1(self, s, "endswith");
}

static PyObject *
htmltext_replace(PyObject *self, PyObject *args)
{
	PyObject *old, *new, *q_old, *q_new, *rv;
	Py_ssize_t maxsplit = -1;
#if PY_VERSION_HEX >= 0x02050000
	if (!PyArg_ParseTuple(args,"OO|n:replace", &old, &new, &maxsplit))
		return NULL;
#else	
	if (!PyArg_ParseTuple(args,"OO|i:replace", &old, &new, &maxsplit))
		return NULL;
#endif
	q_old = quote_arg(old);
	if (q_old == NULL)
		return NULL;
	q_new = quote_arg(new);
	if (q_new == NULL) {
		Py_DECREF(q_old);
		return NULL;
	}
#if PY_VERSION_HEX >= 0x02050000
	rv = PyObject_CallMethod(htmltext_STR(self), "replace", "OOn",
				 q_old, q_new, maxsplit);
#else
	rv = PyObject_CallMethod(htmltext_STR(self), "replace", "OOi",
				 q_old, q_new, maxsplit);
#endif

	Py_DECREF(q_old);
	Py_DECREF(q_new);
	return htmltext_from_string(rv);
}


static PyObject *
htmltext_lower(PyObject *self)
{
	return htmltext_from_string(PyObject_CallMethod(htmltext_STR(self),
							"lower", ""));
}

static PyObject *
htmltext_upper(PyObject *self)
{
	return htmltext_from_string(PyObject_CallMethod(htmltext_STR(self),
							"upper", ""));
}

static PyObject *
htmltext_capitalize(PyObject *self)
{
	return htmltext_from_string(PyObject_CallMethod(htmltext_STR(self),
							"capitalize", ""));
}

#if PY_VERSION_HEX >= 0x02060000
static PyObject *
htmltext_format_method(PyObject *self, PyObject *args, PyObject *kwargs)
{
	PyObject *rv, *wargs, *wkwargs, *k, *v;
	Py_ssize_t i, n;
	rv = NULL;
	wargs = NULL;
	wkwargs = NULL;
	if (args != NULL) {
		n = PyTuple_GET_SIZE(args);
		wargs = PyTuple_New(n);
		for (i=0; i < n; i++) {
			PyObject *v = PyTuple_GET_ITEM(args, i);
			v = quote_wrapper_new(v);
			if (v == NULL) {
				goto error;
			}
			PyTuple_SetItem(wargs, i, v);
		}
	}
	if (kwargs != NULL) {
		i = 0;
		wkwargs = PyDict_New();
		if (wkwargs == NULL) {
			goto error;
		}
		while (PyDict_Next(kwargs, &i, &k, &v)) {
			PyObject *wv = quote_wrapper_new(v);
			if (wv == NULL) {
				goto error;
			}
			if (PyDict_SetItem(wkwargs, k, wv) < 0) {
				Py_DECREF(wv);
				goto error;
			}
		}
	}
	rv = call_method_kwargs(htmltext_STR(self), "format", wargs, wkwargs);
	if (rv && string_check(rv))
	       rv = htmltext_from_string(rv);
error:
	Py_DECREF(wargs);
	Py_XDECREF(wkwargs);
	return rv;
}
#endif


static PyObject *
template_io_new(PyTypeObject *type, PyObject *args, PyObject *kwds)
{
	TemplateIO_Object *self;
	int html = 0;
	static char *kwlist[] = {"html", 0};
	if (!PyArg_ParseTupleAndKeywords(args, kwds, "|i:TemplateIO",
					 kwlist, &html))
		return NULL;
	self = (TemplateIO_Object *)type->tp_alloc(type, 0);
	if (self == NULL) {
		return NULL;
	}
	self->data = PyList_New(0);
	if (self->data == NULL) {
		Py_DECREF(self);
		return NULL;
	}
	self->html = html != 0;
	return (PyObject *)self;
}

static void
template_io_dealloc(TemplateIO_Object *self)
{
	Py_DECREF(self->data);
	self->ob_type->tp_free((PyObject *)self);
}

static PyObject *
template_io_str(TemplateIO_Object *self)
{
	static PyObject *empty = NULL;
	if (empty == NULL) {
		empty = PyString_FromStringAndSize(NULL, 0);
		if (empty == NULL)
			return NULL;
	}
	return _PyString_Join(empty, self->data);
}

static PyObject *
template_io_getvalue(TemplateIO_Object *self)
{
	if (self->html) {
		return htmltext_from_string(template_io_str(self));
	}
	else {
		return template_io_str(self);
	}
}

static PyObject *
template_io_iadd(TemplateIO_Object *self, PyObject *other)
{
	PyObject *s = NULL;
	if (!TemplateIO_Check(self))
		return type_error("TemplateIO object required");
	if (other == Py_None) {
		Py_INCREF(self);
		return (PyObject *)self;
	}
	else if (htmltextObject_Check(other)) {
		s = htmltext_STR(other);
		Py_INCREF(s);
	}
	else {
		if (self->html) {
			PyObject *ss = stringify(other);
			if (ss == NULL)
				return NULL;
			s = escape(ss);
			Py_DECREF(ss);
		}
		else {
			s = stringify(other);
		}
		if (s == NULL)
			return NULL;
	}
	if (PyList_Append(self->data, s) != 0)
		return NULL;
	Py_DECREF(s);
	Py_INCREF(self);
	return (PyObject *)self;
}

static PyMethodDef htmltext_methods[] = {
	{"join", (PyCFunction)htmltext_join, METH_O, ""},
	{"startswith", (PyCFunction)htmltext_startswith, METH_O, ""},
	{"endswith", (PyCFunction)htmltext_endswith, METH_O, ""},
	{"replace", (PyCFunction)htmltext_replace, METH_VARARGS, ""},
	{"lower", (PyCFunction)htmltext_lower, METH_NOARGS, ""},
	{"upper", (PyCFunction)htmltext_upper, METH_NOARGS, ""},
	{"capitalize", (PyCFunction)htmltext_capitalize, METH_NOARGS, ""},
#if PY_VERSION_HEX >= 0x02060000
	{"format", (PyCFunction)htmltext_format_method,
		METH_VARARGS | METH_KEYWORDS, ""},
#endif
	{NULL, NULL}
};

static PyMemberDef htmltext_members[] = {
	{"s", T_OBJECT, offsetof(htmltextObject, s), READONLY, "the string"},
	{NULL},
};

static PySequenceMethods htmltext_as_sequence = {
	(lenfunc)htmltext_length,	/*sq_length*/
	0,				/*sq_concat*/
	(ssizeargfunc)htmltext_repeat,	/*sq_repeat*/
	0,				/*sq_item*/
	0,				/*sq_slice*/
	0,				/*sq_ass_item*/
	0,				/*sq_ass_slice*/
	0,				/*sq_contains*/
};

static PyNumberMethods htmltext_as_number = {
	(binaryfunc)htmltext_add, /*nb_add*/
	0, /*nb_subtract*/
	0, /*nb_multiply*/
	0, /*nb_divide*/
	(binaryfunc)htmltext_format, /*nb_remainder*/
	0, /*nb_divmod*/
	0, /*nb_power*/
	0, /*nb_negative*/
	0, /*nb_positive*/
	0, /*nb_absolute*/
	0, /*nb_nonzero*/
	0, /*nb_invert*/
	0, /*nb_lshift*/
	0, /*nb_rshift*/
	0, /*nb_and*/
	0, /*nb_xor*/
	0, /*nb_or*/
	0, /*nb_coerce*/
	0, /*nb_int*/
	0, /*nb_long*/
	0, /*nb_float*/
};

static PyTypeObject htmltext_Type = {
	PyObject_HEAD_INIT(NULL)
	0,			/*ob_size*/
	"htmltext",		/*tp_name*/
	sizeof(htmltextObject),	/*tp_basicsize*/
	0,			/*tp_itemsize*/
	/* methods */
	(destructor)htmltext_dealloc, /*tp_dealloc*/
	0,			/*tp_print*/
	0,			/*tp_getattr*/
	0,			/*tp_setattr*/
	0,			/*tp_compare*/
	(unaryfunc)htmltext_repr,/*tp_repr*/
	&htmltext_as_number,	/*tp_as_number*/
	&htmltext_as_sequence,	/*tp_as_sequence*/
	0,			/*tp_as_mapping*/
	htmltext_hash,		/*tp_hash*/
	0,			/*tp_call*/
	(unaryfunc)htmltext_str,/*tp_str*/
	0,			/*tp_getattro  set to PyObject_GenericGetAttr by module init*/
	0,			/*tp_setattro*/
	0,			/*tp_as_buffer*/
	Py_TPFLAGS_DEFAULT | Py_TPFLAGS_BASETYPE \
		| Py_TPFLAGS_CHECKTYPES, /*tp_flags*/
	0,			/*tp_doc*/
	0,			/*tp_traverse*/
	0,			/*tp_clear*/
	htmltext_richcompare,	/*tp_richcompare*/
	0,			/*tp_weaklistoffset*/
	0,			/*tp_iter*/
	0,			/*tp_iternext*/
	htmltext_methods,	/*tp_methods*/
	htmltext_members,	/*tp_members*/
	0,			/*tp_getset*/
	0,			/*tp_base*/
	0,			/*tp_dict*/
	0,			/*tp_descr_get*/
	0,			/*tp_descr_set*/
	0,			/*tp_dictoffset*/
	0,			/*tp_init*/
	0,			/*tp_alloc  set to PyType_GenericAlloc by module init*/
	htmltext_new,		/*tp_new*/
	0,			/*tp_free  set to _PyObject_Del by module init*/
	0,			/*tp_is_gc*/
};

static PyNumberMethods quote_wrapper_as_number = {
	0, /*nb_add*/
	0, /*nb_subtract*/
	0, /*nb_multiply*/
	0, /*nb_divide*/
	0, /*nb_remainder*/
	0, /*nb_divmod*/
	0, /*nb_power*/
	0, /*nb_negative*/
	0, /*nb_positive*/
	0, /*nb_absolute*/
	0, /*nb_nonzero*/
	0, /*nb_invert*/
	0, /*nb_lshift*/
	0, /*nb_rshift*/
	0, /*nb_and*/
	0, /*nb_xor*/
	0, /*nb_or*/
	0, /*nb_coerce*/
	0, /*nb_int*/
	0, /*nb_long*/
	0, /*nb_float*/
};

static PyMappingMethods quote_wrapper_as_mapping = {
	0, /*mp_length*/
	(binaryfunc)quote_wrapper_subscript, /*mp_subscript*/
	0, /*mp_ass_subscript*/
};


static PyTypeObject QuoteWrapper_Type = {
	PyObject_HEAD_INIT(NULL)
	0,			/*ob_size*/
	"QuoteWrapper",		/*tp_name*/
	sizeof(QuoteWrapperObject),	/*tp_basicsize*/
	0,			/*tp_itemsize*/
	/* methods */
	(destructor)quote_wrapper_dealloc, /*tp_dealloc*/
	0,			/*tp_print*/
	0,			/*tp_getattr*/
	0,			/*tp_setattr*/
	0,			/*tp_compare*/
	(unaryfunc)quote_wrapper_repr,/*tp_repr*/
	&quote_wrapper_as_number,/*tp_as_number*/
	0,			/*tp_as_sequence*/
	&quote_wrapper_as_mapping,/*tp_as_mapping*/
	0,			/*tp_hash*/
	0,			/*tp_call*/
	(unaryfunc)quote_wrapper_str,  /*tp_str*/
};

static PyTypeObject UnicodeWrapper_Type = {
	PyObject_HEAD_INIT(NULL)
	0,					/*ob_size*/
	"UnicodeWrapper",			/*tp_name*/
	sizeof(UnicodeWrapperObject),		/*tp_basicsize*/
	0,					/*tp_itemsize*/
	/* methods */
	(destructor)unicode_wrapper_dealloc,	/*tp_dealloc*/
	0,					/*tp_print*/
	0,					/*tp_getattr*/
	0,					/*tp_setattr*/
	0,					/*tp_compare*/
	(unaryfunc)unicode_wrapper_repr,	/*tp_repr*/
	0,					/*tp_as_number*/
	0,					/*tp_as_sequence*/
	0,					/*tp_as_mapping*/
	0,					/*tp_hash*/
	0,					/*tp_call*/
	0,					/*tp_str*/
	0,					/*tp_getattro */
	0,					/*tp_setattro */
	0,					/*tp_as_buffer */
	Py_TPFLAGS_DEFAULT|Py_TPFLAGS_BASETYPE,	/*tp_flags */
	0,					/*tp_doc */
	0,					/*tp_traverse */
	0,					/*tp_clear */
	0,					/*tp_richcompare */
	0,					/*tp_weaklistoffset */
	0,					/*tp_iter */
	0,					/*tp_iternext */
	0,					/*tp_methods */
	0,					/*tp_members */
	0,					/*tp_getset */
	0,					/*tp_base */
	0,					/*tp_dict */
	0,					/*tp_descr_get */
	0,					/*tp_descr_set */
	0,					/*tp_dictoffset */
	0,					/*tp_init */
	0,					/*tp_alloc */
	(newfunc)unicode_wrapper_new,		/*tp_new */
};

static PyNumberMethods template_io_as_number = {
	0, /*nb_add*/
	0, /*nb_subtract*/
	0, /*nb_multiply*/
	0, /*nb_divide*/
	0, /*nb_remainder*/
	0, /*nb_divmod*/
	0, /*nb_power*/
	0, /*nb_negative*/
	0, /*nb_positive*/
	0, /*nb_absolute*/
	0, /*nb_nonzero*/
	0, /*nb_invert*/
	0, /*nb_lshift*/
	0, /*nb_rshift*/
	0, /*nb_and*/
	0, /*nb_xor*/
	0, /*nb_or*/
	0, /*nb_coerce*/
	0, /*nb_int*/
	0, /*nb_long*/
	0, /*nb_float*/
	0, /*nb_oct*/
	0, /*nb_hex*/
	(binaryfunc)template_io_iadd, /*nb_inplace_add*/
};

static PyMethodDef template_io_methods[] = {
	{"getvalue", (PyCFunction)template_io_getvalue, METH_NOARGS, ""},
	{NULL, NULL}
};

static PyTypeObject TemplateIO_Type = {
	PyObject_HEAD_INIT(NULL)
	0,			/*ob_size*/
	"TemplateIO",		/*tp_name*/
	sizeof(TemplateIO_Object),/*tp_basicsize*/
	0,			/*tp_itemsize*/
	/* methods */
	(destructor)template_io_dealloc, /*tp_dealloc*/
	0,			/*tp_print*/
	0,			/*tp_getattr*/
	0,			/*tp_setattr*/
	0,			/*tp_compare*/
	0,			/*tp_repr*/
	&template_io_as_number,	/*tp_as_number*/
	0,			/*tp_as_sequence*/
	0,			/*tp_as_mapping*/
	0,			/*tp_hash*/
	0,			/*tp_call*/
	(unaryfunc)template_io_str,/*tp_str*/
	0,			/*tp_getattro  set to PyObject_GenericGetAttr by module init*/
	0,			/*tp_setattro*/
	0,			/*tp_as_buffer*/
	Py_TPFLAGS_DEFAULT | Py_TPFLAGS_BASETYPE, /*tp_flags*/
	0,			/*tp_doc*/
	0,			/*tp_traverse*/
	0,			/*tp_clear*/
	0,			/*tp_richcompare*/
	0,			/*tp_weaklistoffset*/
	0,			/*tp_iter*/
	0,			/*tp_iternext*/
	template_io_methods,	/*tp_methods*/
	0,			/*tp_members*/
	0,			/*tp_getset*/
	0,			/*tp_base*/
	0,			/*tp_dict*/
	0,			/*tp_descr_get*/
	0,			/*tp_descr_set*/
	0,			/*tp_dictoffset*/
	0,			/*tp_init*/
	0,			/*tp_alloc  set to PyType_GenericAlloc by module init*/
	template_io_new,	/*tp_new*/
	0,			/*tp_free  set to _PyObject_Del by module init*/
	0,			/*tp_is_gc*/
};

/* --------------------------------------------------------------------- */

static PyObject *
html_escape(PyObject *self, PyObject *o)
{
	if (htmltextObject_Check(o)) {
		Py_INCREF(o);
		return o;
	}
	else {
		PyObject *rv;
		PyObject *s = stringify(o);
		if (s == NULL)
			return NULL;
		rv = escape(s);
		Py_DECREF(s);
		return htmltext_from_string(rv);
	}
}

static PyObject *
py_escape_string(PyObject *self, PyObject *o)
{
	return escape(o);
}

static PyObject *
py_stringify(PyObject *self, PyObject *o)
{
	return stringify(o);
}

/* List of functions defined in the module */

static PyMethodDef htmltext_module_methods[] = {
	{"htmlescape",		(PyCFunction)html_escape, METH_O},
	{"_escape_string",	(PyCFunction)py_escape_string, METH_O},
	{"stringify",	        (PyCFunction)py_stringify, METH_O},
	{NULL,			NULL}
};

static char module_doc[] = "htmltext string type";

void
init_c_htmltext(void)
{
	PyObject *m;

	/* Create the module and add the functions */
	m = Py_InitModule4("_c_htmltext", htmltext_module_methods, module_doc,
			   NULL, PYTHON_API_VERSION);

	if (PyType_Ready(&htmltext_Type) < 0)
		return;
	if (PyType_Ready(&QuoteWrapper_Type) < 0)
		return;
	UnicodeWrapper_Type.tp_base = &PyUnicode_Type;
	if (PyType_Ready(&UnicodeWrapper_Type) < 0)
		return;
	if (PyType_Ready(&TemplateIO_Type) < 0)
		return;
	Py_INCREF((PyObject *)&htmltext_Type);
	Py_INCREF((PyObject *)&QuoteWrapper_Type);
	Py_INCREF((PyObject *)&UnicodeWrapper_Type);
	Py_INCREF((PyObject *)&TemplateIO_Type);
	PyModule_AddObject(m, "htmltext", (PyObject *)&htmltext_Type);
	PyModule_AddObject(m, "TemplateIO", (PyObject *)&TemplateIO_Type);
}
