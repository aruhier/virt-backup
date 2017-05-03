
import pytest
from virt_backup.group import CompleteBackupGroup
from virt_backup.domain import list_backups_by_domain


class TestCompleteBackupGroup():
    def test_scan_backup_dir(self, build_backup_directory):
        backup_dir = str(build_backup_directory["backup_dir"])
        backups_def = list_backups_by_domain(str(backup_dir))

        group = CompleteBackupGroup(
            name="test", backup_dir=backup_dir, hosts=["r:.*"]
        )
        group.scan_backup_dir()

        assert sorted(group.backups.keys()) == sorted(backups_def.keys())
        for dom in group.backups:
            len(group.backups[dom]) == len(backups_def[dom])

    def test_scan_backup_dir_without_host(self, build_backup_directory):
        backup_dir = str(build_backup_directory["backup_dir"])
        backups_def = list_backups_by_domain(str(backup_dir))

        group = CompleteBackupGroup(
            name="test", backup_dir=backup_dir, hosts=[]
        )
        group.scan_backup_dir()

        assert not group.backups.keys()

    @pytest.mark.skip(reason="to implement")
    def test_clean(self, build_backup_directory):
        pass
