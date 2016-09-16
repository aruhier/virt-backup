
import datetime
import json
import pytest
import tarfile

from virt_backup.virt_backup import DomBackup


def test_get_disks(fixture_build_mock_domain):
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

    assert dombkup._get_disks() == expected_disks


def test_get_disks_with_filter(fixture_build_mock_domain):
    dombkup = DomBackup(dom=fixture_build_mock_domain)
    expected_disks = {
        "vda": {
            "src": "/var/lib/libvirt/images/test-disk-1.qcow2",
            "type": "qcow2",
        },
    }

    assert dombkup._get_disks("vda") == expected_disks


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


def test_get_snapshot_xml(fixture_build_mock_domain):
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
    assert dombkup.gen_snapshot_xml() == expected_xml


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
        "disks": ("vda", ), "compression": "xz", "compression_lvl": 4,
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
    # converts disks to list as json doesn't know tuples
    definition["disks"] = list(definition["disks"])

    dombkup._dump_json_definition(definition)
    assert len(target_dir.listdir()) == 1
    assert json.loads(target_dir.listdir()[0].read()) == definition
