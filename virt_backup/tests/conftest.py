
import pytest
from helper.virt_backup import MockDomain, MockConn


@pytest.fixture
def fixture_build_mock_domain(mocker):
    return MockDomain(_conn=mocker.stub())


@pytest.fixture
def fixture_build_mock_libvirtconn():
    return MockConn()


@pytest.fixture
def fixture_build_mock_libvirtconn_filled(fixture_build_mock_libvirtconn):
    conn = fixture_build_mock_libvirtconn
    domain_names = ("a", "b", "vm-10", "matching", "matching2")
    conn._domains = [
        MockDomain(name=dom_name, _conn=conn) for dom_name in domain_names
    ]
    return conn
