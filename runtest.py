#!/usr/bin/python
__author__ = 'nsokolov'

import unittest
import pyucsm
import httplib
import testucsmparams
from xml.dom import minidom

_host = testucsmparams.HOST
_login = testucsmparams.LOGIN
_password = testucsmparams.PASSWORD

pyucsm.DEBUG = True

class MyBaseTest(unittest.TestCase):
    def assertXmlEquals(self, str1, str2):
        return ''.join(str1.split()) == ''.join(str2.split())

class TestUcsmConnection(MyBaseTest):
    """Need have some working UCSM system to run this tests.
    """

    def test_constructor_nossl(self):
        item = pyucsm.UcsmConnection(_host, 80)
        self.assertEqual(item.__dict__['_create_connection']().__class__, httplib.HTTPConnection)
        
    def test_constructor_ssl(self):
        item = pyucsm.UcsmConnection(_host, 80, secure=True)
        self.assertEqual(item.__dict__['_create_connection']().__class__, httplib.HTTPSConnection)

    def test_connection_ok(self):
        c = pyucsm.UcsmConnection(_host, 80)
        try:
            c.login(_login, _password)
        finally:
            c.logout()

    def test_connection_refresh(self):
        c = pyucsm.UcsmConnection(_host, 80)
        try:
            c.login(_login, _password)
            c.refresh()
        finally:
            c.logout()
        
    def test_connection_wrong_password(self):
        c = pyucsm.UcsmConnection(_host, 80)
        if not testucsmparams.SIMULATOR:
            with self.assertRaises(pyucsm.UcsmResponseError):
                c.login(_login, 'this is wrong password')
                c.logout()

    def test_connection_404(self):
        c = pyucsm.UcsmConnection('example.com', 80)
        with self.assertRaises(pyucsm.UcsmFatalError):
            c.login(_login, 'this is wrong password')
            c.logout()

    def test_property_filter(self):
        self.assertIsInstance(pyucsm.UcsmAttribute('cls','attr')>5, pyucsm.UcsmPropertyFilter)
        self.assertIsInstance(pyucsm.UcsmAttribute('cls','attr')>=5, pyucsm.UcsmPropertyFilter)
        self.assertIsInstance(pyucsm.UcsmAttribute('cls','attr')<5, pyucsm.UcsmPropertyFilter)
        self.assertIsInstance(pyucsm.UcsmAttribute('cls','attr')<=5, pyucsm.UcsmPropertyFilter)
        self.assertIsInstance(pyucsm.UcsmAttribute('cls','attr')==5, pyucsm.UcsmPropertyFilter)
        self.assertIsInstance(pyucsm.UcsmAttribute('cls','attr')!=5, pyucsm.UcsmPropertyFilter)
        self.assertIsInstance(pyucsm.UcsmAttribute('cls','attr').wildcard_match('*'), pyucsm.UcsmPropertyFilter)
        self.assertIsInstance(pyucsm.UcsmAttribute('cls','attr').any_bit(['one','two']), pyucsm.UcsmPropertyFilter)
        self.assertIsInstance(pyucsm.UcsmAttribute('cls','attr').any_bit('one,two'), pyucsm.UcsmPropertyFilter)
        self.assertIsInstance(pyucsm.UcsmAttribute('cls','attr').all_bit(['one','two']), pyucsm.UcsmPropertyFilter)
        self.assertIsInstance(pyucsm.UcsmAttribute('cls','attr').all_bit('one,two'), pyucsm.UcsmPropertyFilter)

    def test_compose_filter(self):
        self.assertIsInstance((pyucsm.UcsmAttribute('cls','attr')>5) & (pyucsm.UcsmAttribute('cls','attr')>5),
                              pyucsm.UcsmComposeFilter)
        self.assertIsInstance((pyucsm.UcsmAttribute('cls','attr')>5) | (pyucsm.UcsmAttribute('cls','attr')>5),
                              pyucsm.UcsmComposeFilter)
        self.assertIsInstance(~((pyucsm.UcsmAttribute('cls','attr')>5) & (pyucsm.UcsmAttribute('cls','attr')>5)),
                              pyucsm.UcsmComposeFilter)
        self.assertIsInstance(~((pyucsm.UcsmAttribute('cls','attr')>5) | (pyucsm.UcsmAttribute('cls','attr')>5)),
                              pyucsm.UcsmComposeFilter)

        expr = (pyucsm.UcsmAttribute('cls','attr')>5) & (pyucsm.UcsmAttribute('cls','attr')>5) & \
               (pyucsm.UcsmAttribute('cls','attr')>5)
        self.assertIsInstance(expr, pyucsm.UcsmComposeFilter)
        self.assertEqual(len(expr.arguments), 3)

        expr = (pyucsm.UcsmAttribute('cls','attr')>5) | (pyucsm.UcsmAttribute('cls','attr')>5) | \
               (pyucsm.UcsmAttribute('cls','attr')>5)
        self.assertIsInstance(expr, pyucsm.UcsmComposeFilter)
        self.assertEqual(len(expr.arguments), 3)

        expr = (pyucsm.UcsmAttribute('cls','attr')>5) | (pyucsm.UcsmAttribute('cls','attr')>5) & \
               (pyucsm.UcsmAttribute('cls','attr')>5)
        self.assertIsInstance(expr, pyucsm.UcsmComposeFilter)
        self.assertNotEqual(len(expr.arguments), 3)

        expr = (pyucsm.UcsmAttribute('cls','attr')>5) & (pyucsm.UcsmAttribute('cls','attr')>5) | \
               (pyucsm.UcsmAttribute('cls','attr')>5)
        self.assertIsInstance(expr, pyucsm.UcsmComposeFilter)
        self.assertNotEqual(len(expr.arguments), 3)

    def test_simple_query_construct(self):
        conn = pyucsm.UcsmConnection('host', 80)
        self.assertXmlEquals('<firsttest />',
                                conn._instantiate_simple_query('firsttest'))
        self.assertXmlEquals('<secondtest one="1" two="zwei" />',
                                conn._instantiate_simple_query('secondtest', one=1, two="zwei"))

    def test_child_query_construct(self):
        conn = pyucsm.UcsmConnection('host', 80)
        self.assertXmlEquals('<secondtest one="1" two="zwei" />',
                                conn._instantiate_simple_query('secondtest', one=1, two="zwei"))
        wish = """<getSmth cookie="123456"><inFilter><gt class="blade" prop="cores" value="2" /></inFilter></getSmth>"""
        self.assertXmlEquals(wish,
                             conn._instantiate_complex_query('getSmth',
                                                             child_data_= (pyucsm.UcsmAttribute('blade','cores')>2).xml(),
                                                             cookie='123456'))

    def test_ucsm_object_single(self):
        xml_str = """<computeBlade adminPower="policy" adminState="in-service" assignedToDn="org-root/ls-11"
        association="associated" availability="unavailable" availableMemory="8192" chassisId="1"
        checkPoint="discovered" connPath="A,B" connStatus="A" descr="" discovery="complete" dn="sys/chassis-1/blade-1"
        fltAggr="0" fsmDescr="" fsmFlags="" fsmPrev="TurnupSuccess" fsmProgr="100" fsmRmtInvErrCode="none"
        fsmRmtInvErrDescr="" fsmRmtInvRslt="" fsmStageDescr="" fsmStamp="2011-06-29T12:35:04.205" fsmStatus="nop"
        fsmTry="0" intId="28925" lc="undiscovered" lcTs="1970-01-01T01:00:00.000" lowVoltageMemory="not-applicable"
        managingInst="A" memorySpeed="not-applicable" model="N20-B6620-1" name="" numOfAdaptors="1" numOfCores="10"
        numOfCoresEnabled="10" numOfCpus="2" numOfEthHostIfs="3" numOfFcHostIfs="0" numOfThreads="14"
        operPower="on" operQualifier="" operState="ok" operability="operable"
        originalUuid="1b4e28ba-2fa1-11d2-0101-b9a761bde3fb" presence="equipped" revision="0" serial="577"
        serverId="1/1" slotId="1" totalMemory="8192" usrLbl="" uuid="1b4e28ba-2fa1-11d2-0101-b9a761bde3fb"
        vendor="Cisco Systems Inc"/>"""
        doc = minidom.parseString(xml_str)
        elem = doc.childNodes[0]
        obj = pyucsm.UcsmObject(elem)
        self.assertEquals('policy', obj.attributes['adminPower'])
        self.assertEquals('policy', obj.adminPower)
        self.assertEquals('sys/chassis-1/blade-1', obj.dn)
        self.assertEquals('computeBlade', obj.ucs_class)
        obj.attributes['this_is_shurely_not_in_dict'] = 42
        self.assertEquals(42, obj.this_is_shurely_not_in_dict)
        obj.this_is_also_not_in_dict = 84
        self.assertEquals(84, obj.this_is_also_not_in_dict)
        copy = obj.copy()
        self.assertEquals(len(obj.attributes), len(copy.attributes))
        self.assertEquals(len(obj.children), len(obj.children))
        obj.ucs_class += 'appended'
        self.assertNotEquals(obj.ucs_class, copy.ucs_class)

    def test_ucsm_object_hierarchy(self):
        obj = pyucsm.UcsmObject('parentClass')
        obj.children.append(pyucsm.UcsmObject('childClass1'))
        obj.children.append(pyucsm.UcsmObject('childClass2'))
        self.assertEquals(1, len(obj.find_children('childClass1')))
        self.assertEquals(1, len(obj.find_children('childClass2')))

    def test_resolve_children(self):
        c = pyucsm.UcsmConnection(_host, 80)
        try:
            c.login(_login, _password)
            res = c.resolve_children('aaaUser', 'sys/user-ext')
            self.assertIsInstance(res, list)
            if len(res):
                self.assertIsInstance(res[0], pyucsm.UcsmObject)
        finally:
            c.logout()

    def test_resolve_class(self):
        c = pyucsm.UcsmConnection(_host, 80)
        try:
            c.login(_login, _password)
            res = c.resolve_class('pkiEp')
            self.assertIsInstance(res, list)
            self.assertIsInstance(res[0], pyucsm.UcsmObject)
            res = c.resolve_class('pkiEp', filter=(pyucsm.UcsmAttribute('pkiEp', 'intId')<0))
            self.assertIsInstance(res, list)
            self.assertEquals(0, len(res))
        finally:
            c.logout()

    def test_resolve_classes(self):
        c = pyucsm.UcsmConnection(_host, 80)
        try:
            c.login(_login, _password)
            res = c.resolve_classes(['computeItem', 'equipmentChassis'])
            self.assertIsInstance(res, list)
            self.assertGreater(len(res), 0)
            self.assertIsInstance(res[0], pyucsm.UcsmObject)
        finally:
            c.logout()

    def test_resolve_dn(self):
        c = pyucsm.UcsmConnection(_host, 80)
        try:
            c.login(_login, _password)
            res = c.resolve_dn('sys')
            self.assertIsInstance(res, pyucsm.UcsmObject)
            res = c.resolve_dn('qewr')
            self.assertIsNone(res)
        finally:
            c.logout()

    def test_resolve_dns(self):
        c = pyucsm.UcsmConnection(_host, 80)
        try:
            c.login(_login, _password)
            res,unres = c.resolve_dns(['sys', 'mac', 'ololo'])
            self.assertIsInstance(res, list)
            self.assertIsInstance(unres, list)
            self.assertEquals(len(res), 2)
            self.assertEquals(len(unres), 1)
        finally:
            c.logout()

    def test_resolve_parent(self):
        c = pyucsm.UcsmConnection(_host, 80)
        try:
            c.login(_login, _password)
            res = c.resolve_parent('sys/user-ext')
            self.assertIsInstance(res, pyucsm.UcsmObject)
            self.assertEquals(res.dn, 'sys')
            res = c.resolve_parent('sys/this/is/bullshit')
            self.assertIsNone(res)
        finally:
            c.logout()

    def test_find_dns_by_class_id(self):
        c = pyucsm.UcsmConnection(_host, 80)
        try:
            c.login(_login, _password)
            res = c.find_dns_by_class_id('macpoolUniverse')
            self.assertIsInstance(res, list)
            self.assertEquals(len(res), 1)
            self.assertEquals(res[0], 'mac')
            with self.assertRaises(pyucsm.UcsmFatalError):
                res = c.find_dns_by_class_id('notrealclass')
        finally:
            c.logout()

    def test_conf_mo(self):
        import random
        if testucsmparams.SIMULATOR:
            c = pyucsm.UcsmConnection(_host, 80)
            try:
                c.login(_login, _password)
                src = pyucsm.UcsmObject()
                src.ucs_class = 'aaaLdapEp'
                src.attributes['timeout'] = random.randint(0, 60)
                res = c.conf_mo(src, dn='sys/ldap-ext')
                self.assertEquals(int(res.attributes['timeout']), src.attributes['timeout'])
            finally:
                c.logout()

    def test_conf_mos(self):
        import random
        if testucsmparams.SIMULATOR:
            c = pyucsm.UcsmConnection(_host, 80)
            try:
                c.login(_login, _password)
                src = pyucsm.UcsmObject()
                src.ucs_class = 'aaaLdapEp'
                src.attributes['timeout'] = random.randint(0, 60)
                res = c.conf_mos({'sys/ldap-ext':src})
                print res, src
                self.assertEquals(int(res['sys/ldap-ext'].attributes['timeout']), src.attributes['timeout'])
            finally:
                c.logout()

    def test_conf_mo_group(self):
        import random
        if testucsmparams.SIMULATOR:
            c = pyucsm.UcsmConnection(_host, 80)
            try:
                c.login(_login, _password)
                src = pyucsm.UcsmObject()
                src.ucs_class = 'aaaLdapEp'
                src.attributes['timeout'] = random.randint(0, 60)
                dns = ['sys']
                res = c.conf_mo_group(dns, src)
                self.assertEquals(int(res[0].attributes['timeout']), src.attributes['timeout'])
            finally:
                c.logout()

    def test_estimate_impact(self):
        import random
        if testucsmparams.SIMULATOR:
            c = pyucsm.UcsmConnection(_host, 80)
            try:
                c.login(_login, _password)
                with self.assertRaises(pyucsm.UcsmResponseError):
                    admin_user = pyucsm.UcsmObject()
                    admin_user.ucs_class = 'aaaUser'
                    admin_user.attributes['status'] = 'deleted'
                    admin_user.attributes['dn'] = 'sys/user-ext/user-admin'
                    ack,old_ack,aff,old_aff = c.estimate_impact({'sys/user-ext/user-admin':admin_user})
                newuser = pyucsm.UcsmObject()
                newuser.ucs_class = 'aaaUser'
                newuser.attributes['status'] = 'created'
                newuser.attributes['dn'] = 'sys/user-ext/user-testuser'
                ack,old_ack,aff,old_aff = c.estimate_impact({'sys/user-ext/user-testuser':newuser})
                self.assertEquals(ack, [])
                self.assertEquals(old_ack, [])
                self.assertEquals(aff, [])
                self.assertEquals(old_aff, [])
            finally:
                c.logout()


if __name__ == '__main__':
    unittest.main()
