
import libvirt
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
            dom_xml = "".join(dom_xmlfile.readlines())
        return dom_xml

    def ID(self):
        return 1

    def name(self):
        return self._name

    def __init__(self, _conn, name="test", *args, **kwargs):
        self._conn = _conn
        self._name = name


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
