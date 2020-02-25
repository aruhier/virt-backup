from abc import ABC, abstractmethod
import os
import yaml
import pytest

from deepdiff import DeepDiff
from virt_backup import config
from virt_backup.compat_layers.config import convert_warn, ToV0_4

CUR_PATH = os.path.dirname(os.path.realpath(__file__))
TESTCONF_PATH = os.path.join(CUR_PATH, "testconfig/versions")


class _BaseTestConfigConverter(ABC):
    @property
    @abstractmethod
    def target(self):
        pass

    @property
    @abstractmethod
    def converter(self):
        pass

    def get_config(self, config_type: str):
        path = os.path.join(TESTCONF_PATH, self.target, "{}.yml".format(config_type))
        return config.get_config(path)

    def test_convert(self):
        pre = self.get_config("pre")
        post = self.get_config("post")

        self.converter.convert(pre)
        diff = DeepDiff(pre, post)
        assert not diff, "diff found between converted config and expected config"


class TestV0_1ToV0_4(_BaseTestConfigConverter):
    target = "0.4"
    converter = ToV0_4()


def test_convert_warn():
    """
    Test conversion from the minimum version supported to the last version supported.
    """
    pre = config.get_config(os.path.join(TESTCONF_PATH, "full", "0.1.yml"))
    post = config.get_config(os.path.join(TESTCONF_PATH, "full", "0.4.yml"))

    convert_warn(pre)
    diff = DeepDiff(pre, post)
    assert not diff, "diff found between converted config and expected config"
