#!/usr/bin/python
from pyucsm import *
import getopt
import sys

def usage():
    print """Usage: ucsmquery.py host[:port] [options] command [arguments].

Options:
    -l login -- UCSM login
    -p pass  -- password

Commands:

Arguments for UCSM query must be used as long options. Sample:

ucsmquery.py example.com -l admin -p admin configFindDnsByClassId --classId=computeItem
"""

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
                print_objects(obj.children, only_dn, hierarchy)
    else:
        newline = False
        for obj in objects:
            print obj.pretty_str()
            if hierarchy:
                print_objects(obj.children, only_dn, hierarchy)
            if newline:
                print
            newline = True

def perform(host, login, password, command, args=list(), opts=dict(), port=80):
    client = UcsmConnection(host, port)
    try:
        client.login(login, password)
        if command == 'configFindDnsByClassId':
            class_id = opts.get('classId')
            dns = client.find_dns_by_class_id(class_id)
            for dn in dns:
                print dn
        elif command == 'configResolveDn':
            dn = opts.get('dn')
            obj = client.resolve_dn(dn)
            if obj:
                print obj.pretty_str()
            else:
                print 'Object not found'
        elif command == 'configResolveDns':
            hierarchy = 'inHierarchical' in opts
            objects,unresolved = client.resolve_dns(args, hierarchy)
            print_objects(objects, only_dn='only-dn' in opts, hierarchy=hierarchy)
        elif command == 'configResolveChildren':
            class_id = opts.get('classId', '')
            dn = opts.get('inDn', '')
            hierarchy = 'inHierarchical' in opts
            objects = client.resolve_children(class_id, dn, hierarchy)
            print_objects(objects, only_dn='only-dn' in opts, hierarchy=hierarchy)
        elif command == 'configResolveClasses':
            hierarchy = 'inHierarchical' in opts
            objects = client.resolve_classes(args, hierarchy)
            print_objects(objects, only_dn='only-dn' in opts, hierarchy=hierarchy)
        else:
            raise KeyError
    except KeyError:
        wrong_command()
    except UcsmError, e:
        print "Error: %s" % e
    finally:
        client.logout()

if __name__ == '__main__':
    try:
        argv = sys.argv[1:]
        opts, args = getopt.gnu_getopt(argv, 'l:p:P:d', ["classId=", "dn=", "inDn=", "only-dn", "inHierarchical"])
    except getopt.GetoptError:
        usage()
        exit()
    login = 'admin'
    password = 'nbv12345'
    comm_opts = {}
    for opt,val in opts:
        if opt=='-l':
            login = val
        elif opt=='-p':
            password = val
        elif opt=='-d':
            import pyucsm
            pyucsm._DEBUG = True
        elif opt[:2]=='--':
            comm_opts[opt[2:]] = val
    if len(args)>=2:
        port = 80
        host = args[0]
        colon = args[0].find(':')
        if colon>=0:
            host = args[:colon]
            port = int(args[colon+1:])
        perform(args[0], login, password, args[1], args=args[2:], opts=comm_opts, port=port)
    else:
        usage()
