
import datetime
import json
import os
import pytest
import tarfile

from virt_backup.domain import (
    DomBackup, search_domains_regex, list_backups_by_domain,
    get_complete_backup_from_def
)

from helper.virt_backup import MockDomain


@pytest.fixture
def fixture_build_bak_definition_with_compression(fixture_build_mock_domain):
    dombkup = DomBackup(
        dom=fixture_build_mock_domain, dev_disks=("vda", ), compression="xz",
        compression_lvl=4,
    )

    definition = dombkup.get_definition()
    datenow = datetime.datetime.now()
    definition["date"] = datenow.timestamp()

    return definition


def test_get_self_domain_disks(fixture_build_mock_domain):
    dombkup = DomBackup(dom=fixture_build_mock_domain)
    expected_disks = {
        "vda": {
            "src": "/var/lib/libvirt/images/test-disk-1.qcow2",
            "type": "qcow2",
        },
        "vdb": {
            "src": "/var/lib/libvirt/images/test-disk-2.qcow2",
            "type": "qcow2",
        }
    }

    assert dombkup._get_self_domain_disks() == expected_disks


def test_get_disks_with_filter(fixture_build_mock_domain):
    dombkup = DomBackup(dom=fixture_build_mock_domain)
    expected_disks = {
        "vda": {
            "src": "/var/lib/libvirt/images/test-disk-1.qcow2",
            "type": "qcow2",
        },
    }

    assert dombkup._get_self_domain_disks("vda") == expected_disks


def test_init_with_disk(fixture_build_mock_domain):
    dombkup = DomBackup(dom=fixture_build_mock_domain, dev_disks=("vda", ))

    expected_disks = {
        "vda": {
            "src": "/var/lib/libvirt/images/test-disk-1.qcow2",
            "type": "qcow2",
        },
    }
    assert dombkup.disks == expected_disks


def test_add_disks(fixture_build_mock_domain):
    """
    Create a DomBackup with only one disk (vda) and test to add vdb
    """
    disks = {
        "vda": {
            "src": "/var/lib/libvirt/images/test-disk-1.qcow2",
            "type": "qcow2",
        },
    }
    dombkup = DomBackup(dom=fixture_build_mock_domain, _disks=disks)
    expected_disks = {
        "vda": {
            "src": "/var/lib/libvirt/images/test-disk-1.qcow2",
            "type": "qcow2",
        },
    }
    assert dombkup.disks == expected_disks

    dombkup.add_disks("vdb")
    expected_disks = {
        "vda": {
            "src": "/var/lib/libvirt/images/test-disk-1.qcow2",
            "type": "qcow2",
        },
        "vdb": {
            "src": "/var/lib/libvirt/images/test-disk-2.qcow2",
            "type": "qcow2",
        }
    }
    assert dombkup.disks == expected_disks


def test_add_not_existing_disk(fixture_build_mock_domain):
    """
    Create a DomBackup and test to add vdc
    """
    dombkup = DomBackup(dom=fixture_build_mock_domain)
    with pytest.raises(KeyError):
        dombkup.add_disks("vdc")


def test_get_libvirt_snapshot_xml(fixture_build_mock_domain):
    dombkup = DomBackup(dom=fixture_build_mock_domain)
    expected_xml = (
        "<domainsnapshot>\n"
        "  <description>Pre-backup external snapshot</description>\n"
        "  <disks>\n"
        "    <disk name=\"vda\" snapshot=\"external\"/>\n"
        "    <disk name=\"vdb\" snapshot=\"external\"/>\n"
        "  </disks>\n"
        "</domainsnapshot>\n"
    )
    assert dombkup.gen_libvirt_snapshot_xml() == expected_xml


def test_main_backup_name_format(fixture_build_mock_domain):
    dombkup = DomBackup(dom=fixture_build_mock_domain)
    snapdate = datetime.datetime(2016, 8, 15, 17, 10, 13, 0)

    expected_name = "20160815-171013_1_test"
    assert dombkup._main_backup_name_format(snapdate) == expected_name


def test_disk_backup_name_format(fixture_build_mock_domain):
    dombkup = DomBackup(dom=fixture_build_mock_domain)
    snapdate = datetime.datetime(2016, 8, 15, 17, 10, 13, 0)

    expected_name = "20160815-171013_1_test_vda"
    assert dombkup._disk_backup_name_format(snapdate, "vda") == expected_name


def test_get_new_tar(fixture_build_mock_domain, tmpdir, compression="tar"):
    dombkup = DomBackup(dom=fixture_build_mock_domain, compression=compression)
    snapdate = datetime.datetime(2016, 8, 15, 17, 10, 13, 0)

    target_dir = tmpdir.mkdir("get_new_tar")

    if compression == "tar":
        extension = "tar"
    else:
        extension = "tar.{}".format(compression)
    tar_path = target_dir.join(
        "{}.{}".format(dombkup._main_backup_name_format(snapdate), extension)
    )
    with dombkup.get_new_tar(str(target_dir), snapshot_date=snapdate):
        assert tar_path.check()


def test_get_new_tar_xz(fixture_build_mock_domain, tmpdir):
    return test_get_new_tar(
        fixture_build_mock_domain, tmpdir, compression="xz"
    )


def test_get_new_tar_unvalid_compression(fixture_build_mock_domain, tmpdir):
    with pytest.raises(tarfile.CompressionError):
        return test_get_new_tar(
            fixture_build_mock_domain, tmpdir, compression="test"
        )


def test_get_definition(fixture_build_mock_domain):
    dombkup = DomBackup(
        dom=fixture_build_mock_domain, dev_disks=("vda", ), compression="xz",
        compression_lvl=4
    )

    expected_def = {
        "compression": "xz", "compression_lvl": 4,
        "domain_id": fixture_build_mock_domain.ID(),
        "domain_name": fixture_build_mock_domain.name(),
        "domain_xml": fixture_build_mock_domain.XMLDesc()
    }
    assert dombkup.get_definition() == expected_def


def test_dump_json_definition(fixture_build_mock_domain, tmpdir):
    target_dir = tmpdir.mkdir("json_dump")
    dombkup = DomBackup(
        dom=fixture_build_mock_domain, dev_disks=("vda", ), compression="xz",
        compression_lvl=4, target_dir=str(target_dir),
    )

    definition = dombkup.get_definition()
    datenow = datetime.datetime.now()
    definition["date"] = datenow.timestamp()

    dombkup._dump_json_definition(definition)
    assert len(target_dir.listdir()) == 1
    assert json.loads(target_dir.listdir()[0].read()) == definition


def test_search_domains_regex(fixture_build_mock_libvirtconn):
    conn = fixture_build_mock_libvirtconn
    domain_names = ("dom1", "dom2", "dom3", "test")
    conn._domains = [
        MockDomain(name=dom_name, _conn=conn) for dom_name in domain_names
    ]

    matches = list(sorted(search_domains_regex("^dom\d$", conn)))
    expected = list(sorted(domain_names))
    expected.remove("test")

    assert matches == expected


def test_search_domains_regex_not_found(
        fixture_build_mock_libvirtconn, fixture_build_mock_domain):
    """
    Search a non existing domain
    """
    conn = fixture_build_mock_libvirtconn
    conn._domains = [fixture_build_mock_domain]

    matches = list(search_domains_regex("^dom$", conn))
    assert matches == []


def test_list_backups_by_domain(fixture_build_backup_directory):
    """
    Search a non existing domain
    """
    backup_dir = str(fixture_build_backup_directory["backup_dir"])
    backup_dates = tuple(fixture_build_backup_directory["backup_dates"])
    domain_names = fixture_build_backup_directory["domain_names"]

    backups = list_backups_by_domain(str(backup_dir))
    assert sorted(backups.keys()) == sorted(domain_names)

    def expected_backups(domain_id, domain_name):
        for backup_date in backup_dates:
            str_backup_date = backup_date.strftime("%Y%m%d-%H%M%S")
            json_filename = "{}_{}_{}.json".format(
                str_backup_date, domain_id, domain_name
            )
            json_path = os.path.join(backup_dir, domain_name, json_filename)

            assert os.path.isfile(json_path)
            with open(json_path, "r") as json_file:
                yield (json_path, json.load(json_file))

    for domain_id, domain_name in enumerate(domain_names):
        assert (
            sorted(expected_backups(domain_id, domain_name)) ==
            sorted(backups[domain_name])
        )


def test_get_complete_backup_from_def(
        fixture_build_bak_definition_with_compression):
    definition = fixture_build_bak_definition_with_compression
    complete_backup = get_complete_backup_from_def(definition)

    assert complete_backup.dom_xml == definition["domain_xml"]
