import pytest
from virt_backup.backups import DomBackup, DomExtSnapshotCallbackRegistrer
from virt_backup.groups import BackupGroup
from helper.virt_backup import MockDomain, MockConn, build_completed_backups


@pytest.fixture
def build_mock_domain(mocker):
    return MockDomain(_conn=mocker.stub())


@pytest.fixture
def build_stopped_mock_domain(build_mock_domain):
    build_mock_domain.set_state(4, 1)
    return build_mock_domain


@pytest.fixture
def build_mock_libvirtconn():
    return MockConn()


@pytest.fixture
def build_mock_libvirtconn_filled(build_mock_libvirtconn):
    conn = build_mock_libvirtconn
    domain_names = ("a", "b", "vm-10", "matching", "matching2")
    conn._domains = [
        MockDomain(name=dom_name, _conn=conn, id=id)
        for id, dom_name in enumerate(domain_names)
    ]
    return conn


@pytest.fixture
def build_backup_directory(tmpdir):
    domain_names, backup_dates = build_completed_backups(str(tmpdir))
    return {
        "domain_names": domain_names,
        "backup_dates": backup_dates,
        "backup_dir": tmpdir,
    }


@pytest.fixture
def get_dombackup(build_mock_domain, build_mock_libvirtconn):
    callbacks_registrer = DomExtSnapshotCallbackRegistrer(build_mock_libvirtconn)
    return DomBackup(build_mock_domain, callbacks_registrer=callbacks_registrer)


@pytest.fixture
def get_uncompressed_dombackup(build_mock_domain, build_mock_libvirtconn):
    callbacks_registrer = DomExtSnapshotCallbackRegistrer(build_mock_libvirtconn)
    return DomBackup(
        dom=build_mock_domain,
        dev_disks=("vda",),
        packager="directory",
        callbacks_registrer=callbacks_registrer,
    )


@pytest.fixture
def get_compressed_dombackup(build_mock_domain, build_mock_libvirtconn):
    callbacks_registrer = DomExtSnapshotCallbackRegistrer(build_mock_libvirtconn)
    return DomBackup(
        dom=build_mock_domain,
        dev_disks=("vda",),
        packager="tar",
        packager_opts={"compression": "xz", "compression_lvl": 4},
        callbacks_registrer=callbacks_registrer,
    )


@pytest.fixture
def get_backup_group(build_mock_domain, build_mock_libvirtconn):
    callbacks_registrer = DomExtSnapshotCallbackRegistrer(build_mock_libvirtconn)
    return BackupGroup(
        build_mock_libvirtconn,
        domlst=((build_mock_domain, None),),
        callbacks_registrer=callbacks_registrer,
    )
