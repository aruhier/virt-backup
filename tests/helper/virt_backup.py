
import defusedxml.lxml
import libvirt
import lxml
import os


CUR_PATH = os.path.dirname(os.path.realpath(__file__))


class MockDomain():
    """
    Simulate a libvirt domain
    """
    def XMLDesc(self):
        """
        Return the definition of a testing domain
        """
        with open(os.path.join(CUR_PATH, "testdomain.xml")) as dom_xmlfile:
            dom_xml_str = dom_xmlfile.read()
        dom_xml = defusedxml.lxml.fromstring(dom_xml_str)
        dom_xml.set("id", str(self._id))
        elem_name = dom_xml.xpath("name")[0]
        if not elem_name:
            elem_name = dom_xml.makeelement("name")
            dom_xml.insert(0, elem_name)
        elem_name.text = self._name
        return lxml.etree.tostring(dom_xml, pretty_print=True).decode()

    def ID(self):
        return self._id

    def name(self):
        return self._name

    def __init__(self, _conn, name="test", id=1, *args, **kwargs):
        self._conn = _conn
        self._name = name
        self._id = id


class MockConn():
    """
    Simulate a libvirt connection
    """
    def listAllDomains(self):
        return self._domains

    def lookupByName(self, name):
        for d in self._domains:
            if d.name() == name:
                return d
        raise libvirt.libvirtError("Domain not found")

    def __init__(self, _domains=None, *args, **kwargs):
        self._domains = _domains or []
