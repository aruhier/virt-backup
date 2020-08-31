import pytest

import os
import yaml

from virt_backup import config
from virt_backup.config import get_config, Config

CUR_PATH = os.path.dirname(os.path.realpath(__file__))
TESTCONF_PATH = os.path.join(CUR_PATH, "testconfig", "config.yml")


@pytest.fixture
def get_testing_config():
    return get_config(custom_path=TESTCONF_PATH)


def test_get_config():
    config.CONFIG_DIRS = (os.path.join(CUR_PATH, "testconfig"),) + config.CONFIG_DIRS
    conf = get_config()
    with open(os.path.join(config.CONFIG_DIRS[0], "config.yml"), "r") as f:
        expected_conf = yaml.safe_load(f)

    assert conf == expected_conf


def test_get_config_custom_path(get_testing_config):
    # get_config already uses a custom path, so uses it
    conf = get_testing_config
    with open(TESTCONF_PATH, "r") as f:
        expected_conf = yaml.safe_load(f)

    assert conf == expected_conf


def test_get_config_not_existing(tmpdir):
    backup_dir = tmpdir.mkdir("no_config")
    testconf_path = str(backup_dir.join("config.yml"))

    with pytest.raises(FileNotFoundError):
        get_config(custom_path=testconf_path)


class TestConfig:
    def test_config(self):
        Config()

    def test_with_default_config(self):
        conf = Config(defaults={"debug": True})
        assert conf["debug"]

    def test_from_dict(self, get_testing_config):
        conf = Config()
        conf.from_dict(get_testing_config)

        assert sorted(conf.items()) == sorted(get_testing_config.items())

    def test_from_yaml(self, get_testing_config):
        conf = Config()
        conf.from_yaml(TESTCONF_PATH)

        assert sorted(conf.items()) == sorted(get_testing_config.items())

    def test_from_str(self, get_testing_config):
        conf = Config()
        with open(TESTCONF_PATH, "r") as conf_file:
            conf.from_str(conf_file.read())

        assert sorted(conf.items()) == sorted(get_testing_config.items())

    def test_get_groups(self, get_testing_config):
        conf = Config()

        conf["default"] = {"daily": 4}
        conf["groups"] = {
            "test_group": {
                "daily": 3,
            },
        }

        groups = conf.get_groups()
        assert groups["test_group"]["daily"] == 3
