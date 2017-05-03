
import arrow
import os
import pytest

from virt_backup.group import CompleteBackupGroup, complete_groups_from_dict
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

    def test_clean(self, build_backup_directory):
        backup_dir = str(build_backup_directory["backup_dir"])
        group = CompleteBackupGroup(
            name="test", backup_dir=backup_dir, hosts=["r:.*"]
        )
        group.scan_backup_dir()
        nb_initial_backups = sum(len(b) for b in group.backups.values())

        cleaned = group.clean(hourly=2, daily=3, weekly=1, monthly=1, yearly=2)
        backups_def = list_backups_by_domain(str(backup_dir))
        expected_dates = sorted((
            arrow.get("2016-07-08 19:40:02").to("local"),
            arrow.get("2016-07-08 18:30:02").to("local"),
            arrow.get("2016-07-08 17:40:02").to("local"),
            arrow.get("2016-07-07 19:40:02").to("local"),
            arrow.get("2016-07-06 20:40:02").to("local"),
            arrow.get("2016-03-08 14:28:13").to("local"),
            arrow.get("2014-05-01 00:30:00").to("local"),
        ))

        for domain, backups in group.backups.items():
            dates = sorted(b.date for b in backups)
            assert dates == expected_dates
            assert len(backups_def[domain]) == len(backups)

        nb_remaining_backups = sum(len(b) for b in group.backups.values())
        assert len(cleaned) == nb_initial_backups - nb_remaining_backups


def test_complete_groups_from_dict(build_mock_libvirtconn_filled):
    """
    Test groups_from_dict with only one group
    """
    groups_config = {
        "test": {
            "target": "/mnt/test",
            "compression": "tar",
            "hosts": [
                {"host": "r:^matching\d?$", "disks": ["vda", "vdb"]},
                "!matching2", "nonexisting"
            ],
        },
    }

    groups = tuple(complete_groups_from_dict(groups_config))
    assert len(groups) == 1
    test_group = groups[0]

    assert test_group.name == "test"
    assert test_group.backup_dir == "/mnt/test"
    assert test_group.hosts == ["r:^matching\d?$", "!matching2", "nonexisting"]


def test_complete_groups_from_dict_multiple_groups(
        build_mock_libvirtconn_filled):
    """
    Test match_domains_from_config with a str pattern
    """
    groups_config = {
        "test0": {
            "target": "/mnt/test0",
            "compression": "tar",
            "hosts": ["matching2", ],
        },
        "test1": {
            "target": "/mnt/test1",
            "hosts": ["matching", "a"],
        },
    }

    groups = tuple(complete_groups_from_dict(groups_config))
    assert len(groups) == 2
    group0, group1 = groups

    assert sorted((group0.name, group1.name)) == ["test0", "test1"]
