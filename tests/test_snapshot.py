import json
import os
import arrow
import libvirt
import pytest

from virt_backup.backups import DomBackup
from virt_backup.domains import get_xml_block_of_disk
from virt_backup.backups.snapshot import DomExtSnapshot, DomExtSnapshotCallbackRegistrer
from virt_backup.exceptions import DiskNotFoundError, SnapshotNotStarted
from helper.virt_backup import MockSnapshot


class TestDomExtSnapshot:
    snapshot_helper = None

    @pytest.fixture(autouse=True)
    def gen_snapshot_helper(self, build_mock_domain):
        dom = build_mock_domain
        callbacks_registrer = DomExtSnapshotCallbackRegistrer(dom._conn)
        self.snapshot_helper = DomExtSnapshot(
            dom=dom,
            callbacks_registrer=callbacks_registrer,
            disks={
                "vda": {"src": "/vda.qcow2", "type": "qcow2"},
                "vdb": {"src": "/vdb.qcow2", "type": "qcow2"},
            },
        )

    def test_snapshot_logic_date(self, monkeypatch):
        """
        Create a DomBackup and test to add vdc
        """
        pre_snap_date = arrow.now()
        metadatas = self.start_snapshot(monkeypatch)
        post_snap_date = arrow.now()

        snapshot_date = metadatas["date"]

        assert snapshot_date >= pre_snap_date
        assert snapshot_date <= post_snap_date

    def test_snapshot_disks_infos(self, monkeypatch):
        """
        Check if metadatas contains the necessary infos
        """
        metadatas = self.start_snapshot(monkeypatch)

        assert len(self.snapshot_helper.disks) == len(metadatas["disks"])
        for disk in self.snapshot_helper.disks:
            assert sorted(("snapshot", "src")) == sorted(
                metadatas["disks"][disk].keys()
            )

    def test_snapshot_correct_snapshot_path(self, monkeypatch):
        """
        Check if the snapshot is done is the same path as its source disk
        """
        metadatas = self.start_snapshot(monkeypatch)

        for disk in metadatas["disks"].values():
            assert os.path.dirname(disk["src"]) == os.path.dirname(disk["snapshot"])

    def start_snapshot(self, monkeypatch):
        monkeypatch.setattr(
            self.snapshot_helper, "external_snapshot", lambda: MockSnapshot("123")
        )

        return self.snapshot_helper.start()

    def test_external_snapshot(self):
        snap = self.snapshot_helper.external_snapshot()
        assert isinstance(snap, MockSnapshot)

    def test_external_snapshot_quiesce_fallback(self):
        tried = {"quiesce": False}

        def mock_quiesce_failure(_, flags):
            if (flags & libvirt.VIR_DOMAIN_SNAPSHOT_CREATE_QUIESCE) != 0:
                tried["quiesce"] = True
                raise libvirt.libvirtError("quiesce error")

            return MockSnapshot("123")

        self.snapshot_helper.dom.set_mock_snapshot_create(mock_quiesce_failure)
        self.snapshot_helper.quiesce = True

        snap = self.snapshot_helper.external_snapshot()
        assert tried["quiesce"]
        assert isinstance(snap, MockSnapshot)

    def test_get_snapshot_flags(self):
        flags = self.snapshot_helper._get_snapshot_flags()
        assert flags == (
            libvirt.VIR_DOMAIN_SNAPSHOT_CREATE_DISK_ONLY
            + libvirt.VIR_DOMAIN_SNAPSHOT_CREATE_ATOMIC
            + libvirt.VIR_DOMAIN_SNAPSHOT_CREATE_NO_METADATA
        )

    def test_get_snapshot_flags_quiesce(self):
        flags = self.snapshot_helper._get_snapshot_flags(quiesce=True)
        assert (flags & libvirt.VIR_DOMAIN_SNAPSHOT_CREATE_QUIESCE) != 0

    def test_gen_libvirt_snapshot_xml(self):
        expected_xml = (
            "<domainsnapshot>\n"
            "  <description>Pre-backup external snapshot</description>\n"
            "  <disks>\n"
            '    <disk name="vda" snapshot="external"/>\n'
            '    <disk name="vdb" snapshot="external"/>\n'
            '    <disk name="vdz" snapshot="no"/>\n'
            "  </disks>\n"
            "</domainsnapshot>\n"
        )
        assert self.snapshot_helper.gen_libvirt_snapshot_xml() == expected_xml

    def test_gen_libvirt_snapshot_xml_ignored_disk(self):
        self.snapshot_helper.disks.pop("vdb")
        expected_xml = (
            "<domainsnapshot>\n"
            "  <description>Pre-backup external snapshot</description>\n"
            "  <disks>\n"
            '    <disk name="vda" snapshot="external"/>\n'
            '    <disk name="vdb" snapshot="no"/>\n'
            '    <disk name="vdz" snapshot="no"/>\n'
            "  </disks>\n"
            "</domainsnapshot>\n"
        )
        assert self.snapshot_helper.gen_libvirt_snapshot_xml() == expected_xml

    def test_manually_pivot_disk(self, build_mock_libvirtconn):
        self.snapshot_helper.conn = build_mock_libvirtconn
        self.snapshot_helper._manually_pivot_disk("vda", "/testvda")
        dom_xml = self.snapshot_helper.dom.XMLDesc()
        assert self.get_src_for_disk(dom_xml, "vda") == "/testvda"

    def get_src_for_disk(self, dom_xml, disk):
        elem = get_xml_block_of_disk(dom_xml, disk)
        return elem.xpath("source")[0].get("file")

    def test_manually_pivot_disk_libvirt_2(self, build_mock_libvirtconn):
        """
        Test manual pivot with libvirt < 3.0
        """
        conn = build_mock_libvirtconn
        conn._libvirt_version = 2000000
        conn._domains.append(self.snapshot_helper.dom)

        return self.test_manually_pivot_disk(conn)

    def test_manually_pivot_unexistant_disk(self):
        with pytest.raises(DiskNotFoundError):
            self.snapshot_helper._manually_pivot_disk("sda", "/testvda")

    def test_clean_no_metadata(self):
        with pytest.raises(SnapshotNotStarted):
            self.snapshot_helper.clean()

    def test_clean(self, monkeypatch, tmpdir):
        snapdir = self.prepare_test_clean(monkeypatch, tmpdir)
        self.snapshot_helper.clean()

        assert len(snapdir.listdir()) == 0

    def prepare_test_clean(self, monkeypatch, tmpdir):
        snapshots = self.create_temp_snapshot_files(tmpdir)

        self.mock_pivot_mechanism(monkeypatch)
        # set the domain unactive to avoid the blockcommit
        self.snapshot_helper.dom.set_state(0, 0)

        self.snapshot_helper.metadatas = {
            "date": arrow.now(),
            "disks": {
                disk: {"src": prop["src"], "snapshot": snapshots[disk]}
                for disk, prop in self.snapshot_helper.disks.items()
            },
        }
        return tmpdir.join("snaps")

    def create_temp_snapshot_files(self, tmpdir):
        tmpdir = tmpdir.mkdir("snaps")
        self.snapshot_helper.dom.set_storage_basedir(os.path.abspath(str(tmpdir)))

        snapshots = {}
        # swap disk and snapshots, to just change the domain basedir
        for disk, prop in self.snapshot_helper.disks.items():
            dom_disk_path = (
                (get_xml_block_of_disk(self.snapshot_helper.dom.XMLDesc(), disk))
                .xpath("source")[0]
                .get("file")
            )
            tmpdir.join(os.path.basename(dom_disk_path)).write("")
            prop["snapshot"] = dom_disk_path

            disk_path = tmpdir.join("{}.qcow2.{}".format(disk, "123"))
            prop["src"] = str(disk_path)
            snapshots[disk] = prop["snapshot"]

        return snapshots

    def mock_pivot_mechanism(self, monkeypatch):
        monkeypatch.setattr(
            self.snapshot_helper, "_qemu_img_commit", lambda *args: None
        )

        monkeypatch.setattr(
            self.snapshot_helper, "_manually_pivot_disk", lambda *args: None
        )
