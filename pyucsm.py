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


import httplib
import logging
import time
import os
import socket
from xml.dom import minidom
import xml.dom as dom
from threading import Timer

DEBUG = False

LOG = logging.getLogger('pyucsm')


def set_debug(enable):
    global DEBUG
    DEBUG = enable
    LOG.setLevel(enable and logging.DEBUG or logging.WARNING)


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


class UcsmResponseError(UcsmError):
    """Error returned by UCSM server.
    """

    def __init__(self, code, text=""):
        self.code = code
        self.text = text
        super(UcsmResponseError, self).__init__(text)


class ReadlineAdapter(object):
    """Wrapper, implements readline function for any file object.
    """

    def __init__(self, io):
        self.__io = io

    def __getattr__(self, item):
        return getattr(self.__io, item)

    def readline(self):
        buffer = ''
        while True:
            c = self.__io.read(1)
            if c is not None and c == '\n':
                return buffer
            buffer += c


class UcsmFilterOp(object):
    def xml(self):
        return self.xml_node().toxml()

    def final_xml(self):
        return self.final_xml_node().toxml()

    def final_xml_node(self):
        node = minidom.Element('inFilter')
        xml_node = self.xml_node()
        node.appendChild(self.xml_node())
        return node

    def xml_node(self):
        visitor = XmlGeneratorVisitor()
        return self.visit(visitor)

    def _raise_type_mismatch(self, obj):
        raise UcsmTypeMismatchError("Expected UcsmPropertyFilter or\
        UcsmComposeFilter, got object %s" % repr(obj))

    def visit(self, visitor):
        return visitor.visit_op(self)


class UcsmConnection(object):
    __ENDPOINT = '/nuova'

    def __init__(self, host, port=None, secure=False, *args, **kwargs):
        self.__cookie = None
        self.__login = None
        self.__password = None
        self.__refresh_timer = None
        self.host = host
        if port:
            self.port = port
        else:
            self.port = secure and 443 or 80
        self.version = None
        self.session_id = None
        self.secure = secure
        if secure:
            self._create_connection = lambda:\
            httplib.HTTPSConnection(self.host, self.port, *args, **kwargs)
        else:
            self._create_connection = lambda:\
            httplib.HTTPConnection(self.host, self.port, *args, **kwargs)

    def login(self, login, password, cookie_timeout=60 * 10):
        """Performs authorisation and retrieving cookie from server.
Cookie refresh will be performed automatically."""
        self.__cookie = None
        self.__login = None
        self.__password = None
        self.version = None
        self.session_id = None
        try:
            body = self._instantiate_simple_query('aaaLogin', inName=login,
                                                  inPassword=password)
            reply_xml, conn = self._perform_xml_call(body)
            self._check_is_error(reply_xml.firstChild)
            response_atom = reply_xml.firstChild
            self._get_cookie_from_xml(response_atom)
            self.version = response_atom.attributes["outVersion"].value
            self.session_id = response_atom.attributes["outSessionId"].value
            self.__login = login
            self.__password = password
            self.cookie_timeout = cookie_timeout
            self._start_autorefresh()
            return self.__cookie
        except KeyError:
            raise UcsmFatalError("Wrong reply syntax.")
        except UcsmFatalError, e:
            raise UcsmFatalError(str(e))

    def set_auth(self, cookie, login=None, password=None):
        self.__cookie = cookie
        self.__login = login
        self.__password = password

    def logout(self):
        try:
            if self.__refresh_timer:
                self.__refresh_timer.cancel()
            cookie = self.__cookie
            body = self._instantiate_simple_query('aaaLogout', inCookie=cookie)
            reply_xml, conn = self._perform_xml_call(body)
            self._check_is_error(reply_xml.firstChild)
            response_atom = reply_xml.firstChild
            if response_atom.attributes["response"].value == "yes":
                self._check_is_error(response_atom)
                status = response_atom.attributes["outStatus"].value
                self.session_id = None
                self.version = None
                return status
            else:
                raise UcsmFatalError()
        except KeyError:
            raise UcsmFatalError("Wrong reply syntax.")
        except UcsmFatalError, e:
            raise UcsmFatalError(str(e))

    def is_logged_in(self):
        return self.__cookie is not None

    def refresh(self):
        """Performs authorisation and retrieving cookie from server.
Cookie refresh will be performed automatically."""
        try:
            login = self.__login
            password = self.__password
            cookie = self.__cookie
            body = self._instantiate_simple_query('aaaRefresh', inName=login,
                                                  inPassword=password,
                                                  inCookie=cookie)
            reply_xml, conn = self._perform_xml_call(body)
            self._check_is_error(reply_xml.firstChild)
            response_atom = reply_xml.firstChild
            return self._get_cookie_from_xml(response_atom)
        except KeyError:
            raise UcsmFatalError("Wrong reply syntax.")

    def _get_single_object_from_response(self, data):
        try:
            out_config = data.getElementsByTagName('outConfig')[0]
            xml_childs = [child for child in out_config.childNodes
                          if child.nodeType == dom.Node.ELEMENT_NODE]
            childs = map(lambda c: UcsmObject(c), xml_childs)
            if len(childs):
                return childs[0]
            else:
                return None
        except (KeyError, IndexError):
            raise UcsmFatalError('No outConfig section in server response!')

    def _get_objects_from_response(self, data):
        try:
            out_config = data.getElementsByTagName('outConfigs')[0]
            return self._get_child_nodes_as_children(out_config)
        except (KeyError, IndexError):
            raise UcsmFatalError('No outConfig section in server response!')

    def _get_pairs_from_response(self, xml_data):
        buf_res = self._get_objects_from_response(xml_data)
        res = {}
        try:
            for pair in buf_res:
                if pair.ucs_class == 'pair':
                    res[pair.key] = pair.children[0]
                else:
                    raise UcsmFatalError('Wrong reply: non-pair object'
                                         'in outConfigs section')
            return res
        except IndexError:
            raise UcsmFatalError('Wrong reply: recieved pair'
                                 'does not contains value')
        except AttributeError:
            raise UcsmFatalError('Wrong reply: recieved pair'
                                 'does not have key')

    def _get_child_nodes_as_children(self, root):
        xml_childs = [child for child in root.childNodes\
                      if child.nodeType == dom.Node.ELEMENT_NODE]
        return map(lambda c: UcsmObject(c), xml_childs)

    def _get_unresolved_from_response(self, data):
        try:
            out_config = data.getElementsByTagName('outUnresolved')[0]
            xml_childs = [child for child in out_config.childNodes
                          if child.nodeType == dom.Node.ELEMENT_NODE
            and child.nodeName == 'dn']
            return map(lambda c: c.attributes['value'].value.encode('utf8'),
                       xml_childs)
        except (KeyError, IndentationError):
            raise UcsmFatalError('No outUnresolved section'
                                 'in server response!')

    def resolve_children(self, class_id='', dn='', hierarchy=False,
                         filter=UcsmFilterOp()):
        """Returns list of objects.
        """
        kwargs = {}
        if class_id:
            kwargs['classId'] = class_id
        data, conn = self._perform_query('configResolveChildren',
                                         filter=filter,
                                         cookie=self.__cookie,
                                         inDn=dn,
                                         inHierarchical=hierarchy and "yes"
                                         or "no",
                                         **kwargs)
        self._check_is_error(data.firstChild)
        return self._get_objects_from_response(data)

    # TODO: unexpected behavior with recursive option
    def scope(self, class_id, dn, filter=UcsmFilterOp(), hierarchy=False,
              recursive=False):
        data, conn = self._perform_query('configScope',
                                         filter=filter,
                                         cookie=self.__cookie,
                                         dn=dn,
                                         inClass=class_id,
                                         inRecursive=recursive and "yes"
                                                               or "no",
                                         inHierarchical=hierarchy and "yes"
                                                                  or "no")
        self._check_is_error(data.firstChild)
        return self._get_objects_from_response(data)

    def resolve_class(self, class_id, filter=UcsmFilterOp(), hierarchy=False):
        data, conn = self._perform_query('configResolveClass',
                                         filter=filter,
                                         cookie=self.__cookie,
                                         classId=class_id,
                                         inHierarchical=hierarchy and "yes"
                                         or "no")
        self._check_is_error(data.firstChild)
        return self._get_objects_from_response(data)

    def resolve_classes(self, classes, hierarchy=False):
        classes_node = minidom.Element('inIds')
        for cls in classes:
            childnode = minidom.Element('id')
            childnode.setAttribute('value', cls)
            classes_node.appendChild(childnode)
        data, conn = self._perform_complex_query('configResolveClasses',
                                                 data=classes_node,
                                                 cookie=self.__cookie,
                                                 inHierarchical=hierarchy
                                                                and "yes"
                                                 or "no")
        self._check_is_error(data.firstChild)
        return self._get_objects_from_response(data)

    def resolve_dn(self, dn, hierarchy=False):
        data, conn = self._perform_query('configResolveDn',
                                         cookie=self.__cookie,
                                         dn=dn,
                                         inHierarchical=hierarchy and "yes"
                                                                  or "no")
        self._check_is_error(data.firstChild)
        res = self._get_single_object_from_response(data)
        if res:
            return res
        else:
            return None

    def resolve_dns(self, dns, hierarchy=False):
        """Returns tuple contains list of resolved objects and list
of unresolved dns."""
        dns_node = minidom.Element('inDns')
        for dn in dns:
            childnode = minidom.Element('dn')
            childnode.setAttribute('value', dn)
            dns_node.appendChild(childnode)
        data, conn = self._perform_complex_query('configResolveDns',
                                                 data=dns_node,
                                                 cookie=self.__cookie,
                                                 inHierarchical=hierarchy
                                                                and "yes"
                                                                or "no")
        self._check_is_error(data.firstChild)
        resolved = self._get_objects_from_response(data)
        unresolved = self._get_unresolved_from_response(data)
        return resolved, unresolved

    def find_dns_by_class_id(self, class_id, filter=None):
        data, conn = self._perform_query('configFindDnsByClassId',
                                         filter=filter,
                                         cookie=self.__cookie,
                                         classId=class_id)
        self._check_is_error(data.firstChild)
        try:
            out_dns_node = data.getElementsByTagName('outDns')[0]
            dns = [child.attributes['value'].value.encode('utf8') for child in
                   out_dns_node.childNodes
                   if child.nodeType == dom.Node.ELEMENT_NODE]
            return dns
        except (IndexError, KeyError):
            raise UcsmFatalError('No outDns section in server response!')

    def resolve_parent(self, dn, hierarchy=False):
        data, conn = self._perform_query('configResolveParent',
                                         cookie=self.__cookie,
                                         dn=dn,
                                         inHierarchical=hierarchy and "yes"
                                                                  or "no")
        self._check_is_error(data.firstChild)
        res = self._get_single_object_from_response(data)
        return res

    def _conf_mo_status(self, config, status, dn='', hierarchy=False):
        """Side-effect eraser.
        """
        oldattr = None
        if 'status' in config.attributes and status not in config.status:
            oldattr = config.status
            config.status = status
        res = self.conf_mo(config, dn, hierarchy)
        if oldattr is not None:
            config.status = oldattr
        return res

    def create_object(self, conf, root=None, rn=None, dn=None,
                      hierarchy=False):
        """When creates, overrides only not given attributes rn, dn, status.
        Priorities:
        - dn
        - root + rn
        - root + conf.rn
        - conf.dn
        """
        if dn is not None:
            conf.dn = dn
        elif root is not None:
            if rn is not None:
                conf.dn = os.path.join(root, rn)
                conf.rn = rn
            elif 'rn' in conf.attributes:
                conf.dn = os.path.join(root, conf.rn)
        return self._conf_mo_status(conf, 'created', hierarchy=hierarchy)

    def delete_object(self, conf):
        obj = UcsmObject(conf.ucs_class)
        obj.dn = conf.dn
        obj.status = 'deleted'
        return self.conf_mo(obj)

    def update_object(self, conf, hierarchy=False):
        return self._conf_mo_status(conf, 'modified', hierarchy=hierarchy)

    def conf_mo(self, config, dn="", hierarchy=False):
        """Modifies or creates config. Special config object attribute 'status'
is used to determines action. Possible values:
('created', 'deleted', 'modified')."""
        in_config_node = minidom.Element('inConfig')
        in_config_node.appendChild(config.xml_node(hierarchy))
        data, conn = self._perform_complex_query('configConfMo',
                                                 data=in_config_node,
                                                 dn=dn,
                                                 cookie=self.__cookie,
                                                 inHierarchical=hierarchy
                                                                and "yes"
                                                                or "no")
        self._check_is_error(data.firstChild)
        res = self._get_single_object_from_response(data)
        return res

    def conf_mos(self, configs, hierarchy=False):
        """Gets dictionary of dn:config as configs argument. Equivalent for
several configConfMo requests. Returns dirtionary of dn:canged_config.
Special config object attribute 'status' is used to determines action.
Possible values: ('created', 'deleted', 'modified')."""
        configs_xml = minidom.Element('inConfigs')
        iteritems = configs
        if isinstance(configs, dict):
            iteritems = configs.iteritems()
        for k, c in iteritems:
            conf = minidom.Element('pair')
            conf.setAttribute('key', k)
            conf.appendChild(c.xml_node(hierarchy))
            configs_xml.appendChild(conf)
        data, conn = self._perform_complex_query('configConfMos',
                                                 cookie=self.__cookie,
                                                 data=configs_xml)
        self._check_is_error(data.firstChild)
        return self._get_pairs_from_response(data)

    def estimate_impact(self, configs):
        """Calculates impact of changing config on server.
Returns four lists: ackables, old ackables, affected and old affected
configs."""
        configs_xml = minidom.Element('inConfigs')
        for k, c in configs.items():
            conf = minidom.Element('pair')
            conf.setAttribute('key', k)
            conf.appendChild(c.xml_node())
            configs_xml.appendChild(conf)
        data, conn = self._perform_complex_query('configEstimateImpact',
                                                 cookie=self.__cookie,
                                                 data=configs_xml)
        self._check_is_error(data.firstChild)
        try:
            ackables = self._get_child_nodes_as_children(
                data.getElementsByTagName('outAckables')[0])
            old_ackables = self._get_child_nodes_as_children(
                data.getElementsByTagName('outOldAckables')[0])
            affected = self._get_child_nodes_as_children(
                data.getElementsByTagName('outAffected')[0])
            old_affected = self._get_child_nodes_as_children(
                data.getElementsByTagName('outOldAffected')[0])
            return ackables, old_ackables, affected, old_affected
        except KeyError:
            raise

    def conf_mo_group(self, dns, config, hierarchy=False):
        """Makes equivalent changes in several dns.
        """
        config_xml = minidom.Element('inConfig')
        config_xml.appendChild(config.xml_node())
        dns_xml = minidom.Element('inDns')
        for dn in dns:
            dn_xml = minidom.Element('dn')
            dn_xml.setAttribute('value', dn)
            dns_xml.appendChild(dn_xml)
        data, conn = self._perform_complex_query('configConfMoGroup',
                                                 cookie=self.__cookie,
                                                 data=[dns_xml, config_xml],
                                                 inHierarchical=hierarchy
                                                                and "yes"
                                                                or "no")
        self._check_is_error(data.firstChild)
        return self._get_objects_from_response(data)

    def clone_profile(self, dn, name, target_org_dn='org-root',
                      hierarchy=True):
        data, conn = self._perform_query('lsClone',
                                         cookie=self.__cookie,
                                         dn=dn,
                                         inTargetOrg=target_org_dn,
                                         inServerName=name,
                                         inHierarchical=hierarchy and "yes"
                                                                  or "no")
        self._check_is_error(data.firstChild)
        res = self._get_single_object_from_response(data)
        return res

    def instantiate_template(self, dn, name, target_org_dn='org-root',
                             hierarchy=False):
        """Returns created profile."""
        data, conn = self._perform_query('lsInstantiateTemplate',
                                         cookie=self.__cookie,
                                         dn=dn,
                                         inTargetOrg=target_org_dn,
                                         inServerName=name,
                                         inHierarchical=hierarchy and "yes"
                                                                  or "no")
        self._check_is_error(data.firstChild)
        res = self._get_single_object_from_response(data)
        return res

    def instantiate_n_template(self, dn, target_org_dn='org-root', prefix='',
                               number=1, hierarchy=False):
        data, conn = self._perform_query('lsInstantiateNTemplate',
                                         cookie=self.__cookie,
                                         dn=dn,
                                         inTargetOrg=target_org_dn,
                                         inServerNamePrefixOrEmpty=prefix,
                                         inNumberOf=number,
                                         inHierarchical=hierarchy and "yes"
                                                                  or "no")
        self._check_is_error(data.firstChild)
        return self._get_objects_from_response(data)

    def instantiate_n_template_named(self, dn, name_set,
                                     target_org_dn='org-root',
                                     hierarchy=True):
        """Creates profiles with given names."""
        inNames = minidom.Element('inNameSet')
        for name in name_set:
            name_elem = minidom.Element('dn')
            name_elem.setAttribute('value', name)
            inNames.appendChild(name_elem)
        data, conn = self._perform_complex_query('lsInstantiateNNamedTemplate',
                                                 inNames,
                                                 dn=dn,
                                                 cookie=self.__cookie,
                                                 inTargetOrg=target_org_dn,
                                                 inHierarchical=hierarchy
                                                                and "yes"
                                                                or "no")
        self._check_is_error(data.firstChild)
        return self._get_objects_from_response(data)

    def resolve_elements(self, dn, class_id, single_level=False,
                         hierarchy=False, filter=UcsmFilterOp()):
        """Recursively resolves all elements that org can work with"""
        data, conn = self._perform_query('orgResolveElements',
                                         filter=filter,
                                         dn=dn,
                                         cookie=self.__cookie,
                                         inClass=class_id,
                                         inSingleLevel=single_level
                                                       and "yes"
                                                       or "no",
                                         inHierarchical=hierarchy and "yes"
                                                                  or "no")
        self._check_is_error(data.firstChild)
        return self._get_pairs_from_response(data)

    def _refresh(self):
        LOG.debug('Refreshing cookie...')
        try:
            self.refresh()
        except Exception:
            LOG.warning('Exception during cookie refresh')
        else:
            self.__refresh_timer = self._recreate_refresh_timer()
            self.__refresh_timer.start()

    def _start_autorefresh(self):
        self.__refresh_timer = self._recreate_refresh_timer()
        self.__refresh_timer.start()

    def _recreate_refresh_timer(self):
        return Timer(min(self.refresh_period / 2, self.cookie_timeout),
                     self._refresh)

    def _check_is_error(self, response_atom):
        if response_atom.hasAttribute("errorCode"):
            error_code = int(response_atom.attributes["errorCode"].value)
            error_description = response_atom.attributes[
                                "errorDescr"].value.encode('utf8')
            raise UcsmResponseError(error_code, error_description)

    def _perform_xml_call(self, request_data, headers=None):
        conn = self._create_connection()
        body = request_data
        LOG.debug(">> %s", body)
        try:
            conn.request("POST", self.__ENDPOINT, body)
            reply = conn.getresponse()
            reply_data = reply.read()
        except socket.error, e:
            raise UcsmFatalError('Error during connecting: %s' % e)
        LOG.debug("<< %s", reply_data)
        try:
            reply_xml = minidom.parseString(reply_data)
        except:
            raise UcsmFatalError("Error during XML parsing.")
        return reply_xml, conn

    def iter_events(self, filter=UcsmFilterOp()):
        """Starts listen events, iterating through them.
Yields event id and configuraion."""
        for root_xml, conn in self._iter_xml_events(filter):
            for event_xml in root_xml.getElementsByTagName(
                'configMoChangeEvent'):
                event_id = int(event_xml.getAttribute('inEid'))
                configs = event_xml.getElementsByTagName('inConfig')
                if configs:
                    xml_childs = [child for child in configs[0].childNodes if
                                  child.nodeType == dom.Node.ELEMENT_NODE]
                    childs = map(lambda c: UcsmObject(c), xml_childs)
                    for child in childs:
                        yield event_id, child

    def _iter_xml_events(self, filter=UcsmFilterOp()):
        request_data = self._instantiate_complex_query('eventSubscribe',
                           child_data=filter.final_xml_node(),
                           cookie=self.__cookie)
        conn = self._create_connection()
        body = request_data
        LOG.debug(">> %s", body)
        try:
            conn.request("POST", self.__ENDPOINT, body)
            reply = conn.getresponse()
            while True:
                reply_data = self._read_event_from_reply(reply)
                LOG.debug("<<e %s" % reply_data)
                try:
                    reply_xml = minidom.parseString(reply_data)
                    yield reply_xml, conn
                except:
                    raise UcsmFatalError("Error during XML parsing.")
        except socket.error, e:
            raise UcsmFatalError('Error during connecting: %s' % e)
        except EOFError:
            return

    def _read_event_from_reply(self, reply):
        adapter = ReadlineAdapter(reply)
        length = int(adapter.readline())
        return adapter.read(length)

    def _get_cookie_from_xml(self, response_atom):
        if response_atom.attributes["response"].value == "yes":
            self._check_is_error(response_atom)
            self.refresh_period = float(
                response_atom.attributes["outRefreshPeriod"].value)
            self.__cookie = response_atom.attributes["outCookie"].value
            self.privileges = response_atom.attributes["outPriv"].value.split(
                ',')
            return self.__cookie
        else:
            raise UcsmFatalError()

    def _perform_query(self, method, filter=None, **kwargs):
        """Gets query method name and its parameters.
Filter must be an instance of class, derived from UcsmFilterToken."""
        if filter is None:
            body = self._instantiate_simple_query(method, **kwargs)
        else:
            body = self._instantiate_complex_query(method,
                       child_data=filter.final_xml_node(), **kwargs)
        data, conn = self._perform_xml_call(body)
        return data, conn

    def _perform_complex_query(self, method, data, filter=None, **kwargs):
        """Gets query method name and its parameters. Filter must be an
instance of class, derived from UcsmFilterToken. Data is a string for inner
xml body."""
        if filter is None:
            body = self._instantiate_complex_query(method, child_data=data,
                                                   **kwargs)
        else:
            body = self._instantiate_complex_query(method,
                       child_data=filter.final_xml_node() + '\n' + data,
                       **kwargs)
        data, conn = self._perform_xml_call(body)
        return data, conn

    def _instantiate_simple_query(self, method, **kwargs):
        query = minidom.Element(method)
        for key, value in kwargs.items():
            query.setAttribute(key, str(value))
        return query.toxml()

    def _instantiate_complex_query(self, method, child_data=None, **kwargs):
        """Formats query with some child nodes. Child data can be string or
list of strings."""
        if child_data is not None:
            query = minidom.Element(method)
            for key, value in kwargs.items():
                query.setAttribute(key, str(value))
            if _iterable(child_data):
                for child in child_data:
                    query.appendChild(child)
            else:
                query.appendChild(child_data)
            return query.toxml()
        else:
            return self._instantiate_simple_query(method, **kwargs)


class UcsmAttribute(object):
    """Describes class attribute. You can use >, >=, <, <=, ==, != operators
to create UCSM property filters. Also wildcard matching, all bits and any bits
operators are avaliable."""

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
        return UcsmPropertyFilter(self, UcsmPropertyFilter.GREATER_OR_EQUAL,
                                  other)

    def __lt__(self, other):
        return UcsmPropertyFilter(self, UcsmPropertyFilter.LESS_THAN, other)

    def __le__(self, other):
        return UcsmPropertyFilter(self, UcsmPropertyFilter.LESS_OR_EQUAL,
                                  other)

    def wildcard_match(self, wcard):
        return  UcsmPropertyFilter(self, UcsmPropertyFilter.WILDCARD, wcard)

    def any_bit(self, bits):
        bits_str = bits
        if isinstance(bits, list):
            bits_str = ','.join(str(bit) for bit in bits)
        return UcsmPropertyFilter(self, UcsmPropertyFilter.ANY_BIT, bits_str)

    def all_bit(self, bits):
        bits_str = bits
        if isinstance(bits, list):
            bits_str = ','.join(str(bit) for bit in bits)
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

    def visit(self, visitor):
        return visitor.visit_property(self)


class UcsmComposeFilter(UcsmFilterToken):
    AND = "and"
    OR = "or"
    NOT = "not"

    def __init__(self, operator, *args):
        self.operator = operator
        self.arguments = []
        for arg in args:
            if isinstance(arg,
                          self.__class__) and arg.operator == self.operator:
                self.arguments.extend(arg.arguments)
            else:
                self.arguments.append(arg)

    def visit(self, visitor):
        return visitor.visit_compose(self)


class UcsmObject(object):
    __slots__ = ['__init__', '__getattr__', '__setattr__', '__repr__', 'xml',
                 'xml_node', 'pretty_xml',
                 'children', 'attributes', 'parent', 'ucs_class',
                 'find_children', 'set_creation_status']

    def __init__(self, node_or_class=None, parent=None):
        self.children = []
        self.attributes = {}
        self.parent = parent
        if node_or_class is None:
            self.ucs_class = None
        elif isinstance(node_or_class, basestring):
            self.ucs_class = node_or_class
        elif isinstance(node_or_class, UcsmObject):
            self._fill_copy(node_or_class)
        else:
            if node_or_class.nodeType != dom.Node.ELEMENT_NODE:
                raise TypeError(
                    'UcsmObjects can be created only from XML element nodes.')
            self.children = []
            self.attributes = {}
            self.ucs_class = node_or_class.nodeName.encode('utf8')
            for attr, val in node_or_class.attributes.items():
                self.attributes[attr.encode('utf8')] = val.encode('utf8')
            if parent is not None\
               and'dn' not in self.attributes\
               and 'rn' in self.attributes\
            and 'dn' in parent.attributes:
                self.dn = os.path.join(parent.dn, self.rn)
            if node_or_class is not None:
                for child_node in node_or_class.childNodes:
                    if child_node.nodeType == dom.Node.ELEMENT_NODE:
                        child = UcsmObject(child_node, self)
                        self.children.append(child)

    def copy(self, parent=None):
        cpy = UcsmObject(str(self.ucs_class), parent=parent)
        cpy._fill_copy(self)
        return cpy

    def _fill_copy(self, src):
        for k, v in src.attributes.items():
            setattr(self, k, type(v)(v))
        for child in src.children:
            self.children.append(child.copy(self))

    def __getattr__(self, item):
        try:
            return self.attributes[item]
        except KeyError:
            raise AttributeError('UcsmObject has no attribute \'%s\'' % item)

    def __setattr__(self, key, value):
        if key in UcsmObject.__slots__:
            super(UcsmObject, self).__setattr__(key, value)
        else:
            self.attributes[key] = value

    def __repr__(self):
        repr = self.ucs_class
        if len(self.attributes):
            repr = repr + '; ' + ' '.join(
                '%s=%s' % (n, v) for n, v in self.attributes.items())
        return '<UcsmObject instance at %x with class %s>' % (id(self), repr)

    def xml(self, hierarchy=False):
        return self.xml_node(hierarchy).toxml()

    def xml_node(self, hierarchy=False):
        node = minidom.Element(self.ucs_class)
        for n, v in self.attributes.items():
            node.setAttribute(n, str(v))
        if hierarchy:
            for child in self.children:
                node.appendChild(child.xml_node(True))
        return node

    def pretty_str(self):
        str = self.ucs_class
        for name, val in self.attributes.items():
            str += '\n%s: %s' % (name, val)
        return str

    def find_children(self, cls=None):
        res = []
        res.extend(self.children)
        if cls is not None:
            pres = [child for child in res if child.ucs_class == cls]
            res = pres
        return res

    def set_creation_status(self, status):
        self.attributes['status'] = status
        for c in self.children:
            c.set_creation_status(status)

    def __eq__(self, other):
        if isinstance(other, self.__class__):
            return self.attributes == other.attributes\
                and self.ucs_class == other.ucs_class\
                and self.children == other.children
        else:
            return False


class UcsmFilterVisitor(object):
    """Base class for recursive operations with filter hierarchy."""

    def visit_op(self, node):
        raise NotImplementedError()

    def visit_property(self, node):
        raise NotImplementedError()

    def visit_compose(self, node):
        raise NotImplementedError()


class XmlGeneratorVisitor(UcsmFilterVisitor):
    """"Xmlizer through visitors."""

    def visit_op(self, node):
        xml_node = minidom.Text()
        xml_node.data = ''
        return xml_node

    def visit_property(self, node):
        xml_node = minidom.Element(node.operator)
        xml_node.setAttribute('class', node.attribute.class_)
        xml_node.setAttribute('property', node.attribute.name)
        xml_node.setAttribute('value', str(node.value))
        return xml_node

    def visit_compose(self, node):
        xml_node = minidom.Element(node.operator)
        for arg in node.arguments:
            xml_node.appendChild(arg.visit(self))
        return xml_node
