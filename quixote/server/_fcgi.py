# Derived from Robin Dunn's FastCGI module,
# available at http://alldunn.com/python/#fcgi.

#------------------------------------------------------------------------
#               Copyright (c) 1998 by Total Control Software
#                         All Rights Reserved
#------------------------------------------------------------------------
#
# Module Name:  fcgi.py
#
# Description:  Handles communication with the FastCGI module of the
#               web server without using the FastCGI developers kit, but
#               will also work in a non-FastCGI environment, (straight CGI.)
#               This module was originally fetched from someplace on the
#               Net (I don't remember where and I can't find it now...) and
#               has been significantly modified to fix several bugs, be more
#               readable, more robust at handling large CGI data and return
#               document sizes, and also to fit the model that we had previously
#               used for FastCGI.
#
#     WARNING:  If you don't know what you are doing, don't tinker with this
#               module!
#
# Creation Date:    1/30/98 2:59:04PM
#
# License:      This is free software.  You may use this software for any
#               purpose including modification/redistribution, so long as
#               this header remains intact and that you do not claim any
#               rights of ownership or authorship of this software.  This
#               software has been tested, but no warranty is expressed or
#               implied.
#
#------------------------------------------------------------------------

import  os, sys, string, socket, errno, struct
from    StringIO   import StringIO
import  cgi

#---------------------------------------------------------------------------

# Set various FastCGI constants
# Maximum number of requests that can be handled
FCGI_MAX_REQS=1
FCGI_MAX_CONNS = 1

# Supported version of the FastCGI protocol
FCGI_VERSION_1 = 1

# Boolean: can this application multiplex connections?
FCGI_MPXS_CONNS=0

# Record types
FCGI_BEGIN_REQUEST = 1 ; FCGI_ABORT_REQUEST = 2 ; FCGI_END_REQUEST   = 3
FCGI_PARAMS        = 4 ; FCGI_STDIN         = 5 ; FCGI_STDOUT        = 6
FCGI_STDERR        = 7 ; FCGI_DATA          = 8 ; FCGI_GET_VALUES    = 9
FCGI_GET_VALUES_RESULT = 10
FCGI_UNKNOWN_TYPE = 11
FCGI_MAXTYPE = FCGI_UNKNOWN_TYPE

# Types of management records
ManagementTypes = [FCGI_GET_VALUES]

FCGI_NULL_REQUEST_ID = 0

# Masks for flags component of FCGI_BEGIN_REQUEST
FCGI_KEEP_CONN = 1

# Values for role component of FCGI_BEGIN_REQUEST
FCGI_RESPONDER = 1 ; FCGI_AUTHORIZER = 2 ; FCGI_FILTER = 3

# Values for protocolStatus component of FCGI_END_REQUEST
FCGI_REQUEST_COMPLETE = 0               # Request completed nicely
FCGI_CANT_MPX_CONN    = 1               # This app can't multiplex
FCGI_OVERLOADED       = 2               # New request rejected; too busy
FCGI_UNKNOWN_ROLE     = 3               # Role value not known


error = 'fcgi.error'


#---------------------------------------------------------------------------

# The following function is used during debugging; it isn't called
# anywhere at the moment

def error(msg):
    "Append a string to /tmp/err"
    errf = open('/tmp/err', 'a+')
    errf.write(msg+'\n')
    errf.close()

#---------------------------------------------------------------------------

class record:
    "Class representing FastCGI records"
    def __init__(self):
        self.version = FCGI_VERSION_1
        self.recType = FCGI_UNKNOWN_TYPE
        self.reqId   = FCGI_NULL_REQUEST_ID
        self.content = ""

    #----------------------------------------
    def readRecord(self, sock, unpack=struct.unpack):
        (self.version, self.recType, self.reqId, contentLength,
         paddingLength) = unpack(">BBHHBx", sock.recv(8))

        content = ""
        while len(content) < contentLength:
            content = content + sock.recv(contentLength - len(content))
        self.content = content

        if paddingLength != 0:
            padding = sock.recv(paddingLength)

        # Parse the content information
        if self.recType == FCGI_BEGIN_REQUEST:
            (self.role, self.flags) = unpack(">HB", content[:3])

        elif self.recType == FCGI_UNKNOWN_TYPE:
            self.unknownType = ord(content[0])

        elif self.recType == FCGI_GET_VALUES or self.recType == FCGI_PARAMS:
            self.values = {}
            pos = 0
            while pos < len(content):
                name, value, pos = readPair(content, pos)
                self.values[name] = value

        elif self.recType == FCGI_END_REQUEST:
            (self.appStatus, self.protocolStatus) = unpack(">IB", content[0:5])

    #----------------------------------------
    def writeRecord(self, sock, pack=struct.pack):
        content = self.content
        if self.recType == FCGI_BEGIN_REQUEST:
            content = pack(">HBxxxxx", self.role, self.flags)

        elif self.recType == FCGI_UNKNOWN_TYPE:
            content = pack(">Bxxxxxx", self.unknownType)

        elif self.recType == FCGI_GET_VALUES or self.recType == FCGI_PARAMS:
            content = ""
            for i in self.values.keys():
                content = content + writePair(i, self.values[i])

        elif self.recType == FCGI_END_REQUEST:
            content = pack(">IBxxx", self.appStatus, self.protocolStatus)

        cLen = len(content)
        eLen = (cLen + 7) & (0xFFFF - 7)    # align to an 8-byte boundary
        padLen = eLen - cLen

        hdr = pack(">BBHHBx", self.version, self.recType, self.reqId, cLen,
                   padLen)

        ##debug.write('Sending fcgi record: %s\n' % repr(content[:50]) )
        sock.send(hdr + content + padLen*'\000')

#---------------------------------------------------------------------------

_lowbits = ~(1L << 31) # everything but the 31st bit

def readPair(s, pos):
    nameLen = ord(s[pos]) ; pos = pos+1
    if nameLen & 128:
        pos = pos + 3
        nameLen = int(struct.unpack(">I", s[pos-4:pos])[0] & _lowbits)
    valueLen = ord(s[pos]) ; pos = pos+1
    if valueLen & 128:
        pos = pos + 3
        valueLen = int(struct.unpack(">I", s[pos-4:pos])[0] & _lowbits)
    return ( s[pos:pos+nameLen], s[pos+nameLen:pos+nameLen+valueLen],
             pos+nameLen+valueLen )

#---------------------------------------------------------------------------

_highbit = (1L << 31)

def writePair(name, value):
    l = len(name)
    if l < 128:
        s = chr(l)
    else:
        s = struct.pack(">I", l | _highbit)
    l = len(value)
    if l < 128:
        s = s + chr(l)
    else:
        s = s + struct.pack(">I", l | _highbit)
    return s + name + value

#---------------------------------------------------------------------------

def HandleManTypes(r, conn):
    if r.recType == FCGI_GET_VALUES:
        r.recType = FCGI_GET_VALUES_RESULT
        v = {}
        vars = {'FCGI_MAX_CONNS' : FCGI_MAX_CONNS,
                'FCGI_MAX_REQS'  : FCGI_MAX_REQS,
                'FCGI_MPXS_CONNS': FCGI_MPXS_CONNS}
        for i in r.values.keys():
            if i in vars:
                v[i] = vars[i]
        r.values = vars
        r.writeRecord(conn)

#---------------------------------------------------------------------------
#---------------------------------------------------------------------------


_isFCGI = 1         # assume it is until we find out for sure

def isFCGI():
    return _isFCGI



#---------------------------------------------------------------------------


_init = None
_sock = None

class FCGI:
    def __init__(self):
        self.haveFinished = 0
        if _init == None:
            _startup()
        if not _isFCGI:
            self.haveFinished = 1
            self.inp = sys.__stdin__
            self.out = sys.__stdout__
            self.err = sys.__stderr__
            self.env = os.environ
            return

        if 'FCGI_WEB_SERVER_ADDRS' in os.environ:
            good_addrs = string.split(os.environ['FCGI_WEB_SERVER_ADDRS'], ',')
            good_addrs = map(string.strip, good_addrs)        # Remove whitespace
        else:
            good_addrs = None

        self.conn, addr = _sock.accept()
        stdin, data = "", ""
        self.env = {}
        self.requestId = 0
        remaining = 1

        # Check if the connection is from a legal address
        if good_addrs != None and addr not in good_addrs:
            raise error, 'Connection from invalid server!'

        while remaining:
            r = record()
            r.readRecord(self.conn)

            if r.recType in ManagementTypes:
                HandleManTypes(r, self.conn)

            elif r.reqId == 0:
                # Oh, poopy.  It's a management record of an unknown
                # type.  Signal the error.
                r2 = record()
                r2.recType = FCGI_UNKNOWN_TYPE
                r2.unknownType = r.recType
                r2.writeRecord(self.conn)
                continue                # Charge onwards

            # Ignore requests that aren't active
            elif r.reqId != self.requestId and r.recType != FCGI_BEGIN_REQUEST:
                continue

            # If we're already doing a request, ignore further BEGIN_REQUESTs
            elif r.recType == FCGI_BEGIN_REQUEST and self.requestId != 0:
                continue

            # Begin a new request
            if r.recType == FCGI_BEGIN_REQUEST:
                self.requestId = r.reqId
                if r.role == FCGI_AUTHORIZER:   remaining = 1
                elif r.role == FCGI_RESPONDER:  remaining = 2
                elif r.role == FCGI_FILTER:     remaining = 3

            elif r.recType == FCGI_PARAMS:
                if r.content == "":
                    remaining = remaining-1
                else:
                    for i in r.values.keys():
                        self.env[i] = r.values[i]

            elif r.recType == FCGI_STDIN:
                if r.content == "":
                    remaining = remaining-1
                else:
                    stdin = stdin+r.content

            elif r.recType == FCGI_DATA:
                if r.content == "":
                    remaining = remaining-1
                else:
                    data = data+r.content
        # end of while remaining:

        self.inp = StringIO(stdin)
        self.err = StringIO()
        self.out = StringIO()
        self.data = StringIO(data)

    def __del__(self):
        self.Finish()

    def Finish(self, status=0):
        if not self.haveFinished:
            self.haveFinished = 1

            self.err.seek(0,0)
            self.out.seek(0,0)

            ##global debug
            ##debug = open("/tmp/quixote-debug.log", "a+")
            ##debug.write("fcgi.FCGI.Finish():\n")

            r = record()
            r.recType = FCGI_STDERR
            r.reqId = self.requestId
            data = self.err.read()
            ##debug.write("  sending stderr (%s)\n" % `self.err`)
            ##debug.write("  data = %s\n" % `data`)
            while data:
                chunk, data = self.getNextChunk(data)
                ##debug.write("  chunk, data = %s, %s\n" % (`chunk`, `data`))
                r.content = chunk
                r.writeRecord(self.conn)
            r.content = ""
            r.writeRecord(self.conn)      # Terminate stream

            r.recType = FCGI_STDOUT
            data = self.out.read()
            ##debug.write("  sending stdout (%s)\n" % `self.out`)
            ##debug.write("  data = %s\n" % `data`)
            while data:
                chunk, data = self.getNextChunk(data)
                r.content = chunk
                r.writeRecord(self.conn)
            r.content = ""
            r.writeRecord(self.conn)      # Terminate stream

            r = record()
            r.recType = FCGI_END_REQUEST
            r.reqId = self.requestId
            r.appStatus = status
            r.protocolStatus = FCGI_REQUEST_COMPLETE
            r.writeRecord(self.conn)
            self.conn.close()

            #debug.close()


    def getFieldStorage(self):
        method = 'GET'
        if 'REQUEST_METHOD' in self.env:
            method = string.upper(self.env['REQUEST_METHOD'])
        if method == 'GET':
            return cgi.FieldStorage(environ=self.env, keep_blank_values=1)
        else:
            return cgi.FieldStorage(fp=self.inp,
                                    environ=self.env,
                                    keep_blank_values=1)

    def getNextChunk(self, data):
        chunk = data[:8192]
        data = data[8192:]
        return chunk, data


Accept = FCGI       # alias for backwards compatibility
#---------------------------------------------------------------------------

def _startup():
    global _isFCGI, _init, _sock
    # This function won't work on Windows at all.
    if sys.platform[:3] == 'win':
        _isFCGI = 0
        return

    _init = 1
    try:
        s = socket.fromfd(sys.stdin.fileno(), socket.AF_INET,
                          socket.SOCK_STREAM)
        s.getpeername()
    except socket.error, (err, errmsg):
        if err != errno.ENOTCONN:       # must be a non-fastCGI environment
            _isFCGI = 0
            return

    _sock = s


#---------------------------------------------------------------------------

def _test():
    counter = 0
    try:
        while isFCGI():
            req = Accept()
            counter = counter+1

            try:
                fs = req.getFieldStorage()
                size = string.atoi(fs['size'].value)
                doc = ['*' * size]
            except:
                doc = ['<HTML><HEAD>'
                       '<TITLE>FCGI TestApp</TITLE>'
                       '</HEAD>\n<BODY>\n']
                doc.append('<H2>FCGI TestApp</H2><P>')
                doc.append('<b>request count</b> = %d<br>' % counter)
                doc.append('<b>pid</b> = %s<br>' % os.getpid())
                if 'CONTENT_LENGTH' in req.env:
                    cl = string.atoi(req.env['CONTENT_LENGTH'])
                    doc.append('<br><b>POST data (%s):</b><br><pre>' % cl)
                    keys = fs.keys()
                    keys.sort()
                    for k in keys:
                        val = fs[k]
                        if type(val) == type([]):
                            doc.append('    <b>%-15s :</b>  %s\n'
                                       % (k, val))
                        else:
                            doc.append('    <b>%-15s :</b>  %s\n'
                                       % (k, val.value))
                    doc.append('</pre>')


                doc.append('<P><HR><P><pre>')
                keys = req.env.keys()
                keys.sort()
                for k in keys:
                    doc.append('<b>%-20s :</b>  %s\n' % (k, req.env[k]))
                doc.append('\n</pre><P><HR>\n')
                doc.append('</BODY></HTML>\n')


            doc = string.join(doc, '')
            req.out.write('Content-length: %s\r\n'
                        'Content-type: text/html\r\n'
                        'Cache-Control: no-cache\r\n'
                        '\r\n'
                            % len(doc))
            req.out.write(doc)

            req.Finish()
    except:
        import traceback
        f = open('traceback', 'w')
        traceback.print_exc( file = f )
#        f.write('%s' % doc)

if __name__ == '__main__':
    #import pdb
    #pdb.run('_test()')
    _test()
