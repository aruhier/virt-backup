
import arrow
import datetime
import json
import pytest
import tarfile

import virt_backup
from virt_backup.backups import DomBackup
from virt_backup.domains import get_xml_block_of_disk
from virt_backup.exceptions import DiskNotFoundError
from helper.virt_backup import MockSnapshot


class TestDomBackup():
    def test_get_self_domain_disks(self, build_mock_domain):
        dombkup = DomBackup(dom=build_mock_domain)
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

    def test_get_disks_with_filter(self, build_mock_domain):
        dombkup = DomBackup(dom=build_mock_domain)
        expected_disks = {
            "vda": {
                "src": "/var/lib/libvirt/images/test-disk-1.qcow2",
                "type": "qcow2",
            },
        }

        assert dombkup._get_self_domain_disks("vda") == expected_disks

    def test_init_with_disk(self, build_mock_domain):
        dombkup = DomBackup(dom=build_mock_domain, dev_disks=("vda", ))

        expected_disks = {
            "vda": {
                "src": "/var/lib/libvirt/images/test-disk-1.qcow2",
                "type": "qcow2",
            },
        }
        assert dombkup.disks == expected_disks

    def test_add_disks(self, build_mock_domain):
        """
        Create a DomBackup with only one disk (vda) and test to add vdb
        """
        disks = {
            "vda": {
                "src": "/var/lib/libvirt/images/test-disk-1.qcow2",
                "type": "qcow2",
            },
        }
        dombkup = DomBackup(dom=build_mock_domain, _disks=disks)
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

    def test_add_not_existing_disk(self, build_mock_domain):
        """
        Create a DomBackup and test to add vdc
        """
        dombkup = DomBackup(dom=build_mock_domain)
        with pytest.raises(KeyError):
            dombkup.add_disks("vdc")

    def test_snapshot_and_save_date_logic_date(self, build_mock_domain,
                                               monkeypatch, tmpdir):
        """
        Create a DomBackup and test to add vdc
        """
        target_dir = tmpdir.mkdir("snapshot_and_save_date")

        pre_snap_date = arrow.now()
        snapshot_date, definition = self.take_snapshot_and_return_date(
            build_mock_domain, str(target_dir), monkeypatch
        )
        post_snap_date = arrow.now()

        assert snapshot_date >= pre_snap_date
        assert snapshot_date <= post_snap_date

    def test_snapshot_and_save_date_test_pending_info(self, build_mock_domain,
                                                      monkeypatch, tmpdir):
        """
        Create a DomBackup and test to add vdc
        """
        target_dir = tmpdir.mkdir("snapshot_and_save_date")
        snapshot_date, definition = self.take_snapshot_and_return_date(
            build_mock_domain, str(target_dir), monkeypatch
        )

        pending_info_path = target_dir.listdir()[0]
        pending_info = json.loads(pending_info_path.read())

        assert definition.items() <= pending_info.items()
        assert "snapshot" in pending_info["disks"]["vda"]
        assert "src" in pending_info["disks"]["vda"]

    def take_snapshot_and_return_date(self, mock_domain, target_dir,
                                      monkeypatch):
        dombkup = DomBackup(
            dom=mock_domain, dev_disks=("vda", ), target_dir=target_dir
        )
        monkeypatch.setattr(
            dombkup, "external_snapshot", lambda: MockSnapshot(name="test")
        )

        definition = dombkup.get_definition()
        return dombkup._snapshot_and_save_date(definition)

    def test_get_libvirt_snapshot_xml(self, build_mock_domain):
        dombkup = DomBackup(dom=build_mock_domain)
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

    def test_main_backup_name_format(self, build_mock_domain):
        dombkup = DomBackup(dom=build_mock_domain)
        snapdate = datetime.datetime(2016, 8, 15, 17, 10, 13, 0)

        expected_name = "20160815-171013_1_test"
        assert dombkup._main_backup_name_format(snapdate) == expected_name

    def test_disk_backup_name_format(self, build_mock_domain):
        dombkup = DomBackup(dom=build_mock_domain)
        snapdate = datetime.datetime(2016, 8, 15, 17, 10, 13, 0)

        backup_name = dombkup._disk_backup_name_format(snapdate, "vda")
        expected_name = "20160815-171013_1_test_vda"
        assert backup_name == expected_name

    def test_get_new_tar(self, build_mock_domain, tmpdir, compression="tar"):
        dombkup = DomBackup(
            dom=build_mock_domain, compression=compression
        )
        snapdate = datetime.datetime(2016, 8, 15, 17, 10, 13, 0)

        target_dir = tmpdir.join("get_new_tar")

        if compression == "tar":
            extension = "tar"
        else:
            extension = "tar.{}".format(compression)
        tar_path = target_dir.join(
            "{}.{}".format(
                dombkup._main_backup_name_format(snapdate), extension
            )
        )
        with dombkup.get_new_tar(str(target_dir), snapshot_date=snapdate):
            assert tar_path.check()

    def test_get_new_tar_xz(self, build_mock_domain, tmpdir):
        return self.test_get_new_tar(
            build_mock_domain, tmpdir, compression="xz"
        )

    def test_get_new_tar_already_exists(self, build_mock_domain, tmpdir):
        dombkup = DomBackup(
            dom=build_mock_domain, compression="tar"
        )

        snapdate = datetime.datetime(2016, 8, 15, 17, 10, 13, 0)
        tar_path = tmpdir.join(
            "{}.tar".format(dombkup._main_backup_name_format(snapdate))
        )
        tar_path.write("test")

        with pytest.raises(FileExistsError):
            dombkup.get_new_tar(str(tmpdir), snapshot_date=snapdate)

    def test_get_new_tar_unvalid_compression(self, build_mock_domain, tmpdir):
        with pytest.raises(tarfile.CompressionError):
            return self.test_get_new_tar(
                build_mock_domain, tmpdir, compression="test"
            )

    def test_get_definition(self, build_mock_domain):
        dombkup = DomBackup(
            dom=build_mock_domain, dev_disks=("vda", ),
            compression="xz", compression_lvl=4
        )

        expected_def = {
            "compression": "xz", "compression_lvl": 4,
            "domain_id": build_mock_domain.ID(),
            "domain_name": build_mock_domain.name(),
            "domain_xml": build_mock_domain.XMLDesc(),
            "version": virt_backup.VERSION
        }
        assert dombkup.get_definition() == expected_def

    def test_manually_pivot_disk(self, build_mock_domain,
                                 build_mock_libvirtconn):
        conn = build_mock_libvirtconn
        dombkup = DomBackup(dom=build_mock_domain, conn=conn)

        dombkup._manually_pivot_disk("vda", "/testvda")
        dom_xml = dombkup.dom.XMLDesc()
        assert self.get_src_for_disk(dom_xml, "vda") == "/testvda"

    def test_manually_pivot_disk_libvirt_2(self, build_mock_domain,
                                           build_mock_libvirtconn):
        """
        Test manual pivot with libvirt < 3.0
        """
        conn = build_mock_libvirtconn
        conn._libvirt_version = 2000000
        conn._domains.append(build_mock_domain)

        return self.test_manually_pivot_disk(build_mock_domain, conn)

    def test_manually_pivot_unexistant_disk(self, build_mock_domain,
                                            build_mock_libvirtconn):
        conn = build_mock_libvirtconn
        dombkup = DomBackup(dom=build_mock_domain, conn=conn)

        with pytest.raises(DiskNotFoundError):
            dombkup._manually_pivot_disk("sda", "/testvda")

    def get_src_for_disk(self, dom_xml, disk):
        elem = get_xml_block_of_disk(dom_xml, disk)
        return elem.xpath("source")[0].get("file")

    def test_dump_json_definition(self, build_mock_domain, tmpdir):
        target_dir = tmpdir.mkdir("json_dump")
        dombkup = DomBackup(
            dom=build_mock_domain, dev_disks=("vda", ),
            compression="xz", compression_lvl=4, target_dir=str(target_dir),
        )

        definition = dombkup.get_definition()
        datenow = datetime.datetime.now()
        definition["date"] = datenow.timestamp()

        dombkup._dump_json_definition(definition)
        assert len(target_dir.listdir()) == 1
        assert json.loads(target_dir.listdir()[0].read()) == definition

    def test_clean_pending_info(self, build_mock_domain, tmpdir):
        target_dir = tmpdir.mkdir("clean_pending_info")
        dombkup = DomBackup(dom=build_mock_domain, target_dir=str(target_dir))
        dombkup._pending_info["date"] = 0

        dombkup._dump_pending_info()
        assert len(target_dir.listdir()) == 1
        dombkup._clean_pending_info()
        assert len(target_dir.listdir()) == 0

    def test_clean_aborted(self, build_mock_domain, tmpdir, monkeypatch):
        target_dir = tmpdir.mkdir("clean_aborted")
        dombkup = self.prepare_clean_aborted_dombkup(
            build_mock_domain, target_dir, monkeypatch
        )

        target_dir.join("vda.qcow2").write("")
        dombkup._pending_info["disks"] = {
            "vda": {
                "src": "vda.qcow2", "target": "vda.qcow2",
                "snapshot": "vda.snap"
            },
        }
        dombkup._dump_pending_info()
        assert len(target_dir.listdir()) == 2

        dombkup.clean_aborted()
        assert not target_dir.listdir()

    def test_clean_aborted_tar(self, build_mock_domain, tmpdir, monkeypatch):
        target_dir = tmpdir.mkdir("clean_aborted_tar")
        dombkup = self.prepare_clean_aborted_dombkup(
            build_mock_domain, target_dir, monkeypatch
        )
        dombkup.compression = "tar"

        target_dir.join("backup.tar").write("")
        dombkup._pending_info["tar"] = "backup.tar"
        dombkup._dump_pending_info()
        assert len(target_dir.listdir()) == 2

        dombkup.clean_aborted()
        assert not target_dir.listdir()

    def prepare_clean_aborted_dombkup(self, mock_domain, target_dir,
                                      monkeypatch):
        def mock_post_backup_cleaning_snapshot(*args, **kwargs):
            return None

        dombkup = DomBackup(dom=mock_domain, target_dir=str(target_dir))
        dombkup._pending_info["date"] = 0

        # TODO: will have to check if pivot is triggered, and temp snapshot
        #       deleted
        monkeypatch.setattr(
            dombkup, "post_backup_cleaning_snapshot",
            mock_post_backup_cleaning_snapshot
        )

        return dombkup

    def test_compatible_with(self, get_uncompressed_dombackup,
                             build_mock_domain):
        dombackup1 = get_uncompressed_dombackup
        dombackup2 = DomBackup(
            dom=build_mock_domain, dev_disks=("vdb", ), compression=None,
        )

        assert dombackup1.compatible_with(dombackup2)

    def test_not_compatible_with(self, get_uncompressed_dombackup,
                                 build_mock_domain):
        dombackup1 = get_uncompressed_dombackup
        dombackup1.target_dir = "/tmp/test"
        dombackup2 = DomBackup(
            dom=build_mock_domain, dev_disks=("vdb", ), compression=None,
        )

        assert not dombackup1.compatible_with(dombackup2)
