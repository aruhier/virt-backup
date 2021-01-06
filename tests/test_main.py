import os
import re
import arrow
import pytest

import virt_backup.__main__
from virt_backup.__main__ import (
    build_all_or_selected_groups,
    clean_backups,
    build_parser,
    list_groups,
    get_usable_complete_groups,
)
from virt_backup.backups import DomExtSnapshotCallbackRegistrer
from virt_backup.config import get_config, Config
from virt_backup.groups import CompleteBackupGroup
from helper.virt_backup import MockConn, MockDomain

CUR_PATH = os.path.dirname(os.path.realpath(__file__))
TESTCONF_PATH = os.path.join(CUR_PATH, "testconfig", "config.yml")


@pytest.fixture
def args_parser():
    return build_parser()


class AbstractMainTest:
    backups = None

    @pytest.fixture
    def mocked_config(self, monkeypatch, build_backup_directory):
        config = mock_get_config(monkeypatch)
        change_config_to_testing_bak_dir(
            config, str(build_backup_directory["backup_dir"])
        )
        self.backups = build_backup_directory

        return config

    @pytest.fixture(autouse=True)
    def mocked_conn(self, monkeypatch, build_mock_libvirtconn):
        mock_get_conn(monkeypatch, build_mock_libvirtconn)

    @pytest.fixture(autouse=True)
    def mocked_callbacks_registrer(self, monkeypatch):
        mock_callbacks_registrer(monkeypatch)


class AbstractTestList(AbstractMainTest):
    def extract_groups(self, list_output):
        raise NotImplementedError()


class TestList(AbstractTestList):
    default_parser_args = ("list",)

    def test_list_basic(self, args_parser, mocked_config, capsys):
        args = args_parser.parse_args(self.default_parser_args)

        list_groups(args)
        captured = capsys.readouterr()
        parsed_groups = self.extract_groups(captured.out)
        assert parsed_groups
        self.compare_parsed_groups_with_complete(parsed_groups, mocked_config)

    def extract_groups(self, list_output):
        """
        Extract groups from listing output
        """
        lines = list_output.splitlines()
        try:
            lines.remove("")
        except ValueError:
            pass
        groups = {}

        while lines:
            group_name = lines[0].lstrip().rstrip()
            groups[group_name] = {}

            nb_domains = int(
                re.match(r".*: (?P<domains>\d*) .*, \d* .*$", lines[2]).group("domains")
            )

            for i in range(nb_domains):
                domain, nb_backups = re.match(
                    r"(?P<domain>.*): (?P<backups>\d*) .*$", lines[4 + i]
                ).groups()

                groups[group_name][domain.lstrip()] = int(nb_backups)

            lines = lines[4 + nb_domains :]

        return groups

    def compare_parsed_groups_with_complete(self, parsed_groups, config):
        groups = {g.name: g for g in get_usable_complete_groups(config)}
        for parsed_group, parsed_values in parsed_groups.items():
            group = groups[parsed_group]
            group.scan_backup_dir()

            assert sorted(parsed_values.keys()) == sorted(group.backups.keys())
            for parsed_domain, parsed_backups in parsed_values.items():
                assert parsed_backups == len(group.backups[parsed_domain])

    def test_list_group_filtered(self, args_parser, mocked_config, capsys):
        args = args_parser.parse_args((*self.default_parser_args, "test", "empty"))

        list_groups(args)
        captured = capsys.readouterr()
        parsed_groups = self.extract_groups(captured.out)
        assert parsed_groups
        self.compare_parsed_groups_with_complete(parsed_groups, mocked_config)
        assert "empty" not in parsed_groups

    def test_list_filtered_empty(self, args_parser, mocked_config, capsys):
        args = args_parser.parse_args((*self.default_parser_args, "empty"))

        list_groups(args)
        captured = capsys.readouterr()
        parsed_groups = self.extract_groups(captured.out)

        assert not parsed_groups

    def test_list_one_host(self, args_parser, mocked_config, capsys):
        args = args_parser.parse_args(self.default_parser_args)
        mocked_config["groups"]["test"]["hosts"] = ["matching"]

        list_groups(args)
        captured = capsys.readouterr()
        parsed_groups = self.extract_groups(captured.out)

        assert parsed_groups
        self.compare_parsed_groups_with_complete(parsed_groups, mocked_config)

    def test_list_empty(self, args_parser, mocked_config, capsys):
        args = args_parser.parse_args(self.default_parser_args)
        mocked_config["groups"]["test"]["hosts"] = []

        list_groups(args)
        captured = capsys.readouterr()
        parsed_groups = self.extract_groups(captured.out)

        assert parsed_groups
        assert not parsed_groups["test"]


class TestListShort(TestList):
    default_parser_args = ("list", "-s")

    def extract_groups(self, list_output):
        """
        Extract groups from listing output
        """
        lines = list_output.splitlines()
        try:
            lines.remove("")
        except ValueError:
            pass
        groups = {}

        while lines:
            group_name = lines[0].lstrip().rstrip()

            nb_backups = int(
                re.match(r".*: \d* .*, (?P<backups>\d*) .*$", lines[2]).group("backups")
            )
            groups[group_name] = nb_backups

            lines = lines[3:]

        return groups

    def compare_parsed_groups_with_complete(self, parsed_groups, config):
        groups = {g.name: g for g in get_usable_complete_groups(config)}
        for parsed_group, parsed_nb_backups in parsed_groups.items():
            group = groups[parsed_group]
            group.scan_backup_dir()

            assert parsed_nb_backups == sum(
                len(dom_baks) for dom_baks in group.backups.values()
            )


class TestListDetailed(AbstractTestList):
    default_parser_args = ("list",)

    def test_list_detailed(self, args_parser, mocked_config, capsys):
        args = args_parser.parse_args(
            self.default_parser_args
            + (
                "-D",
                "matching",
            )
        )
        return self.list_and_compare(args, mocked_config, capsys)

    def list_and_compare(self, args, mocked_config, capsys):
        list_groups(args)
        captured = capsys.readouterr()
        parsed_groups = self.extract_groups(captured.out)
        assert parsed_groups
        self.compare_parsed_groups_with_complete(parsed_groups, mocked_config)

    def extract_groups(self, list_output):
        """
        Extract groups from listing output
        """
        lines = list_output.splitlines()
        try:
            lines.remove("")
        except ValueError:
            pass
        groups = {}

        while lines:
            group_name = lines[0].lstrip().rstrip()
            groups[group_name] = {}
            lines = lines[2:]

            while lines:
                host_matching = re.match(
                    r"(?P<host>.*): (?P<backups>\d*) backup\(s\)$", lines[0]
                )
                if not host_matching:
                    break

                host, nb_backups = (
                    host_matching.group("host"),
                    int(host_matching.group("backups")),
                )
                groups[group_name][host] = self.extract_backups_for_host(
                    lines[1 : 1 + nb_backups]
                )
                lines = lines[1 + nb_backups :]

            lines = lines[3:]

        return groups

    def extract_backups_for_host(self, output):
        backups = {}
        for l in output:
            date_str, def_file = re.match(
                r"(?P<date>.*): (?P<def_file>.*)$", l.lstrip().rstrip()
            ).groups()
            backups[arrow.get(date_str)] = def_file

        return backups

    def compare_parsed_groups_with_complete(self, parsed_groups, config):
        groups = {g.name: g for g in get_usable_complete_groups(config)}
        for g in groups.values():
            g.scan_backup_dir()

        for parsed_group, group_hosts in parsed_groups.items():
            for h, backups in group_hosts.items():
                self.compare_parsed_host_with_complete(
                    h, parsed_group, backups, groups[parsed_group]
                )

    def compare_parsed_host_with_complete(self, host, group, backups, complete_group):
        scanned_backups = complete_group.backups[host]
        assert len(scanned_backups) == len(backups)

        for scanned_backup in scanned_backups:
            backup_date = scanned_backup.date
            assert backup_date in backups

            assert backups[backup_date] == scanned_backup.get_complete_path_of(
                scanned_backup.definition_filename
            )

    def test_list_detailed_multiple_hosts(self, args_parser, mocked_config, capsys):
        args = args_parser.parse_args(
            self.default_parser_args + ("-D", "matching", "-D", "vm-10")
        )
        return self.list_and_compare(args, mocked_config, capsys)

    def test_list_detailed_empty(self, args_parser, mocked_config, capsys):
        with pytest.raises(SystemExit):
            args_parser.parse_args(self.default_parser_args + ("-D",))


class TestListAll(TestList):
    default_parser_args = ("list", "-a")
    conn = None

    @pytest.fixture(autouse=True)
    def mocked_conn(self, monkeypatch):
        self.conn = MockConn()
        self.conn._domains.append(MockDomain(self.conn, name="mocked_domain"))
        mock_get_conn(monkeypatch, self.conn)

    def compare_parsed_groups_with_complete(self, parsed_groups, config):
        """
        :param additional_domains: domains without backup, by group, needed to
                                   be printed in the listing
        """
        callbacks_registrer = DomExtSnapshotCallbackRegistrer(self.conn)
        complete_groups = {g.name: g for g in get_usable_complete_groups(config)}
        pending_groups = {
            g.name: g
            for g in build_all_or_selected_groups(
                config, self.conn, callbacks_registrer
            )
        }

        for parsed_group, parsed_values in parsed_groups.items():
            cgroup = complete_groups[parsed_group]
            cgroup.scan_backup_dir()
            pgroup = pending_groups[parsed_group]

            expected_domains = set(cgroup.backups.keys())
            expected_domains.update(set(b.dom.name() for b in pgroup.backups))
            assert sorted(parsed_values.keys()) == sorted(expected_domains)

            for parsed_domain, parsed_backups in parsed_values.items():
                assert parsed_backups == len(cgroup.backups.get(parsed_domain, []))


class TestClean(AbstractMainTest):
    default_parser_args = ("clean",)

    def test_clean_basic(self, args_parser, mocked_config, mocked_conn):
        args = args_parser.parse_args(self.default_parser_args)
        clean_backups(args)


def mock_get_config(monkeypatch):
    config = Config(
        defaults={
            "debug": False,
        }
    )
    config.from_dict(get_config(TESTCONF_PATH))

    monkeypatch.setattr(virt_backup.__main__, "get_setup_config", lambda: config)

    return config


def mock_get_conn(monkeypatch, conn):
    monkeypatch.setattr(virt_backup.__main__, "get_setup_conn", lambda x: conn)


def mock_callbacks_registrer(monkeypatch):
    monkeypatch.setattr(
        virt_backup.__main__.DomExtSnapshotCallbackRegistrer, "open", lambda *args: None
    )
    monkeypatch.setattr(
        virt_backup.__main__.DomExtSnapshotCallbackRegistrer,
        "close",
        lambda *args: None,
    )


def change_config_to_testing_bak_dir(config, backup_directory):
    config["groups"]["test"]["target"] = backup_directory

    return config
