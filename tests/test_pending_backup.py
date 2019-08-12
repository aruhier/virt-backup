import tarfile
import datetime
import json
import pytest

import virt_backup
from virt_backup.backups import DomBackup
from virt_backup.backups.snapshot import (
    DomExtSnapshot, DomExtSnapshotCallbackRegistrer
)
from helper.virt_backup import MockSnapshot, build_dombackup


class TestDomBackup():
    def test_get_self_domain_disks(self, get_dombackup):
        dombkup = get_dombackup
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

    def test_get_disks_with_filter(self, get_dombackup):
        dombkup = get_dombackup
        expected_disks = {
            "vda": {
                "src": "/var/lib/libvirt/images/test-disk-1.qcow2",
                "type": "qcow2",
            },
        }

        assert dombkup._get_self_domain_disks("vda") == expected_disks

    def test_init_with_disk(self, build_mock_domain):
        dombkup = build_dombackup(build_mock_domain, dev_disks=("vda", ))

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
        dombkup = build_dombackup(build_mock_domain, disks=("vda", ))
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

    def test_add_not_existing_disk(self, get_dombackup):
        """
        Create a DomBackup and test to add vdc
        """
        dombkup = get_dombackup
        with pytest.raises(KeyError):
            dombkup.add_disks("vdc")

    def test_snapshot_and_save_date_test_pending_info(self, build_mock_domain,
                                                      monkeypatch, tmpdir):
        """
        Create a DomBackup, snapshot, then tests if dumped pending info are
        correct
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
        dombkup = build_dombackup(
            dom=mock_domain, dev_disks=("vda", ), target_dir=target_dir
        )

        snapshot_helper = DomExtSnapshot(
            dombkup.dom, dombkup.disks,
            DomExtSnapshotCallbackRegistrer(dombkup.conn), dombkup.conn,
            dombkup.timeout,

        )
        monkeypatch.setattr(
            snapshot_helper, "external_snapshot",
            lambda: MockSnapshot(name="test")
        )
        dombkup._ext_snapshot_helper = snapshot_helper

        definition = dombkup.get_definition()
        return dombkup._snapshot_and_save_date(definition)

    def test_main_backup_name_format(self, get_dombackup):
        dombkup = get_dombackup
        snapdate = datetime.datetime(2016, 8, 15, 17, 10, 13, 0)

        expected_name = "20160815-171013_1_test"
        assert dombkup._main_backup_name_format(snapdate) == expected_name

    def test_disk_backup_name_format(self, get_dombackup):
        dombkup = get_dombackup
        snapdate = datetime.datetime(2016, 8, 15, 17, 10, 13, 0)

        backup_name = dombkup._disk_backup_name_format(snapdate, "vda")
        expected_name = "20160815-171013_1_test_vda"
        assert backup_name == expected_name

    def test_get_definition(self, build_mock_domain):
        dombkup = build_dombackup(
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

    def test_dump_json_definition(self, build_mock_domain, tmpdir):
        target_dir = tmpdir.mkdir("json_dump")
        dombkup = build_dombackup(
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
        dombkup = build_dombackup(
            dom=build_mock_domain, target_dir=str(target_dir)
        )
        dombkup.pending_info["date"] = 0

        dombkup._dump_pending_info()
        assert len(target_dir.listdir()) == 1
        dombkup._clean_pending_info()
        assert len(target_dir.listdir()) == 0

    def test_clean_aborted(self, build_mock_domain, tmpdir, mocker):
        target_dir = tmpdir.mkdir("clean_aborted")
        dombkup = self.prepare_clean_aborted_dombkup(
            build_mock_domain, target_dir, mocker
        )

        target_dir.join("vda.qcow2").write("")
        dombkup.pending_info["disks"] = {
            "vda": {
                "src": "vda.qcow2", "target": "vda.qcow2",
                "snapshot": "vda.snap"
            },
        }
        dombkup._dump_pending_info()
        assert len(target_dir.listdir()) == 2

        dombkup.clean_aborted()
        assert not target_dir.listdir()

    def test_clean_aborted_test_ext_snapshot(self, build_mock_domain, tmpdir,
                                             mocker):
        """
        Ensure that the external snapshot helper is correctly declared

        Needs to be declared to clean the external snapshots
        """
        target_dir = tmpdir.mkdir("clean_aborted")
        dombkup = self.prepare_clean_aborted_dombkup(
            build_mock_domain, target_dir, mocker
        )

        target_dir.join("vda.qcow2").write("")
        disk_infos = {
            "vda": {
                "src": "vda.qcow2", "target": "vda.qcow2",
                "snapshot": "vda.snap"
            },
        }
        dombkup.pending_info["disks"] = disk_infos.copy()
        dombkup._dump_pending_info()

        dombkup.clean_aborted()
        DomExtSnapshot.clean.assert_called_once_with()
        assert dombkup._ext_snapshot_helper.metadatas["disks"] == {
            "vda": {
                "src": disk_infos["vda"]["src"],
                "snapshot": disk_infos["vda"]["snapshot"]
            }
        }

    def test_clean_aborted_tar(self, build_mock_domain, tmpdir, mocker):
        target_dir = tmpdir.mkdir("clean_aborted_tar")
        dombkup = self.prepare_clean_aborted_dombkup(
            build_mock_domain, target_dir, mocker
        )
        dombkup.compression = "tar"

        target_dir.join("backup.tar").write("")
        dombkup.pending_info["tar"] = "backup.tar"
        dombkup._dump_pending_info()
        assert len(target_dir.listdir()) == 2

        dombkup.clean_aborted()
        assert not target_dir.listdir()

    def prepare_clean_aborted_dombkup(self, mock_domain, target_dir,
                                      mocker):

        dombkup = build_dombackup(dom=mock_domain, target_dir=str(target_dir))
        dombkup.pending_info["date"] = 0

        mocker.patch("virt_backup.backups.snapshot.DomExtSnapshot.clean")

        return dombkup

    def test_compatible_with(self, get_uncompressed_dombackup,
                             build_mock_domain):
        dombackup1 = get_uncompressed_dombackup
        dombackup2 = build_dombackup(
            dom=build_mock_domain, dev_disks=("vdb", ), compression=None,
        )

        assert dombackup1.compatible_with(dombackup2)

    def test_not_compatible_with(self, get_uncompressed_dombackup,
                                 build_mock_domain):
        dombackup1 = get_uncompressed_dombackup
        dombackup1.target_dir = "/tmp/test"
        dombackup2 = build_dombackup(
            dom=build_mock_domain, dev_disks=("vdb", ), compression=None,
        )

        assert not dombackup1.compatible_with(dombackup2)
