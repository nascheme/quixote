import sys, subprocess

import quixote
from quixote.server.simple_server import run
from io import StringIO
import os
import urllib.request, urllib.parse, urllib.error

_server_url = None

testdir = os.path.dirname(__file__)
print('testdir is:', testdir)
sys.path.insert(0, os.path.abspath(os.path.join(testdir, '..')))

import twill

def cd_testdir():
    global cwd
    cwd = os.getcwd()
    os.chdir(testdir)

def pop_testdir():
    global cwd
    os.chdir(cwd)

def execute_twill_script(filename, inp=None, initial_url=None):
    global testdir
    
    if inp:
        inp_fp = StringIO(inp)
        old, sys.stdin = sys.stdin, inp_fp

    scriptfile = os.path.join(testdir, filename)
    try:
        twill.execute_file(filename, initial_url=initial_url)
    finally:
        if inp:
            sys.stdin = old

def run_server(create_fn, PORT=None):
    """
    Run a Quixote simple_server on localhost:PORT with subprocess.
    All output is captured & thrown away.

    The parent process returns the URL on which the server is running.
    """
    import time, tempfile
    global _server_url

    if PORT is None:
        PORT = int(os.environ.get('QX_TEST_PORT', '8080'))

    outfd = tempfile.mkstemp('quixote_tst')[0]
	
    print('STARTING:', sys.executable, 'tests/qx_testserver.py', os.getcwd())
    process = subprocess.Popen([sys.executable, '-u', 'qx_testserver.py'],
                               stderr=subprocess.STDOUT,
                               stdout=outfd)
   
    time.sleep(1)

    result = process.poll()
    if result is not None:
        raise Exception("server is not running: return code %s" % (result,))

    _server_url = 'http://localhost:%d/' % (PORT,)
    return _server_url
	
def kill_server():
    """
    Kill the previously started Quixote server.
    """
    global _server_url
    if _server_url != None:
       try:
          fp = urllib.request.urlopen('%sexit' % (_server_url,))
       except:
          pass

    _server_url = None
