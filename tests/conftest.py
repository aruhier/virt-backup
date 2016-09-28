
import pytest
from helper.virt_backup import MockDomain, MockConn, build_completed_backups


@pytest.fixture
def build_mock_domain(mocker):
    return MockDomain(_conn=mocker.stub())


@pytest.fixture
def build_mock_libvirtconn():
    return MockConn()


@pytest.fixture
def build_mock_libvirtconn_filled(build_mock_libvirtconn):
    conn = build_mock_libvirtconn
    domain_names = ("a", "b", "vm-10", "matching", "matching2")
    conn._domains = [
        MockDomain(name=dom_name, _conn=conn) for dom_name in domain_names
    ]
    return conn


@pytest.fixture
def build_backup_directory(tmpdir):
    domain_names, backup_dates = build_completed_backups(str(tmpdir))
    return {
        "domain_names": domain_names, "backup_dates": backup_dates,
        "backup_dir": tmpdir
    }
