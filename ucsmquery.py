#!/usr/bin/python

# Copyright (c) 2011 Grid Dynamics Consulting Services, Inc, All Rights Reserved
#  http://www.griddynamics.com
#
#    Licensed under the Apache License, Version 2.0 (the "License");
#    you may not use this file except in compliance with the License.
#    You may obtain a copy of the License at
#
#        http://www.apache.org/licenses/LICENSE-2.0
#
#  THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
#  AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
#  IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
#  DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT OWNER OR CONTRIBUTORS BE LIABLE
#  FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL
#  DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR
#  SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER
#  CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY,
#  OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
#  OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
#
#  @Project:     pyucsm
#  @Description: Python binding for CISCO UCS XML API


from pyucsm import *
import getopt
from inspect import getargspec
import sys


IGNORE = ['set_auth', 'login', 'logout', 'refresh']
CONN_CLS = UcsmConnection
ONLY_DN = False
HIERARCHY = False


def gener_descr(func):
    args = getargspec(func)[0]
    args = args[args[0] == 'self':]
    templ = "Method:\t\t%(name)s"
    if args:
        templ += '\nArguments:\t%(args)s'
    if func.func_doc:
        templ += '\nDocumentation:\t%(doc)s'
    return templ % {'name': func.func_name, 'args': ', '.join(args),
       'doc': func.func_doc}


def get_possible_opts(cls):
    return list(set('%s=' % arg
            for attr_name, attr in cls.__dict__.items()
                if attr_name not in IGNORE \
                    and attr_name[0] != '_' \
                    and hasattr(attr, 'func_name')
                    for arg in getargspec(attr)[0][1:]))


def create_doc(cls):
    descr = '\n\n'.join(gener_descr(attr)
            for attr_name, attr in cls.__dict__.items()
                if attr_name not in IGNORE \
                    and attr_name[0] != '_' \
                    and hasattr(attr, 'func_name'))
    return descr


def print_help(func_name):
    cls = CONN_CLS
    try:
        print gener_descr(getattr(cls, func_name))
    except AttributeError:
        return usage()


def usage():
    print """Usage: ucsmquery.py host[:port] [options] command [arguments].

Options:
    -l login -- UCSM login
    -p pass  -- password

Commands:

%s

Arguments for UCSM query must be used as long options. Sample:

ucsmquery.py 192.168.0.1 -l admin -p 12345  resolve_dn \
--dn=sys/chassis-2/blade-5
""" % create_doc(UcsmConnection)


def wrong_command(command=None):
    print """Command not found or incorrect arguments."""


def print_objects(objects, only_dn=False, hierarchy=False):
    if only_dn:
        for obj in objects:
            try:
                print '%s: %s' % (obj.ucs_class, obj.dn)
            except AttributeError:
                print '%s object has no DN' % obj.ucs_class
            if hierarchy:
                print
                print_objects(obj.children, only_dn, hierarchy)
    else:
        newline = False
        for obj in objects:
            if newline:
                print
            print obj.pretty_str()
            if hierarchy:
                if len(obj.children):
                    print
                print_objects(obj.children, only_dn, hierarchy)
            newline = True


def print_objects_glob(objects):
    print_objects(objects, ONLY_DN, HIERARCHY)


def serialize_print(data):
    if isinstance(data, list):
        if len(data) and isinstance(data[0], UcsmObject):
            print_objects_glob(data)
        else:
            for elem in data:
                serialize_print(elem)
    if isinstance(data, UcsmObject):
        print_objects_glob([data])
    if isinstance(data, dict):
        for key, val in data.items():
            print '%s:'
            serialize_print(val)
    if isinstance(data, basestring):
        print data


def kwargs_to_ucsm_object(cls_, **kwargs):
    obj = UcsmObject(cls_)
    for key, val in kwargs:
        setattr(obj, key, val)
    return obj


def parse_opt_val(string):
    try:
        if string.startswith('{') or \
            string.startswith('obj('):
            raise Exception
        return eval(string, {'obj': kwargs_to_ucsm_object,
                             'UcsmObject': UcsmObject})
    except Exception:
        return string


def kwargs_from_opts(opts):
    kwargs = {}
    for opt, val in opts.items():
        kwargs[opt] = parse_opt_val(val)
    return kwargs


def perform(host, login, password, command, args=list(), opts=dict(), port=80):
    client = CONN_CLS(host, port)
    try:
        global quiet
        client.login(login, password)
        reply = getattr(client, command)(*args, **kwargs_from_opts(opts))
        serialize_print(reply)
    except (KeyError, AttributeError):
        wrong_command()
    except UcsmError, e:
        print "Error: %s" % e
    finally:
        client.logout()


def import_class(path):
    mod, cls = path.rsplit('.', 1)
    return getattr(__import__(mod, fromlist=[cls]), cls)


def main():
    global CONN_CLS
    global ONLY_DN
    global HIERARCHY
    try:
        argv = sys.argv[1:]
        opts, args = getopt.gnu_getopt(argv, 'l:p:P:dqcr',
                                       get_possible_opts(CONN_CLS))
    except getopt.GetoptError, e:
        usage()
        print e
        exit()
    login = 'admin'
    password = 'nbv12345'
    comm_opts = {}
    global quiet
    quiet = False
    for opt, val in opts:
        if opt == '-l':
            login = val
        elif opt == '-p':
            password = val
        elif opt == '-d':
            import pyucsm
            pyucsm.set_debug(True)
        elif opt[:2] == '--':
            comm_opts[opt[2:]] = val
        elif opt == '-q':
            ONLY_DN = True
        elif opt == '-r':
            HIERARCHY = True
        elif opt == '-c':
            CONN_CLS = import_class(val)
    if len(args) >= 2:
        if args[0] == 'help':
            print_help(args[1])
            exit(0)
        port = 80
        host = args[0]
        colon = args[0].find(':')
        if colon >= 0:
            host = args[0][:colon]
            port = int(args[0][colon + 1:])
        perform(host, login, password, args[1], args=args[2:],
                opts=comm_opts, port=port)
    else:
        usage()

if __name__ == '__main__':
    main()
