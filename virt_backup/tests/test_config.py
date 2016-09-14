
import pytest

import os
import yaml

from virt_backup import config

CUR_PATH = os.path.dirname(os.path.realpath(__file__))


def test_get_config():
    config.CONFIG_DIRS = (
        (os.path.join(CUR_PATH, "testconfig"), ) + config.CONFIG_DIRS
    )
    conf = config.get_config()
    with open(os.path.join(config.CONFIG_DIRS[0], "config.yml"), "r") as f:
        expected_conf = yaml.safe_load(f)

    assert conf == expected_conf


def test_get_config_custom_path():
    testconf_path = os.path.join(CUR_PATH, "testconfig", "config.yml")
    conf = config.get_config(custom_path=testconf_path)
    with open(testconf_path, "r") as f:
        expected_conf = yaml.safe_load(f)

    assert conf == expected_conf


def test_get_config_not_existing(tmpdir):
    target_dir = tmpdir.mkdir("no_config")
    testconf_path = str(target_dir.join("config.yml"))

    with pytest.raises(FileNotFoundError):
        config.get_config(custom_path=testconf_path)
