from pyexpat import ExpatError

__author__ = 'nsokolov'

import httplib
from xml.dom import minidom
from threading import Timer
from pyexpat import ExpatError

class UcsmError(Exception):
    """Any error during UCSM session.
    """""
    pass

class UcsmFatalError(UcsmError):
    """Syntax or http connection error.
    """
    pass

class UcsmTypeMismatchError(UcsmError):
    """Filter expression is incorrect.
    """
    pass

class UcsmResponseError(Exception):
    """Error returned by UCSM server.
    """
    def __init__(self, code, text=""):
        self.code = code
        self.text = text
        super(UcsmResponseError, self).__init__(text)

class UcsmConnection:
    __ENDPOINT = '/nuova'

    def __init__(self, host, port=None, secure=False, *args, **kwargs):
        if secure:
            self._create_connection = lambda: httplib.HTTPSConnection(host, port, *args, **kwargs)
        else:
            self._create_connection = lambda: httplib.HTTPConnection(host, port, *args, **kwargs)

    def login(self, login, password):
        """Performs authorisation and retrieving cookie from server. Cookie refresh will be performed automatically.
        """
        try:
            body = '<aaaLogin inName="%(login)s" inPassword="%(password)s"/>' % locals()
            reply_xml, conn = self._perform_xml_call(body)
            response_atom = reply_xml.firstChild
            self._get_cookie_from_xml(response_atom)
            self.version = response_atom.attributes["outVersion"].value
            self.session_id = response_atom.attributes["outSessionId"].value
            self.__login = login
            self.__password = password
            return self.__cookie
        except KeyError, UcsmError:
            raise UcsmFatalError("Wrong reply syntax.")


    def logout(self):
        try:
            cookie = self.__cookie
            body = '<aaaLogout inCookie="%(cookie)s"/>' % locals()
            reply_xml, conn = self._perform_xml_call(body)
            response_atom = reply_xml.firstChild
            if response_atom.attributes["response"].value =="yes":
                self._check_is_error(response_atom)
                status = response_atom.attributes["outStatus"].value
                return status
            else:
                raise UcsmFatalError()
        except KeyError, UcsmError:
            raise UcsmFatalError("Wrong reply syntax.")

    def refresh(self):
        """Performs authorisation and retrieving cookie from server. Cookie refresh will be performed automatically.
        """
        try:
            login = self.__login
            password = self.__password
            cookie = self.__cookie
            body = '<aaaRefresh inName="%(login)s" inPassword="%(password)s" inCookie="%(cookie)s"/>' % locals()
            reply_xml, conn = self._perform_xml_call(body)
            response_atom = reply_xml.firstChild
            self._get_cookie_from_xml(response_atom)
        except KeyError:
            raise UcsmFatalError("Wrong reply syntax.")

    def _refresh(self):
        self.__cookie = self.refresh()
        self.__refresh_timer = self._recreate_refresh_timer()

    def _recreate_refresh_timer(self):
        Timer(self.refresh_period/2, self._refresh)

    def _check_is_error(self, response_atom):
        if response_atom.attributes.has_key("errorCode"):
            error_code = response_atom.attributes["errorCode"]
            error_description = response_atom.attributes["errorDescr"]
            raise UcsmResponseError(error_code, error_description)

    def _perform_xml_call(self, request_data, headers=None):
        conn = self._create_connection()
        body = request_data
        conn.request("POST", self.__ENDPOINT, body)
        reply = conn.getresponse()
        reply_data = reply.read()
        print reply_data
        try:
            reply_xml = minidom.parseString(reply_data)
        except:
            raise UcsmFatalError("Error during XML parsing.")
        return reply_xml, conn

    def _get_cookie_from_xml(self, response_atom):
        if response_atom.attributes["response"].value=="yes":
            self._check_is_error(response_atom)
            self.refresh_period = float(response_atom.attributes["outRefreshPeriod"].value)
            self.__cookie = response_atom.attributes["outCookie"].value
            self.__refresh_timer = self._recreate_refresh_timer()
            self.privileges = response_atom.attributes["outPriv"].value.split(',')
            return self.__cookie
        else:
            raise UcsmFatalError()


class UcsmFilterOp:
    def xml(self):
        return ''
    def _raise_type_mismatch(self, obj):
        raise UcsmTypeMismatchError("Expected UcsmPropertyFilter or UcsmComposeFilter, got object %s" % repr(obj))

class UcsmAttribute:
    """Describes class attribute. You can use >, >=, <, <=, ==, != operators to create UCSM property filters. Also wildcard matching,
    all bits and any bits operators are avaliable.
    """

    def __init__(self, class_, attr):
        self.class_ = class_
        self.name = attr

    def __eq__(self, other):
        return UcsmPropertyFilter(self, UcsmPropertyFilter.EQUALS, other)

    def __ne__(self, other):
        return UcsmPropertyFilter(self, UcsmPropertyFilter.NOT_EQUALS, other)

    def __gt__(self, other):
        return UcsmPropertyFilter(self, UcsmPropertyFilter.GREATER, other)

    def __ge__(self, other):
        return UcsmPropertyFilter(self, UcsmPropertyFilter.GREATER_OR_EQUAL, other)

    def __lt__(self, other):
        return UcsmPropertyFilter(self, UcsmPropertyFilter.LESS_THAN, other)

    def __le__(self, other):
        return UcsmPropertyFilter(self, UcsmPropertyFilter.LESS_OR_EQUAL, other)

    def wildcard_match(self, wcard):
        return  UcsmPropertyFilter(self, UcsmPropertyFilter.WILDCARD, wcard)

    def any_bit(self, bits):
        bits_str = bits
        if isinstance(bits, list):
            bits_str = ','.join( str(bit) for bit in bits )
        return UcsmPropertyFilter(self, UcsmPropertyFilter.ANY_BIT, bits_str)

    def all_bit(self, bits):
        bits_str = bits
        if isinstance(bits, list):
            bits_str = ','.join( str(bit) for bit in bits )
        return UcsmPropertyFilter(self, UcsmPropertyFilter.ALL_BIT, bits_str)


class UcsmFilterToken(UcsmFilterOp):
    def __and__(self, other):
        if isinstance(other, (UcsmComposeFilter, UcsmPropertyFilter)):
            return UcsmComposeFilter(UcsmComposeFilter.AND, self, other)
        else:
            self._raise_type_mismatch(other)

    def __or__(self, other):
        if isinstance(other, (UcsmComposeFilter, UcsmPropertyFilter)):
            return UcsmComposeFilter(UcsmComposeFilter.OR, self, other)
        else:
            self._raise_type_mismatch(other)

    def __invert__(self):
        return UcsmComposeFilter(UcsmComposeFilter.NOT, self)


class UcsmPropertyFilter(UcsmFilterToken):

    EQUALS = 'eq'
    NOT_EQUALS = 'ne'
    GREATER = 'gt'
    GREATER_OR_EQUAL = 'ge'
    LESS_THAN = 'lt'
    LESS_OR_EQUAL = 'le'
    WILDCARD = 'wcard'
    ANY_BIT = 'anybit'
    ALL_BIT = 'allbit'

    def __init__(self, attribute, operator, value):
        self.attribute = attribute
        self.operator = operator
        self.value = value

    def xml(self):
        op = self.operator
        prop = self.attribute.name
        cls = self.attribute.class_
        val = self.value
        return '<%(op)s class="%(cls)s" prop="%(prop)s" value="%(val)s" />' % locals()



class UcsmComposeFilter(UcsmFilterToken):

    AND = "and"
    OR = "or"
    NOT = "not"

    def __init__(self, operator, *args):
        self.operator = operator
        self.arguments = []
        for arg in args:
            if isinstance(arg, self.__class__) and arg.operator == self.operator:
                self.arguments.extend(arg.arguments)
            else:
                self.arguments.append(arg)

    def xml(self):
        op = self.operator
        args = "\n".join( arg.xml() for arg in self.arguments )
        return "<%(op)s>\n\t%(args)s\n</%(op)s>" % locals()
