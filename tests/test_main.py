import os
import pytest
import re

import virt_backup.__main__
from virt_backup.__main__ import (
    build_parser, list_groups, get_usable_complete_groups
)
from virt_backup.config import get_config, Config
from virt_backup.groups import CompleteBackupGroup

CUR_PATH = os.path.dirname(os.path.realpath(__file__))
TESTCONF_PATH = os.path.join(CUR_PATH, "testconfig", "config.yml")


@pytest.fixture
def args_parser():
    return build_parser()


class TestList():
    default_parser_args = ("list", )

    @pytest.fixture
    def mocked_config(self, monkeypatch, build_backup_directory):
        config = mock_get_config(monkeypatch)
        change_config_to_testing_bak_dir(
            config, str(build_backup_directory["backup_dir"])
        )
        self.backups = build_backup_directory

        return config

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
        lines.remove("")
        groups = {}

        while lines:
            group_name = lines[0].lstrip().rstrip()
            groups[group_name] = {}

            nb_domains = int(re.match(
                r".*: (?P<domains>\d*) .*, \d* .*$", lines[2]
            ).group("domains"))

            for i in range(nb_domains):
                domain, nb_backups = re.match(
                    r"(?P<domain>.*): (?P<backups>\d*) .*$", lines[4 + i]
                ).groups()

                groups[group_name][domain.lstrip()] = int(nb_backups)

            lines = lines[4 + nb_domains:]

        return groups

    def compare_parsed_groups_with_complete(self, parsed_groups, config):
        groups = {g.name: g for g in get_usable_complete_groups(config)}
        for parsed_group, parsed_values in parsed_groups.items():
            group = groups[parsed_group]
            group.scan_backup_dir()

            assert sorted(parsed_values.keys()) == sorted(group.backups.keys())
            for parsed_domain, parsed_backups in parsed_values.items():
                assert parsed_backups == len(group.backups[parsed_domain])

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
        lines.remove("")
        groups = {}

        while lines:
            group_name = lines[0].lstrip().rstrip()

            nb_backups = int(re.match(
                r".*: \d* .*, (?P<backups>\d*) .*$", lines[2]
            ).group("backups"))
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


def mock_get_config(monkeypatch):
    config = Config(defaults={"debug": False, })
    config.from_dict(get_config(TESTCONF_PATH))

    monkeypatch.setattr(
        virt_backup.__main__, "get_setup_config", lambda: config
    )

    return config


def change_config_to_testing_bak_dir(config, backup_directory):
    config["groups"]["test"]["target"] = backup_directory

    return config
