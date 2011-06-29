__author__ = 'nsokolov'

import unittest
import pyucsm
import httplib
import testucsmparams

_host = testucsmparams.host
_login = testucsmparams.login
_password = testucsmparams.password

class TestUcsmConnection(unittest.TestCase):
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
        c.login(_login, _password)
        c.logout()

    def test_connection_refresh(self):
        c = pyucsm.UcsmConnection(_host, 80)
        c.login(_login, _password)
        c.refresh()
        c.logout()
        
    def test_connection_wrong_password(self):
        c = pyucsm.UcsmConnection(_host, 80)
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

if __name__ == '__main__':
    unittest.main()
