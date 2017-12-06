/* htmltext type and the htmlescape function  */

#include "Python.h"
#include "structmember.h"

typedef struct {
	PyObject_HEAD
	PyObject *s;
} htmltextObject;

static PyTypeObject htmltext_Type;

#define htmltextObject_Check(v)	PyType_IsSubtype(Py_TYPE(v), &htmltext_Type)

#define htmltext_STR(v) ((PyObject *)(((htmltextObject *)v)->s))

typedef struct {
	PyObject_HEAD
	PyObject *obj;
} QuoteWrapperObject;

static PyTypeObject QuoteWrapper_Type;

#define QuoteWrapper_Check(v)	(Py_TYPE(v) == &QuoteWrapper_Type)

typedef struct {
	PyObject_HEAD
	PyObject *data; /* PyList_Object */
	int html;
} TemplateIO_Object;

static PyTypeObject TemplateIO_Type;

#define TemplateIO_Check(v)	(Py_TYPE(v) == &TemplateIO_Type)


static PyObject *
type_error(const char *msg)
{
	PyErr_SetString(PyExc_TypeError, msg);
	return NULL;
}

static PyObject *
stringify(PyObject *obj)
{
	PyObject *res;
	if (PyUnicode_Check(obj) || PyBytes_Check(obj)) {
		Py_INCREF(obj);
		return obj;
	}
	if (Py_TYPE(obj)->tp_str != NULL)
		res = (*Py_TYPE(obj)->tp_str)(obj);
	else
		res = PyObject_Repr(obj);
	if (res == NULL)
                return NULL;
	if (!PyUnicode_Check(res)) {
		Py_DECREF(res);
		return type_error("string object required");
	}
	return res;
}

static PyObject *
escape_unicode(PyObject *pystr)
{
	/* Take a PyUnicode pystr and return a new escaped PyUnicode */
	Py_ssize_t i;
	Py_ssize_t input_chars;
	Py_ssize_t extra_chars;
	Py_ssize_t chars;
	PyObject *rval;
	void *input;
	int kind;
	Py_UCS4 maxchar;

	if (PyUnicode_READY(pystr) == -1)
		return NULL;

	maxchar = PyUnicode_MAX_CHAR_VALUE(pystr);
	input_chars = PyUnicode_GET_LENGTH(pystr);
	input = PyUnicode_DATA(pystr);
	kind = PyUnicode_KIND(pystr);

	/* Compute the output size */
	for (i = 0, extra_chars = 0; i < input_chars; i++) {
		Py_UCS4 c = PyUnicode_READ(kind, input, i);
		switch (c) {
		case '&':
			extra_chars += 4;
			break;
		case '<':
		case '>':
			extra_chars += 3;
			break;
		case '"':
			extra_chars += 5;
			break;
		}
	}
	if (extra_chars > PY_SSIZE_T_MAX - input_chars) {
		PyErr_SetString(PyExc_OverflowError,
				"string is too long to escape");
		return NULL;
	}

	rval = PyUnicode_New(input_chars + extra_chars, maxchar);
	if (rval == NULL)
		return NULL;

	kind = PyUnicode_KIND(rval);

#define ENCODE_OUTPUT do { \
	chars = 0; \
	for (i = 0; i < input_chars; i++) { \
		Py_UCS4 c = PyUnicode_READ(kind, input, i); \
		switch (c) { \
		case '&':  \
			output[chars++] = '&'; \
			output[chars++] = 'a'; \
			output[chars++] = 'm'; \
			output[chars++] = 'p'; \
			output[chars++] = ';'; \
			break; \
		case '<':  \
			output[chars++] = '&'; \
			output[chars++] = 'l'; \
			output[chars++] = 't'; \
			output[chars++] = ';'; \
			break; \
		case '>':  \
			output[chars++] = '&'; \
			output[chars++] = 'g'; \
			output[chars++] = 't'; \
			output[chars++] = ';'; \
			break; \
		case '"':  \
			output[chars++] = '&'; \
			output[chars++] = 'q'; \
			output[chars++] = 'u'; \
			output[chars++] = 'o'; \
			output[chars++] = 't'; \
			output[chars++] = ';'; \
			break; \
		default: \
			 output[chars++] = c; \
		} \
	} \
	} while (0)

	if (kind == PyUnicode_1BYTE_KIND) {
		Py_UCS1 *output = PyUnicode_1BYTE_DATA(rval);
		ENCODE_OUTPUT;
	} else if (kind == PyUnicode_2BYTE_KIND) {
		Py_UCS2 *output = PyUnicode_2BYTE_DATA(rval);
		ENCODE_OUTPUT;
	} else {
		Py_UCS4 *output = PyUnicode_4BYTE_DATA(rval);
		assert(kind == PyUnicode_4BYTE_KIND);
		ENCODE_OUTPUT;
	}
	assert (chars == input_chars + extra_chars);
#undef ENCODE_OUTPUT

#ifdef Py_DEBUG
	assert(_PyUnicode_CheckConsistency(rval, 1));
#endif
return rval;
}

static PyObject *
escape(PyObject *obj)
{
	if (PyUnicode_Check(obj)) {
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
            o = htmltext_STR(o);
            Py_INCREF(o);
            return o;
        }
	if (PyFloat_Check(o) ||
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
htmltext_from_string(PyObject *s)
{
	/* note, this steals a reference */
	PyObject *self;
	if (s == NULL)
		return NULL;
	assert (PyUnicode_Check(s));
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
	Py_TYPE(self)->tp_free((PyObject *)self);
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
	rv = PyUnicode_FromFormat("<htmltext %s>", PyUnicode_AsUTF8(sr));
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
	PyObject *rv, *wargs;
	assert (PyUnicode_Check(self->s));
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
	rv = PyUnicode_Format(self->s, wargs);
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
	else if (PyUnicode_Check(v)) {
		assert (htmltextObject_Check(w));
		qw = htmltext_STR(w);
		qv = escape(v);
		if (qv == NULL)
			return NULL;
		Py_INCREF(qw);

	}
	else if (PyUnicode_Check(w)) {
		assert (htmltextObject_Check(v));
		qv = htmltext_STR(v);
		qw = escape(w);
		if (qw == NULL)
			return NULL;
		Py_INCREF(qv);
	}
	else {
		Py_INCREF(Py_NotImplemented);
		return Py_NotImplemented;
	}
	assert (PyUnicode_Check(qv));
	rv = PyUnicode_Concat(qv, qw);
	Py_DECREF(qv);
	Py_DECREF(qw);
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
			if (!PyUnicode_Check(value)) {
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
        assert (PyUnicode_Check(htmltext_STR(self)));
        rv = PyUnicode_Join(htmltext_STR(self), quoted_args);
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
	if (PyUnicode_Check(s)) {
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
	if (!PyArg_ParseTuple(args,"OO|n:replace", &old, &new, &maxsplit))
		return NULL;
	q_old = quote_arg(old);
	if (q_old == NULL)
		return NULL;
	q_new = quote_arg(new);
	if (q_new == NULL) {
		Py_DECREF(q_old);
		return NULL;
	}
	rv = PyObject_CallMethod(htmltext_STR(self), "replace", "OOn",
				 q_old, q_new, maxsplit);
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
	if (rv && PyUnicode_Check(rv))
	       rv = htmltext_from_string(rv);
error:
	Py_DECREF(wargs);
	Py_XDECREF(wkwargs);
	return rv;
}


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
	Py_TYPE(self)->tp_free((PyObject *)self);
}

static PyObject *
template_io_str(TemplateIO_Object *self)
{
	static PyObject *empty = NULL;
	if (empty == NULL) {
		empty = PyUnicode_FromStringAndSize(NULL, 0);
		if (empty == NULL)
			return NULL;
	}
	return PyUnicode_Join(empty, self->data);
}

static PyObject *
template_call(TemplateIO_Object *self, PyObject *args, PyObject *kw)
{
    PyObject *obj, *s;
    if (!_PyArg_NoKeywords("TemplateIO", kw))
        return NULL;
    if (!PyArg_UnpackTuple(args, "TemplateIO", 1, 1, &obj))
        return NULL;
    if (obj == Py_None) {
            Py_INCREF(obj);
            return obj;
    }
    if (htmltextObject_Check(obj)) {
        s = htmltext_STR(obj);
        Py_INCREF(s);
    }
    else {
        if (self->html) {
            PyObject *ss = stringify(obj);
            if (ss == NULL)
                return NULL;
            s = escape(ss);
            Py_DECREF(ss);
        }
        else {
            s = stringify(obj);
        }
        if (s == NULL)
            return NULL;
    }
    if (PyList_Append(self->data, s) != 0)
        return NULL;
    Py_DECREF(s);
    Py_INCREF(Py_None);
    return Py_None;
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
	{"format", (PyCFunction)htmltext_format_method,
		METH_VARARGS | METH_KEYWORDS, ""},
	{NULL, NULL}
};

static PyMemberDef htmltext_members[] = {
	{"s", T_OBJECT, offsetof(htmltextObject, s), READONLY, "the string"},
	{NULL},
};

static PySequenceMethods htmltext_as_sequence = {
	(lenfunc)htmltext_length,	/*sq_length*/
	0,	/*sq_concat*/
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
	(binaryfunc)htmltext_format, /*nb_remainder*/
};

static PyTypeObject htmltext_Type = {
	PyVarObject_HEAD_INIT(&PyType_Type, 0)
	"htmltext",		/*tp_name*/
	sizeof(htmltextObject),	/*tp_basicsize*/
	0,			/*tp_itemsize*/
	/* methods */
	(destructor)htmltext_dealloc, /*tp_dealloc*/
	0,			/*tp_print*/
	0,			/*tp_getattr*/
	0,			/*tp_setattr*/
	0,			/*tp_reserved*/
	(unaryfunc)htmltext_repr,/*tp_repr*/
	&htmltext_as_number,	/*tp_as_number*/
	&htmltext_as_sequence,	/*tp_as_sequence*/
	0,			/*tp_as_mapping*/
	htmltext_hash,		/*tp_hash*/
	0,			/*tp_call*/
	(unaryfunc)htmltext_str,/*tp_str*/
	0,			/*tp_getattro*/
	0,			/*tp_setattro*/
	0,			/*tp_as_buffer*/
	Py_TPFLAGS_DEFAULT | Py_TPFLAGS_BASETYPE, /*tp_flags*/
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
	0,			/*tp_alloc*/
	htmltext_new,		/*tp_new*/
	0,			/*tp_free*/
	0,			/*tp_is_gc*/
};

static PyMappingMethods quote_wrapper_as_mapping = {
	0, /*mp_length*/
	(binaryfunc)quote_wrapper_subscript, /*mp_subscript*/
	0, /*mp_ass_subscript*/
};


static PyTypeObject QuoteWrapper_Type = {
	PyVarObject_HEAD_INIT(&PyType_Type, 0)
	"QuoteWrapper",		/*tp_name*/
	sizeof(QuoteWrapperObject),	/*tp_basicsize*/
	0,
	(destructor)quote_wrapper_dealloc,          /* tp_dealloc */
	0,                                          /* tp_print */
	0,                                          /* tp_getattr */
	0,                                          /* tp_setattr */
	0,                                          /* tp_reserved */
	(unaryfunc)quote_wrapper_repr,              /* tp_repr */
	0,                                          /* tp_as_number */
	0,                                          /* tp_as_sequence */
	&quote_wrapper_as_mapping,                  /* tp_as_mapping */
	0,                                          /* tp_hash */
	0,                                          /* tp_call */
	(unaryfunc)quote_wrapper_str,               /* tp_str */
	0,                                          /* tp_getattro */
	0,                                          /* tp_setattro */
	0,                                          /* tp_as_buffer */
	Py_TPFLAGS_DEFAULT,                         /* tp_flags */
};

static PySequenceMethods template_io_as_seq = {
	0, /* sq_length */
	0, /* sq_concat */
	0, /* sq_repeat */
	0, /* sq_item */
	0, /* sq_slice */
	0, /* sq_ass_item */
	0, /* sq_ass_slice */
	0, /* sq_contains */
	(binaryfunc)template_io_iadd, /* sq_inplace_concat */
	0, /* sq_inplace_repeat */
};
static PyMethodDef template_io_methods[] = {
	{"getvalue", (PyCFunction)template_io_getvalue, METH_NOARGS, ""},
	{NULL, NULL}
};

static PyTypeObject TemplateIO_Type = {
	PyVarObject_HEAD_INIT(&PyType_Type, 0)
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
	0,			/*tp_as_number*/
	&template_io_as_seq,	/*tp_as_sequence*/
	0,			/*tp_as_mapping*/
	0,			/*tp_hash*/
	(ternaryfunc)template_call,/*tp_call*/
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

static struct PyModuleDef htmltext_module = {
	PyModuleDef_HEAD_INIT,
	"_c_htmltext",
	module_doc,
	-1,
	htmltext_module_methods,
        NULL,
        NULL,
        NULL,
        NULL,
};


PyMODINIT_FUNC PyInit__c_htmltext(void)
{
    PyObject *m = PyModule_Create(&htmltext_module);
    if (m == NULL)
        return NULL;
    if (PyType_Ready(&htmltext_Type) < 0)
        return NULL;
    if (PyType_Ready(&QuoteWrapper_Type) < 0)
        return NULL;
    if (PyType_Ready(&TemplateIO_Type) < 0)
        return NULL;
    Py_INCREF((PyObject *)&htmltext_Type);
    Py_INCREF((PyObject *)&QuoteWrapper_Type);
    Py_INCREF((PyObject *)&TemplateIO_Type);
    PyModule_AddObject(m, "htmltext", (PyObject *)&htmltext_Type);
    PyModule_AddObject(m, "TemplateIO", (PyObject *)&TemplateIO_Type);
    return m;
};
