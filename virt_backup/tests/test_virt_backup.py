
import os
import pytest

from virt_backup.virt_backup import DomBackup


CUR_PATH = os.path.dirname(os.path.realpath(__file__))


class MockDomain():
    """
    Simulate a libvirt domain
    """
    def XMLDesc(self):
        """
        Return the definition of a testing domain
        """
        with open(os.join(CUR_PATH, "testdomain.xml")) as dom_xmlfile:
            dom_xml = "".join(dom_xmlfile.readlines())
        return dom_xml

    def __init__(self, _conn, *args, **kwargs):
        self._conn = _conn


@pytest.fixture
def fixture_build_mock_domain(mocker):
    return MockDomain(_conn=mocker.stub())


def test_get_disks(fixture_build_mock_domain):
    dombkup = DomBackup(dom=fixture_build_mock_domain)
    expected_disks = ("vda", "vdb")

    dombkup._get_disks == expected_disks
