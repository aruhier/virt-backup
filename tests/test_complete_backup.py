import datetime
import filecmp
import os
import tarfile
import arrow
import pytest

from virt_backup.backups import build_dom_complete_backup_from_def
from virt_backup.domains import get_domain_disks_of
from virt_backup.exceptions import DomainRunningError

from helper.virt_backup import build_complete_backup_files_from_domainbackup


def transform_dombackup_to_dom_complete_backup(dombkup):
    definition = build_complete_backup_files_from_domainbackup(dombkup, arrow.now())

    return build_dom_complete_backup_from_def(definition, dombkup.backup_dir)


@pytest.fixture
def get_uncompressed_complete_backup(get_uncompressed_dombackup, tmpdir):
    dombkup = get_uncompressed_dombackup
    dombkup.backup_dir = str(tmpdir)

    return transform_dombackup_to_dom_complete_backup(dombkup)


@pytest.fixture
def get_compressed_complete_backup(get_compressed_dombackup, tmpdir):
    dombkup = get_compressed_dombackup
    dombkup.backup_dir = str(tmpdir)

    return transform_dombackup_to_dom_complete_backup(dombkup)


@pytest.fixture
def build_bak_definition(get_uncompressed_dombackup):
    dombkup = get_uncompressed_dombackup

    return get_and_tweak_def_from_dombackup(dombkup)


@pytest.fixture
def build_bak_definition_with_compression(get_compressed_dombackup):
    dombkup = get_compressed_dombackup

    return get_and_tweak_def_from_dombackup(dombkup)


def get_and_tweak_def_from_dombackup(dombkup, date=None):
    definition = dombkup.get_definition()
    if date is None:
        date = datetime.datetime.now()
    definition["date"] = date.timestamp()
    definition["name"] = dombkup._main_backup_name_format(date)

    return definition


def test_get_complete_backup_from_def(build_bak_definition_with_compression):
    definition = build_bak_definition_with_compression
    complete_backup = build_dom_complete_backup_from_def(definition, backup_dir="./")

    assert complete_backup.dom_xml == definition["domain_xml"]


class TestDomCompleteBackup:
    def test_cancel(self, get_dombackup):
        get_dombackup.cancel()

        assert get_dombackup._cancel_flag.is_set()

    def test_restore_disk_in_domain(
        self, get_uncompressed_complete_backup, build_stopped_mock_domain, tmpdir
    ):
        backup = get_uncompressed_complete_backup
        domain = build_stopped_mock_domain

        src_img = backup.get_complete_path_of(backup.disks["vda"])
        domain.set_storage_basedir(str(tmpdir))
        dst_img = get_domain_disks_of(domain.XMLDesc(), "vda")["vda"]["src"]

        backup.restore_and_replace_disk_of("vda", domain, "vda")

        assert filecmp.cmp(src_img, dst_img)
        assert (
            get_domain_disks_of(domain.XMLDesc())["vda"]["type"]
            == get_domain_disks_of(backup.dom_xml)["vda"]["type"]
        )

    def test_restore_disk_in_running_domain(
        self, get_uncompressed_complete_backup, build_mock_domain
    ):
        backup = get_uncompressed_complete_backup
        domain = build_mock_domain

        with pytest.raises(DomainRunningError):
            backup.restore_and_replace_disk_of("vda", domain, "vda")

    def test_restore_to(self, get_uncompressed_complete_backup, tmpdir):
        """
        Test with a not compressed backup
        """
        backup = get_uncompressed_complete_backup
        target_dir = tmpdir.mkdir("extract")

        return self.restore_to(backup, target_dir)

    def test_restore_to_with_tar(self, get_compressed_complete_backup, tmpdir):
        """
        Test with a not compressed backup
        """
        backup = get_compressed_complete_backup
        target_dir = tmpdir.mkdir("extract")

        return self.restore_to(backup, target_dir)

    def restore_to(self, complete_backup, target):
        complete_backup.restore_to(str(target))

        # there should be 1 .xml file + all disks
        assert len(target.listdir()) == 1 + len(complete_backup.disks)

    def test_restore_disk_to_dir(self, get_uncompressed_complete_backup, tmpdir):
        backup = get_uncompressed_complete_backup
        src_img = backup.get_complete_path_of(backup.disks["vda"])
        extract_dir = tmpdir.mkdir("extract")
        dst_img = os.path.join(str(extract_dir), backup.disks["vda"])

        backup.restore_disk_to("vda", str(extract_dir))

        assert filecmp.cmp(src_img, dst_img)

    def test_restore_disk_to(self, get_uncompressed_complete_backup, tmpdir):
        """
        Test with a not compressed backup
        """
        backup = get_uncompressed_complete_backup
        src_img = backup.get_complete_path_of(backup.disks["vda"])
        extract_dir = tmpdir.mkdir("extract")
        dst_img = os.path.join(str(extract_dir), "vda.img")

        backup.restore_disk_to("vda", dst_img)

        assert filecmp.cmp(src_img, dst_img)

    def test_restore_replace_domain(
        self, get_uncompressed_complete_backup, build_mock_libvirtconn
    ):
        conn = build_mock_libvirtconn
        backup = get_uncompressed_complete_backup

        backup.restore_replace_domain(conn)

    def test_restore_domain_to(
        self, get_uncompressed_complete_backup, build_mock_libvirtconn
    ):
        """
        Test to restore the domain to a specific id
        """
        conn = build_mock_libvirtconn
        backup = get_uncompressed_complete_backup

        # TODO: check if id of the new domain matches
        backup.restore_replace_domain(conn, id=13)

    def test_restore_compressed_disk_to(self, get_compressed_complete_backup, tmpdir):
        """
        Test with a compressed backup
        """
        backup = get_compressed_complete_backup
        extract_dir = tmpdir.mkdir("extract")
        dst_img = os.path.join(str(extract_dir), backup.disks["vda"])

        backup.restore_disk_to("vda", dst_img)
        src_img = self.extract_disk_from_backup_packager(backup, "vda")

        assert filecmp.cmp(src_img, dst_img, shallow=False)

    def test_restore_compressed_disk_to_dir(
        self, get_compressed_complete_backup, tmpdir
    ):
        """
        Test with a compressed backup
        """
        backup = get_compressed_complete_backup
        extract_dir = tmpdir.mkdir("extract")
        dst_img = os.path.join(str(extract_dir), backup.disks["vda"])

        backup.restore_disk_to("vda", str(extract_dir))
        src_img = self.extract_disk_from_backup_packager(backup, "vda")

        assert filecmp.cmp(src_img, dst_img, shallow=False)

    def extract_disk_from_backup_packager(self, backup, disk):
        packager = backup._get_packager()
        dest = backup.get_complete_path_of(backup.disks[disk])
        with packager:
            packager.restore(backup.disks[disk], dest)

        return dest

    def test_get_complete_backup_from_def(self, get_uncompressed_complete_backup):
        backup = get_uncompressed_complete_backup

        complete_path_of_vda = backup.get_complete_path_of(backup.disks["vda"])
        expected_path = os.path.join(backup.backup_dir, backup.disks["vda"])

        assert complete_path_of_vda == expected_path

    def test_delete(self, get_uncompressed_complete_backup):
        backup = get_uncompressed_complete_backup
        backup.delete()

        assert not os.path.exists(backup.backup_dir)
