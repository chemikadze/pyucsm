#!/usr/bin/python
from pyexpat import ExpatError

__author__ = 'nsokolov'

_DEBUG = False

import httplib
from xml.dom import minidom
import xml.dom as dom
from threading import Timer
from pyexpat import ExpatError

def _iterable(possibly_iterable):
    try:
        iter(possibly_iterable)
    except TypeError:
        return False
    return True

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


class UcsmFilterOp:
    def xml(self):
        return ''

    def final_xml(self):
        return "<inFilter>\n\t%s\n</inFilter>" % self.xml()

    def _raise_type_mismatch(self, obj):
        raise UcsmTypeMismatchError("Expected UcsmPropertyFilter or UcsmComposeFilter, got object %s" % repr(obj))

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
        self.__cookie = None
        self.__login = None
        self.__password = None
        self.version = None
        self.session_id = None
        try:
            body = self._instantiate_simple_query('aaaLogin', inName=login, inPassword=password)
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
            body = self._instantiate_simple_query('aaaLogout', inCookie=cookie)
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
            body = self._instantiate_simple_query('aaaRefresh', inName=login, inPassword=password, inCookie=cookie)
            reply_xml, conn = self._perform_xml_call(body)
            response_atom = reply_xml.firstChild
            self._get_cookie_from_xml(response_atom)
        except KeyError:
            raise UcsmFatalError("Wrong reply syntax.")

    def _get_single_object_from_response(self, data):
        try:
            out_config = data.getElementsByTagName('outConfig')[0]
            xml_childs = [child for child in out_config.childNodes if child.nodeType == dom.Node.ELEMENT_NODE]
            childs = map(lambda c: UcsmObject(c), xml_childs)
            if len(childs):
                return childs[0]
            else:
                return None
        except KeyError, IndexError:
            raise UcsmFatalError('No outConfig section in server response!')

    def _get_objects_from_response(self, data):
        try:
            out_config = data.getElementsByTagName('outConfigs')[0]
            xml_childs = [child for child in out_config.childNodes if child.nodeType == dom.Node.ELEMENT_NODE]
            return map(lambda c: UcsmObject(c), xml_childs)
        except KeyError, IndexError:
            raise UcsmFatalError('No outConfig section in server response!')

    def _get_unresolved_from_response(self, data):
        try:
            out_config = data.getElementsByTagName('outUnresolved')[0]
            xml_childs = [child for child in out_config.childNodes
                            if child.nodeType == dom.Node.ELEMENT_NODE
                               and child.nodeName == 'dn']
            return map(lambda c: c.attributes['value'].value.encode('utf8'), xml_childs)
        except KeyError, IndentationError:
            raise UcsmFatalError('No outUnresolved section in server response!')

    def resolve_children(self, class_id='', dn='', hierarchy=False, filter=UcsmFilterOp()):
        data,conn = self._perform_query('configResolveChildren',
                                        filter = filter,
                                        cookie = self.__cookie,
                                        classId = class_id,
                                        inDn = dn,
                                        inHierarchical = hierarchy and "yes" or "no")
        self._check_is_error(data.firstChild)
        return self._get_objects_from_response(data)

    def resolve_class(self, class_id, filter=UcsmFilterOp(), hierarchy=False):
        data,conn = self._perform_query('configResolveClass',
                                   filter = filter,
                                   cookie = self.__cookie,
                                   classId = class_id,
                                   inHierarchical = hierarchy and "yes" or "no")
        self._check_is_error(data.firstChild)
        return self._get_objects_from_response(data)

    def resolve_classes(self, classes, hierarchy=False):
        classes_xml = "<inIds>\n%s\n</inIds>" % ('\n'.join('<id value="%s"/>'%cls for cls in classes))
        data,conn = self._perform_complex_query('configResolveClasses',
                                                data = classes_xml,
                                                inHierarchical = hierarchy and "yes" or "no")
        self._check_is_error(data.firstChild)
        return self._get_objects_from_response(data)

    def resolve_dn(self, dn, hierarchy=False):
        data,conn = self._perform_query('configResolveDn',
                                        cookie = self.__cookie,
                                        dn = dn,
                                        inHierarchical = hierarchy and "yes" or "no")
        self._check_is_error(data.firstChild)
        res = self._get_single_object_from_response(data)
        if res:
            return res
        else:
            return None

    def resolve_dns(self, dns, hierarchy=False):
        """Returns tuple contains list of resolved objects and list of unresolved dns..
        """
        dns_xml = "<inDns>\n%s\n</inDns>" % ('\n'.join('<dn value="%s" />'%cls for cls in dns))
        data,conn = self._perform_complex_query('configResolveDns',
                                        data = dns_xml,
                                        inHierarchical = hierarchy and "yes" or "no")
        self._check_is_error(data.firstChild)
        resolved = self._get_objects_from_response(data)
        unresolved = self._get_unresolved_from_response(data)
        return resolved, unresolved

    def find_dns_by_class_id(self, class_id, filter=None):
        data,conn = self._perform_query('configFindDnsByClassId',
                                                filter=filter,
                                                cookie = self.__cookie,
                                                classId = class_id)
        self._check_is_error(data.firstChild)
        try:
            out_dns_node = data.getElementsByTagName('outDns')[0]
            dns = [ child.attributes['value'].value.encode('utf8') for child in out_dns_node.childNodes
                        if child.nodeType == dom.Node.ELEMENT_NODE]
            return dns
        except IndexError,KeyError:
            raise UcsmFatalError('No outDns section in server response!')


    def resolve_parent(self, dn, hierarchy=False):
        data,conn = self._perform_query('configResolveParent',
                                        cookie = self.__cookie,
                                        dn = dn,
                                        inHierarchical = hierarchy and "yes" or "no")
        self._check_is_error(data.firstChild)
        res = self._get_single_object_from_response(data)
        return res

    def conf_mo(self, config, dn="", hierachy=True):
        data,conn = self._perform_complex_query('configConfMo',
                                                data='<inConfig>'+config.xml()+'</inConfig>',
                                                dn = dn,
                                                inHierarchical = hierachy and "yes" or "no")
        self._check_is_error(data.firstChild)
        res = self._get_single_object_from_response(data)
        return res

    def conf_mos(self, configs):
        """Gets dictionary of dn:config as configs argument. Equivalent for several configConfMo requests.
        returns dirtionary of dn:canged_config.
        """
        configs = '<inConfigs>%s</inConfigs>' % '\n'.join('<pair key="%s">%s</pair>' %
                                                          (k, c.xml()) for k,c in configs.items())
        data,conn = self._perform_complex_query('configConfMos',
                                                data=configs)
        self._check_is_error(data.firstChild)
        buf_res = self._get_objects_from_response(data)
        res = {}
        try:
            for pair in buf_res:
                if pair.ucs_class == 'pair':
                    res[pair.key] = pair.children[0]
                else:
                    raise UcsmFatalError('Wrong reply: non-pair object in outConfigs section')
            return res
        except IndexError:
            raise UcsmFatalError('Wrong reply: recieved pair does not contains value')
        except AttributeError:
            raise UcsmFatalError('Wrong reply: recieved pair does not have key')


    def conf_mo_group(self, dns, config, hierarchy=False):
        """Makes equivalent changes in several dns.
        """
        dns_data = '\n'.join('<dn value="%s" />' % dn for dn in dns)
        data = '<inConfig>%s</inConfig>\n<inDns>%s</inDns>' % (config.xml(), dns_data)
        data,conn = self._perform_complex_query('configConfMoGroup',
                                                data=data,
                                                inHierarchical = hierarchy and "yes" or "no")
        self._check_is_error(data.firstChild)
        return self._get_objects_from_response(data)

    def _refresh(self):
        self.__cookie = self.refresh()
        self.__refresh_timer = self._recreate_refresh_timer()

    def _recreate_refresh_timer(self):
        Timer(self.refresh_period/2, self._refresh)

    def _check_is_error(self, response_atom):
        if response_atom.attributes.has_key("errorCode"):
            error_code = int(response_atom.attributes["errorCode"].value)
            error_description = response_atom.attributes["errorDescr"].value.encode('utf8')
            raise UcsmResponseError(error_code, error_description)

    def _perform_xml_call(self, request_data, headers=None):
        conn = self._create_connection()
        body = request_data
        if _DEBUG:
            print ">> %s" % body
        conn.request("POST", self.__ENDPOINT, body)
        reply = conn.getresponse()
        reply_data = reply.read()
        if _DEBUG:
            print "<< %s" % reply_data
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

    def _perform_query(self, method, filter=None, **kwargs):
        """Gets query method name and its parameters. Filter must be an instance of class, derived from UcsmFilterToken.
        """
        if filter is None:
            body = self._instantiate_simple_query(method, **kwargs)
        else:
            body = self._instantiate_complex_query(method, child_data=filter.final_xml(), **kwargs)
        data, conn = self._perform_xml_call(body)
        return data, conn

    def _perform_complex_query(self, method, data, filter=None, **kwargs):
        """Gets query method name and its parameters. Filter must be an instance of class, derived from UcsmFilterToken.
                 Data is a string for inner xml body.
        """
        if filter is None:
            body = self._instantiate_complex_query(method, child_data=data, **kwargs)
        else:
            body = self._instantiate_complex_query(method, child_data=filter.final_xml()+'\n'+data, **kwargs)
        data, conn = self._perform_xml_call(body)
        return data, conn

    def _instantiate_simple_query(self, method, **kwargs):
        params = ' '.join( [('%s="%s"'%(key,value)) for key,value in kwargs.items()] )
        return "<%(method)s %(params)s />" % locals()

    def _instantiate_complex_query(self, method, child_data=None, **kwargs):
        """Formats query with some child nodes. Child data can be string or list of strings.
        """
        if child_data is not None:
            child_body = child_data
            params = ' '.join( [('%s="%s"'%(key,value)) for key,value in kwargs.items()] )
            if _iterable(child_data) and not isinstance(child_data, basestring):
                child_body = '\n'.join(child_data_)
            body = "<%(method)s %(params)s>\n\t%(child_body)s\n</%(method)s>" % locals()
            return body
        else:
            return self._instantiate_simple_query(method, **kwargs)


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
        return '<%(op)s class="%(cls)s" property="%(prop)s" value="%(val)s" />' % locals()



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


class UcsmObject:
    def __init__(self, dom_node=None, parent=None):
        self.children = []
        self.attributes = {}
        self.parent = parent
        if dom_node is None:
            self.ucs_class = None
        else:
            if dom_node.nodeType != dom.Node.ELEMENT_NODE:
                raise TypeError('UcsmObjects can be created only from XML element nodes.')
            self.children = []
            self.attributes = {}
            self.ucs_class = dom_node.nodeName.encode('utf8')
            if dom_node is not None:
                for child_node in dom_node.childNodes:
                    if child_node.nodeType == dom.Node.ELEMENT_NODE:
                        child = UcsmObject(child_node, self)
                        self.children.append(child)
            for attr,val in dom_node.attributes.items():
                self.attributes[attr.encode('utf8')] = val.encode('utf8')

    def __getattr__(self, item):
        try:
            return self.attributes[item]
        except KeyError:
            raise AttributeError('UcsmObject has no attribute \'%s\'' % item)

    def __repr__(self):
        repr = self.ucs_class
        if len(self.attributes):
            repr = repr + '; ' + ' '.join('%s=%s'%(n,v) for n,v in self.attributes.items())
        return '<UcsmObject instance at %x with class %s>' % (id(self), repr)

    def xml(self):
        attributes =  ' '.join('%s="%s"'%(n,v) for n,v in self.attributes.items())
        return '<%s %s/>' % (self.ucs_class, attributes)

    def pretty_str(self):
        str = self.ucs_class
        for name,val in self.attributes.items():
            str += '\n%s: %s' % (name,val)
        return str