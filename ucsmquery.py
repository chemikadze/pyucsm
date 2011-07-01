from pyucsm import *
import getopt
import sys

def usage():
    print """Usage: ucsmqyery.py host[:port] [options] command [arguments].

Options:
    -l login -- UCSM login
    -p pass  -- password

Commands:

Arguments for UCSM query must be used as long options. Sample:

ucsmquery.py example.com -l admin -p admin configFindDnsByClassId --classId=computeItem
"""

def wrong_command(command=None):
    print """Command not found or incorrect arguments."""

def perform(host, login, password, command, args=dict(), port=80):
    client = UcsmConnection(host, port)
    try:
        client.login(login, password)
        try:
            if command == 'configFindDnsByClassId':
                class_id = args['classId']
                dns = client.find_dns_by_class_id(class_id)
                for dn in dns:
                    print dn
            elif command == 'configResolveDn':
                dn = args['dn']
                obj = client.resolve_dn(dn)
                print obj.pretty_str()
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
        opts, args = getopt.gnu_getopt(argv, 'l:p:P:d', ["classId=","dn="])
    except getopt.GetoptError:
        usage()
        exit()
    login = 'admin'
    password = 'nbv12345'
    comm_args = {}
    for opt,val in opts:
        if opt=='-l':
            login = val
        elif opt=='-p':
            password = val
        elif opt=='-d':
            import pyucsm
            pyucsm._DEBUG = True
        elif opt[:2]=='--':
            comm_args[opt[2:]] = val
    if len(args)==2:
        port = 80
        host = args[0]
        colon = args[0].find(':')
        if colon>=0:
            host = args[:colon]
            port = int(args[colon+1:])
        perform(args[0], login, password, args[1], comm_args, port=port)
    else:
        usage()
