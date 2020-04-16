import datetime
import json
import tarfile

import arrow
import pytest

import virt_backup
from virt_backup.backups import DomBackup, WriteBackupPackagers
from virt_backup.backups.snapshot import DomExtSnapshot, DomExtSnapshotCallbackRegistrer
from helper.virt_backup import MockSnapshot, build_dombackup


class TestDomBackup:
    def test_cancel(self, get_dombackup):
        get_dombackup.cancel()

        assert get_dombackup._cancel_flag.is_set()

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
            },
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
        dombkup = build_dombackup(build_mock_domain, dev_disks=("vda",))

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
        dombkup = build_dombackup(build_mock_domain, disks=("vda",))
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
            },
        }
        assert dombkup.disks == expected_disks

    def test_add_not_existing_disk(self, get_dombackup):
        """
        Create a DomBackup and test to add vdc
        """
        dombkup = get_dombackup
        with pytest.raises(KeyError):
            dombkup.add_disks("vdc")

    def test_snapshot_and_save_date_test_pending_info(
        self, build_mock_domain, monkeypatch, tmpdir
    ):
        """
        Create a DomBackup, snapshot, then tests if dumped pending info are
        correct
        """
        backup_dir = tmpdir.mkdir("snapshot_and_save_date")
        snapshot_date, definition = self.take_snapshot_and_return_date(
            build_mock_domain, str(backup_dir), monkeypatch
        )

        pending_info_path = backup_dir.listdir()[0]
        pending_info = json.loads(pending_info_path.read())

        assert definition.items() <= pending_info.items()
        assert "snapshot" in pending_info["disks"]["vda"]
        assert "src" in pending_info["disks"]["vda"]

    def take_snapshot_and_return_date(self, mock_domain, backup_dir, monkeypatch):
        dombkup = build_dombackup(
            dom=mock_domain, dev_disks=("vda",), backup_dir=backup_dir
        )

        snapshot_helper = DomExtSnapshot(
            dombkup.dom,
            dombkup.disks,
            DomExtSnapshotCallbackRegistrer(dombkup.conn),
            dombkup.conn,
            dombkup.timeout,
        )
        monkeypatch.setattr(
            snapshot_helper, "external_snapshot", lambda: MockSnapshot(name="test")
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

    def test_get_packager(self, build_mock_domain):
        """
        Checks that this function can build a packager and that it fills every required
        info in the definition and pending_info.

        Some info cannot be written in the definition and the pending_info before getting a packager for a backup. For
        example, a tar archive name is
        """
        dombkup = build_dombackup(
            dom=build_mock_domain,
            dev_disks=("vda",),
            packager="tar",
            packager_opts={"compression": "xz", "compression_lvl": 4},
        )

        snapdate = arrow.get("2016-07-09 17:40:02")
        dombkup._name = dombkup._main_backup_name_format(snapdate)

        packager = dombkup._get_packager()
        assert isinstance(packager, WriteBackupPackagers.tar.value)
        assert packager.compression == "xz"
        assert packager.compression_lvl == 4

    def test_get_definition(self, build_mock_domain):
        dombkup = build_dombackup(
            dom=build_mock_domain,
            dev_disks=("vda",),
            packager="tar",
            packager_opts={"compression": "xz", "compression_lvl": 4},
        )

        expected_def = {
            "domain_id": build_mock_domain.ID(),
            "domain_name": build_mock_domain.name(),
            "domain_xml": build_mock_domain.XMLDesc(),
            "packager": {
                "type": "tar",
                "opts": {"compression": "xz", "compression_lvl": 4},
            },
            "version": virt_backup.VERSION,
        }
        assert dombkup.get_definition() == expected_def

    def test_dump_json_definition(self, build_mock_domain, tmpdir):
        backup_dir = tmpdir.mkdir("json_dump")
        dombkup = build_dombackup(
            dom=build_mock_domain,
            dev_disks=("vda",),
            packager="tar",
            packager_opts={"compression": "xz", "compression_lvl": 4},
            backup_dir=str(backup_dir),
        )

        definition = dombkup.get_definition()
        datenow = datetime.datetime.now()
        definition["date"] = datenow.timestamp()

        dombkup._dump_json_definition(definition)
        assert len(backup_dir.listdir()) == 1
        assert json.loads(backup_dir.listdir()[0].read()) == definition

    def test_clean_pending_info(self, build_mock_domain, tmpdir):
        backup_dir = tmpdir.mkdir("clean_pending_info")
        dombkup = build_dombackup(dom=build_mock_domain, backup_dir=str(backup_dir))
        dombkup.pending_info["date"] = 0

        dombkup._dump_pending_info()
        assert len(backup_dir.listdir()) == 1
        dombkup._clean_pending_info()
        assert len(backup_dir.listdir()) == 0

    def test_clean_aborted_packager(self, build_mock_domain, tmpdir, mocker):
        backup_dir = tmpdir.mkdir("clean_aborted")
        dombkup = self.prepare_clean_aborted_dombkup(
            build_mock_domain, backup_dir, mocker
        )

        backup_dir.join("vda.qcow2").write("")
        dombkup.pending_info["disks"] = {
            "vda": {"src": "vda.qcow2", "target": "vda.qcow2", "snapshot": "vda.snap"},
        }
        dombkup.pending_info["packager"] = {"type": "directory", "opts": {}}
        dombkup._dump_pending_info()
        dombkup._dump_json_definition(dombkup.definition)
        assert len(backup_dir.listdir()) == 3

        dombkup.clean_aborted()
        assert not backup_dir.listdir()

    def test_clean_aborted_packager_multiple_disks(
        self, build_mock_domain, tmpdir, mocker
    ):
        """
        Test with multiple disks, but one not backup yet (no target yet defined).
        """
        backup_dir = tmpdir.mkdir("clean_aborted")
        dombkup = self.prepare_clean_aborted_dombkup(
            build_mock_domain, backup_dir, mocker
        )

        backup_dir.join("vda.qcow2").write("")
        dombkup.pending_info["disks"] = {
            "vda": {"src": "vda.qcow2", "target": "vda.qcow2", "snapshot": "vda.snap"},
            "vdb": {"src": "vdb.qcow2", "snapshot": "vda.snap"},
        }
        dombkup.pending_info["packager"] = {"type": "directory", "opts": {}}
        dombkup._dump_pending_info()
        dombkup._dump_json_definition(dombkup.definition)
        assert len(backup_dir.listdir()) == 3

        dombkup.clean_aborted()
        assert not backup_dir.listdir()

    def test_clean_aborted_test_ext_snapshot(self, build_mock_domain, tmpdir, mocker):
        """
        Ensure that the external snapshot helper is correctly declared

        Needs to be declared to clean the external snapshots
        """
        backup_dir = tmpdir.mkdir("clean_aborted")
        dombkup = self.prepare_clean_aborted_dombkup(
            build_mock_domain, backup_dir, mocker
        )

        backup_dir.join("vda.qcow2").write("")
        disk_infos = {
            "vda": {"src": "vda.qcow2", "target": "vda.qcow2", "snapshot": "vda.snap"},
        }
        dombkup.pending_info["disks"] = disk_infos.copy()
        dombkup._dump_pending_info()
        dombkup._dump_json_definition(dombkup.definition)

        dombkup.clean_aborted()
        DomExtSnapshot.clean.assert_called_once_with()
        assert dombkup._ext_snapshot_helper.metadatas["disks"] == {
            "vda": {
                "src": disk_infos["vda"]["src"],
                "snapshot": disk_infos["vda"]["snapshot"],
            }
        }

    def prepare_clean_aborted_dombkup(self, mock_domain, backup_dir, mocker):
        dombkup = build_dombackup(
            dom=mock_domain, backup_dir=str(backup_dir), packager="directory"
        )
        dombkup.definition = dombkup.get_definition()
        dombkup.pending_info["date"] = 0
        dombkup.definition["date"] = 0

        dombkup.definition["name"] = "test"
        dombkup.pending_info["name"] = "test"

        mocker.patch("virt_backup.backups.snapshot.DomExtSnapshot.clean")

        return dombkup

    def test_compatible_with(self, get_compressed_dombackup, build_mock_domain):
        dombackup1 = get_compressed_dombackup
        dombackup2 = build_dombackup(
            dom=build_mock_domain,
            dev_disks=("vdb",),
            packager="tar",
            packager_opts={"compression": "xz", "compression_lvl": 4},
        )

        assert dombackup1.compatible_with(dombackup2)

    def test_not_compatible_with(self, get_compressed_dombackup, build_mock_domain):
        dombackup1 = get_compressed_dombackup
        dombackup1.backup_dir = "/tmp/test"
        dombackup2 = build_dombackup(
            dom=build_mock_domain,
            dev_disks=("vdb",),
            packager="tar",
            packager_opts={"compression": "gz", "compression_lvl": 4},
        )

        assert not dombackup1.compatible_with(dombackup2)
