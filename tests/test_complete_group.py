import arrow
import json
import os
import pytest

from virt_backup.groups import CompleteBackupGroup, complete_groups_from_dict
from virt_backup.groups.complete import list_backups_by_domain
from virt_backup.backups import DomBackup, DomExtSnapshotCallbackRegistrer
from virt_backup.exceptions import BackupNotFoundError


class TestCompleteBackupGroup:
    def test_scan_backup_dir(self, build_backup_directory):
        backup_dir = str(build_backup_directory["backup_dir"])
        backups_def = list_backups_by_domain(str(backup_dir))

        group = CompleteBackupGroup(name="test", backup_dir=backup_dir, hosts=("r:.*",))
        group.scan_backup_dir()

        assert sorted(group.backups.keys()) == sorted(backups_def.keys())
        for dom in group.backups:
            assert len(group.backups[dom]) == len(backups_def[dom])

    def test_scan_backup_dir_without_host(self, build_backup_directory):
        backup_dir = str(build_backup_directory["backup_dir"])

        group = CompleteBackupGroup(name="test", backup_dir=backup_dir, hosts=tuple())
        group.scan_backup_dir()

        assert not group.backups.keys()

    def test_scan_backup_dir_several_patterns(self, build_backup_directory):
        backup_dir = str(build_backup_directory["backup_dir"])
        backups_def = list_backups_by_domain(str(backup_dir))

        # g: should do nothing for now, but test if passing
        group = CompleteBackupGroup(
            name="test", backup_dir=backup_dir, hosts=("a", "r:^[b-z].*", "g:all")
        )
        group.scan_backup_dir()

        assert group.backups
        assert sorted(group.backups.keys()) == sorted(backups_def.keys())
        for dom in group.backups:
            assert len(group.backups[dom]) == len(backups_def[dom])

    def test_get_backup_at_date(self, build_backup_directory):
        group = self.prepare_get_backup_at_date(build_backup_directory)

        domain_name = next(iter(group.backups.keys()))
        testing_date = arrow.get("2016-07-08 17:40:02")

        backup = group.get_backup_at_date(domain_name, testing_date)
        assert backup.date == testing_date

    def test_get_backup_at_date_unexisting(self, build_backup_directory):
        group = self.prepare_get_backup_at_date(build_backup_directory)

        domain_name = next(iter(group.backups.keys()))
        testing_date = arrow.get("2016-07-09 17:40:02")

        with pytest.raises(BackupNotFoundError):
            group.get_backup_at_date(domain_name, testing_date)

    def prepare_get_backup_at_date(self, build_backup_directory):
        backup_dir = str(build_backup_directory["backup_dir"])
        group = CompleteBackupGroup(name="test", backup_dir=backup_dir, hosts=["r:.*"])
        group.scan_backup_dir()

        return group

    def test_get_nearest_backup_of(self, build_backup_directory):
        backup_dir = str(build_backup_directory["backup_dir"])
        group = CompleteBackupGroup(name="test", backup_dir=backup_dir, hosts=["r:.*"])
        group.scan_backup_dir()

        domain_name = next(iter(group.backups.keys()))
        testing_date = arrow.get("2015")
        nearest_backup = group.get_n_nearest_backup(domain_name, testing_date, 1)[0]

        difference = abs(testing_date - nearest_backup.date)
        for b in group.backups[domain_name]:
            assert abs(testing_date - b.date) >= difference

    def test_clean(self, build_backup_directory):
        backup_dir = str(build_backup_directory["backup_dir"])
        group = CompleteBackupGroup(name="test", backup_dir=backup_dir, hosts=["r:.*"])
        group.scan_backup_dir()
        nb_initial_backups = sum(len(b) for b in group.backups.values())

        cleaned = group.clean(hourly=2, daily=3, weekly=1, monthly=1, yearly=2)
        backups_def = list_backups_by_domain(str(backup_dir))
        expected_dates = sorted(
            (
                arrow.get("2016-07-08 19:40:02").to("local"),
                arrow.get("2016-07-08 18:30:02").to("local"),
                arrow.get("2016-07-08 17:40:02").to("local"),
                arrow.get("2016-07-07 19:40:02").to("local"),
                arrow.get("2016-07-06 20:40:02").to("local"),
                arrow.get("2016-03-08 14:28:13").to("local"),
                arrow.get("2014-05-01 00:30:00").to("local"),
            )
        )

        for domain, backups in group.backups.items():
            dates = sorted(b.date for b in backups)
            assert dates == expected_dates
            assert len(backups_def[domain]) == len(backups)

        nb_remaining_backups = sum(len(b) for b in group.backups.values())
        assert len(cleaned) == nb_initial_backups - nb_remaining_backups

    def test_clean_unset_period(self, build_backup_directory):
        """
        Test if cleaning works if some periods are not set.

        Related to issue #27
        """
        backup_dir = str(build_backup_directory["backup_dir"])
        group = CompleteBackupGroup(name="test", backup_dir=backup_dir, hosts=["r:.*"])
        group.scan_backup_dir()

        group.clean(daily=3, monthly=1, yearly=2)
        expected_dates = sorted(
            (
                arrow.get("2014-05-01 00:30:00").to("local"),
                arrow.get("2016-03-08 14:28:13").to("local"),
                arrow.get("2016-04-08 19:40:02").to("local"),
                arrow.get("2016-07-06 20:40:02").to("local"),
                arrow.get("2016-07-07 19:40:02").to("local"),
                arrow.get("2016-07-07 21:40:02").to("local"),
                arrow.get("2016-07-08 17:40:02").to("local"),
                arrow.get("2016-07-08 18:30:02").to("local"),
                arrow.get("2016-07-08 19:40:02").to("local"),
            )
        )

        for domain, backups in group.backups.items():
            dates = sorted(b.date for b in backups)
            assert dates == expected_dates

    def test_clean_broken(
        self, build_backup_directory, build_mock_domain, build_mock_libvirtconn, mocker
    ):
        build_mock_libvirtconn._domains.append(build_mock_domain)
        callbacks_registrer = DomExtSnapshotCallbackRegistrer(build_mock_libvirtconn)
        backup_dir = build_backup_directory["backup_dir"]
        group = CompleteBackupGroup(
            name="test",
            backup_dir=str(backup_dir),
            hosts=["r:.*"],
            conn=build_mock_libvirtconn,
            callbacks_registrer=callbacks_registrer,
        )

        dombkup = DomBackup(
            dom=build_mock_domain,
            backup_dir=str(backup_dir.mkdir(build_mock_domain.name())),
            callbacks_registrer=callbacks_registrer,
        )
        dombkup.pending_info = dombkup.get_definition()
        dombkup.pending_info["domain_name"] = build_mock_domain.name()
        dombkup.pending_info["date"] = 0
        dombkup.pending_info["disks"] = {}
        dombkup.pending_info["name"] = "test"
        dombkup.pending_info["packager"] = {"type": "directory", "opts": {}}
        dombkup._dump_pending_info()

        group.scan_backup_dir()
        nb_initial_backups = sum(len(b) for b in group.broken_backups.values())
        assert nb_initial_backups == 1

        broken_backup = group.broken_backups[build_mock_domain.name()][0]
        mocker.spy(broken_backup, "clean_aborted")

        group.clean_broken_backups()
        assert not group.broken_backups[build_mock_domain.name()]
        assert broken_backup.clean_aborted.called


def test_complete_groups_from_dict():
    """
    Test groups_from_dict with only one group
    """
    groups_config = {
        "test": {
            "target": "/mnt/test",
            "compression": "tar",
            "hosts": [
                {"host": r"r:^matching\d?$", "disks": ["vda", "vdb"]},
                "!matching2",
                "nonexisting",
            ],
        },
    }

    groups = tuple(complete_groups_from_dict(groups_config))
    assert len(groups) == 1
    test_group = groups[0]

    assert test_group.name == "test"
    assert test_group.backup_dir == "/mnt/test"
    assert test_group.hosts == [r"r:^matching\d?$", r"!matching2", r"nonexisting"]


def test_complete_groups_from_dict_multiple_groups():
    """
    Test match_domains_from_config with a str pattern
    """
    groups_config = {
        "test0": {
            "target": "/mnt/test0",
            "compression": "tar",
            "hosts": [
                "matching2",
            ],
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


def test_list_backups_by_domain(build_backup_directory):
    backup_dir = str(build_backup_directory["backup_dir"])
    backup_dates = tuple(build_backup_directory["backup_dates"])
    domain_names = build_backup_directory["domain_names"]

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
        assert sorted(expected_backups(domain_id, domain_name)) == sorted(
            backups[domain_name]
        )
