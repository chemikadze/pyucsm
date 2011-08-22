#!/usr/bin/python
# -*- coding: utf8 -*-

from pyucsm import *
import testucsmparams
import time

if __name__ == '__main__':
    conn = UcsmConnection(testucsmparams.HOST, 80)
    try:
        conn.login(testucsmparams.LOGIN, testucsmparams.PASSWORD)
        for eid, config in conn.iter_events():
            print '%s E№%s %s' % (time.strftime("%d %b %Y %H:%M:%S", time.localtime()), eid, config)
    finally:
        conn.logout()