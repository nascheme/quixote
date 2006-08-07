/* Mostly stolen from Python/import.c.  PSF license applies. */


#include "Python.h"
#include "osdefs.h"

#ifdef HAVE_UNISTD_H
#include <unistd.h>
#endif

#if PY_VERSION_HEX < 0x02050000
typedef int Py_ssize_t;
#endif

/* Python function to find and load a module. */
static PyObject *loader_hook;


PyObject *
call_find_load(char *fullname, char *subname, PyObject *path)
{
	PyObject *args, *m;

	if (!(args = Py_BuildValue("(ssO)", fullname, subname,
				   path != NULL ? path : Py_None)))
		return NULL;

	m = PyEval_CallObject(loader_hook, args);

	Py_DECREF(args);
	return m;
}
	

/* Forward declarations for helper routines */
static PyObject *get_parent(PyObject *globals, char *buf, int *p_buflen);
static PyObject *load_next(PyObject *mod, PyObject *altmod,
			   char **p_name, char *buf, int *p_buflen);
static int mark_miss(char *name);
static int ensure_fromlist(PyObject *mod, PyObject *fromlist,
			   char *buf, int buflen, int recursive);
static PyObject * import_submodule(PyObject *mod, char *name, char *fullname);


static PyObject *
import_module(char *name, PyObject *globals, PyObject *locals,
		 PyObject *fromlist)
{
	char buf[MAXPATHLEN+1];
	int buflen = 0;
	PyObject *parent, *head, *next, *tail;

	parent = get_parent(globals, buf, &buflen);
	if (parent == NULL)
		return NULL;

	head = load_next(parent, Py_None, &name, buf, &buflen);
	if (head == NULL)
		return NULL;

	tail = head;
	Py_INCREF(tail);
	while (name) {
		next = load_next(tail, tail, &name, buf, &buflen);
		Py_DECREF(tail);
		if (next == NULL) {
			Py_DECREF(head);
			return NULL;
		}
		tail = next;
	}

	if (fromlist != NULL) {
		if (fromlist == Py_None || !PyObject_IsTrue(fromlist))
			fromlist = NULL;
	}

	if (fromlist == NULL) {
		Py_DECREF(tail);
		return head;
	}

	Py_DECREF(head);
	if (!ensure_fromlist(tail, fromlist, buf, buflen, 0)) {
		Py_DECREF(tail);
		return NULL;
	}

	return tail;
}

static PyObject *
get_parent(PyObject *globals, char *buf, int *p_buflen)
{
	static PyObject *namestr = NULL;
	static PyObject *pathstr = NULL;
	PyObject *modname, *modpath, *modules, *parent;

	if (globals == NULL || !PyDict_Check(globals))
		return Py_None;

	if (namestr == NULL) {
		namestr = PyString_InternFromString("__name__");
		if (namestr == NULL)
			return NULL;
	}
	if (pathstr == NULL) {
		pathstr = PyString_InternFromString("__path__");
		if (pathstr == NULL)
			return NULL;
	}

	*buf = '\0';
	*p_buflen = 0;
	modname = PyDict_GetItem(globals, namestr);
	if (modname == NULL || !PyString_Check(modname))
		return Py_None;

	modpath = PyDict_GetItem(globals, pathstr);
	if (modpath != NULL) {
		int len = PyString_GET_SIZE(modname);
		if (len > MAXPATHLEN) {
			PyErr_SetString(PyExc_ValueError,
					"Module name too long");
			return NULL;
		}
		strcpy(buf, PyString_AS_STRING(modname));
		*p_buflen = len;
	}
	else {
		char *start = PyString_AS_STRING(modname);
		char *lastdot = strrchr(start, '.');
		size_t len;
		if (lastdot == NULL)
			return Py_None;
		len = lastdot - start;
		if (len >= MAXPATHLEN) {
			PyErr_SetString(PyExc_ValueError,
					"Module name too long");
			return NULL;
		}
		strncpy(buf, start, len);
		buf[len] = '\0';
		*p_buflen = len;
	}

	modules = PyImport_GetModuleDict();
	parent = PyDict_GetItemString(modules, buf);
	if (parent == NULL)
		parent = Py_None;
	return parent;
	/* We expect, but can't guarantee, if parent != None, that:
	   - parent.__name__ == buf
	   - parent.__dict__ is globals
	   If this is violated...  Who cares? */
}

/* altmod is either None or same as mod */
static PyObject *
load_next(PyObject *mod, PyObject *altmod, char **p_name, char *buf,
	  int *p_buflen)
{
	char *name = *p_name;
	char *dot = strchr(name, '.');
	size_t len;
	char *p;
	PyObject *result;

	if (dot == NULL) {
		*p_name = NULL;
		len = strlen(name);
	}
	else {
		*p_name = dot+1;
		len = dot-name;
	}
	if (len == 0) {
		PyErr_SetString(PyExc_ValueError,
				"Empty module name");
		return NULL;
	}

	p = buf + *p_buflen;
	if (p != buf)
		*p++ = '.';
	if (p+len-buf >= MAXPATHLEN) {
		PyErr_SetString(PyExc_ValueError,
				"Module name too long");
		return NULL;
	}
	strncpy(p, name, len);
	p[len] = '\0';
	*p_buflen = p+len-buf;

	result = import_submodule(mod, p, buf);
	if (result == Py_None && altmod != mod) {
		Py_DECREF(result);
		/* Here, altmod must be None and mod must not be None */
		result = import_submodule(altmod, p, p);
		if (result != NULL && result != Py_None) {
			if (mark_miss(buf) != 0) {
				Py_DECREF(result);
				return NULL;
			}
			strncpy(buf, name, len);
			buf[len] = '\0';
			*p_buflen = len;
		}
	}
	if (result == NULL)
		return NULL;

	if (result == Py_None) {
		Py_DECREF(result);
		PyErr_Format(PyExc_ImportError,
			     "No module named %.200s", name);
		return NULL;
	}

	return result;
}

static int
mark_miss(char *name)
{
	PyObject *modules = PyImport_GetModuleDict();
	return PyDict_SetItemString(modules, name, Py_None);
}

static int
ensure_fromlist(PyObject *mod, PyObject *fromlist, char *buf, int buflen,
		int recursive)
{
	Py_ssize_t i;

	if (!PyObject_HasAttrString(mod, "__path__"))
		return 1;

	for (i = 0; ; i++) {
		PyObject *item = PySequence_GetItem(fromlist, i);
		int hasit;
		if (item == NULL) {
			if (PyErr_ExceptionMatches(PyExc_IndexError)) {
				PyErr_Clear();
				return 1;
			}
			return 0;
		}
		if (!PyString_Check(item)) {
			PyErr_SetString(PyExc_TypeError,
					"Item in ``from list'' not a string");
			Py_DECREF(item);
			return 0;
		}
		if (PyString_AS_STRING(item)[0] == '*') {
			PyObject *all;
			Py_DECREF(item);
			/* See if the package defines __all__ */
			if (recursive)
				continue; /* Avoid endless recursion */
			all = PyObject_GetAttrString(mod, "__all__");
			if (all == NULL)
				PyErr_Clear();
			else {
				if (!ensure_fromlist(mod, all, buf, buflen, 1))
					return 0;
				Py_DECREF(all);
			}
			continue;
		}
		hasit = PyObject_HasAttr(mod, item);
		if (!hasit) {
			char *subname = PyString_AS_STRING(item);
			PyObject *submod;
			char *p;
			if (buflen + strlen(subname) >= MAXPATHLEN) {
				PyErr_SetString(PyExc_ValueError,
						"Module name too long");
				Py_DECREF(item);
				return 0;
			}
			p = buf + buflen;
			*p++ = '.';
			strcpy(p, subname);
			submod = import_submodule(mod, subname, buf);
			Py_XDECREF(submod);
			if (submod == NULL) {
				Py_DECREF(item);
				return 0;
			}
		}
		Py_DECREF(item);
	}

	/* NOTREACHED */
}

static PyObject *
import_submodule(PyObject *mod, char *subname, char *fullname)
{
	PyObject *modules = PyImport_GetModuleDict();
	PyObject *m;

	/* Require:
	   if mod == None: subname == fullname
	   else: mod.__name__ + "." + subname == fullname
	*/

	if ((m = PyDict_GetItemString(modules, fullname)) != NULL) {
		Py_INCREF(m);
	}
	else {
		PyObject *path;

		if (mod == Py_None)
			path = NULL;
		else {
			path = PyObject_GetAttrString(mod, "__path__");
			if (path == NULL) {
				PyErr_Clear();
				Py_INCREF(Py_None);
				return Py_None;
			}
		}

		m = call_find_load(fullname, subname, path);

		if (m != NULL && m != Py_None && mod != Py_None) {
			if (PyObject_SetAttrString(mod, subname, m) < 0) {
				Py_DECREF(m);
				m = NULL;
			}
		}
	}

	return m;
}


PyObject *
reload_module(PyObject *m)
{
	PyObject *modules = PyImport_GetModuleDict();
	PyObject *path = NULL;
	char *name, *subname;

	if (m == NULL || !PyModule_Check(m)) {
		PyErr_SetString(PyExc_TypeError,
				"reload_module() argument must be module");
		return NULL;
	}
	name = PyModule_GetName(m);
	if (name == NULL)
		return NULL;
	if (m != PyDict_GetItemString(modules, name)) {
		PyErr_Format(PyExc_ImportError,
			     "reload(): module %.200s not in sys.modules",
			     name);
		return NULL;
	}
	subname = strrchr(name, '.');
	if (subname == NULL)
		subname = name;
	else {
		PyObject *parentname, *parent;
		parentname = PyString_FromStringAndSize(name, (subname-name));
		if (parentname == NULL)
			return NULL;
		parent = PyDict_GetItem(modules, parentname);
		Py_DECREF(parentname);
		if (parent == NULL) {
			PyErr_Format(PyExc_ImportError,
			    "reload(): parent %.200s not in sys.modules",
			    name);
			return NULL;
		}
		subname++;
		path = PyObject_GetAttrString(parent, "__path__");
		if (path == NULL)
			PyErr_Clear();
	}
	m = call_find_load(name, subname, path);
	Py_XDECREF(path);
	return m;
}


static PyObject *
cimport_import_module(PyObject *self, PyObject *args)
{
	char *name;
	PyObject *globals = NULL;
	PyObject *locals = NULL;
	PyObject *fromlist = NULL;

	if (!PyArg_ParseTuple(args, "s|OOO:import_module", &name, &globals,
			      &locals, &fromlist))
		return NULL;
	return import_module(name, globals, locals, fromlist);
}

static PyObject *
cimport_reload_module(PyObject *self, PyObject *args)
{
	PyObject *m;
	if (!PyArg_ParseTuple(args, "O:reload_module", &m))
		return NULL;
	return reload_module(m);
}

static char doc_reload_module[] =
"reload(module) -> module\n\
\n\
Reload the module.  The module must have been successfully imported before.";

static PyObject *
cimport_set_loader(PyObject *self, PyObject *args)
{
	PyObject *l = NULL;
	if (!PyArg_ParseTuple(args, "O:set_loader", &l))
		return NULL;
	if (!PyCallable_Check(l)) {
		PyErr_SetString(PyExc_TypeError, "callable object needed");
		return NULL;
	}
	Py_XDECREF(loader_hook);
	loader_hook = l;
	Py_INCREF(loader_hook);
	Py_INCREF(Py_None);
	return Py_None;
}
static char doc_set_loader[] = "\
Set the function that will be used to import modules.\n\
\n\
The function should should have the signature:\n\
\n\
 loader(fullname : str, subname : str, path : [str] | None) -> module | None\n\
\n\
It should return the initialized module or None if it is not found.\n\
";	


static PyObject *
cimport_get_loader(PyObject *self, PyObject *args)
{
	if (!PyArg_ParseTuple(args, ":get_loader"))
		return NULL;
	Py_INCREF(loader_hook);
	return loader_hook;
}

static char doc_get_loader[] = "\
Get the function that will be used to import modules.\n\
";

static char doc_import_module[] = "\
import_module(name, globals, locals, fromlist) -> module\n\
\n\
Import a module.  The globals are only used to determine the context;\n\
they are not modified.  The locals are currently unused.  The fromlist\n\
should be a list of names to emulate ``from name import ...'', or an\n\
empty list to emulate ``import name''.\n\
\n\
When importing a module from a package, note that import_module('A.B', ...)\n\
returns package A when fromlist is empty, but its submodule B when\n\
fromlist is not empty.\n\
";


static PyMethodDef cimport_methods[] = {
	{"import_module",	cimport_import_module,	1, doc_import_module},
	{"reload_module",	cimport_reload_module,	1, doc_reload_module},
	{"get_loader",		cimport_get_loader,	1, doc_get_loader},
	{"set_loader",		cimport_set_loader,	1, doc_set_loader},
	{NULL,			NULL}		/* sentinel */
};

void
initcimport(void)
{
	PyObject *m, *d;

	m = Py_InitModule4("cimport", cimport_methods, "",
			   NULL, PYTHON_API_VERSION);
	d = PyModule_GetDict(m);

}
