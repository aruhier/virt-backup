
import pytest

import os
import yaml

from virt_backup import config
from virt_backup.config import get_config, Config

CUR_PATH = os.path.dirname(os.path.realpath(__file__))
TESTCONF_PATH = os.path.join(CUR_PATH, "testconfig", "config.yml")


@pytest.fixture
def fixture_get_config():
    return get_config(custom_path=TESTCONF_PATH)


def test_get_config():
    config.CONFIG_DIRS = (
        (os.path.join(CUR_PATH, "testconfig"), ) + config.CONFIG_DIRS
    )
    conf = get_config()
    with open(os.path.join(config.CONFIG_DIRS[0], "config.yml"), "r") as f:
        expected_conf = yaml.safe_load(f)

    assert conf == expected_conf


def test_get_config_custom_path(fixture_get_config):
    # fixture_get_config already uses a custom path, so uses it
    conf = fixture_get_config
    with open(TESTCONF_PATH, "r") as f:
        expected_conf = yaml.safe_load(f)

    assert conf == expected_conf


def test_get_config_not_existing(tmpdir):
    target_dir = tmpdir.mkdir("no_config")
    testconf_path = str(target_dir.join("config.yml"))

    with pytest.raises(FileNotFoundError):
        get_config(custom_path=testconf_path)


def test_config():
    Config()


def test_config_with_default_config():
    conf = Config(defaults={"debug": True})
    assert conf["debug"]


def test_config_from_dict(fixture_get_config):
    conf = Config()
    conf.from_dict(fixture_get_config)

    assert sorted(conf.items()) == sorted(fixture_get_config.items())


def test_config_from_yaml(fixture_get_config):
    conf = Config()
    conf.from_yaml(TESTCONF_PATH)

    assert sorted(conf.items()) == sorted(fixture_get_config.items())


def test_config_from_str(fixture_get_config):
    conf = Config()
    with open(TESTCONF_PATH, "r") as conf_file:
        conf.from_str(conf_file.read())

    assert sorted(conf.items()) == sorted(fixture_get_config.items())
