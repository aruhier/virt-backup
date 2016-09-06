#!/usr/bin/env python3

import errno
import logging
import os
import yaml


logger = logging.getLogger("virt_backup")


class Config(dict):
    """
    Works like a dict but can be filled directly from a yaml configuration
    file. Inspired from the Flask Config class (a part of their code has been
    copied here).

    :param defaults: an optional dictionary of default values
    """
    def __init__(self, root_path, defaults=None):
        dict.__init__(self, defaults or {})
        self.refresh_global_logger_lvl()

    def refresh_global_logger_lvl(self):
        if self["debug"]:
            logging.getLogger("virt_backup").setLevel(logging.DEBUG)

    def from_dict(self, conf_dict):
        """
        Copy values from dict
        """
        self.update(conf_dict)

    def from_str(self, conf_str):
        """
        Read configuration from string
        """
        self.from_dict(yaml.load(conf_str))

    def from_yaml(self, filename, silent=False):
        """
        Updates the values in the config from a yaml file.  This function
        behaves as if the file was imported as module with the
        :meth:`from_object` function.

        :param filename: the filename of the config.  This can either be an
                         absolute filename or a filename relative to the
                         root path.
        :param silent: set to ``True`` if you want silent failure for missing
                       files.
        """
        filename = os.path.join(self.root_path, filename)
        try:
            with open(filename) as conf_yaml:
                self.from_dict(yaml.load(conf_yaml))
        except IOError as e:
            if silent and e.errno in (errno.ENOENT, errno.EISDIR):
                return False
            e.strerror = 'Unable to load configuration file (%s)' % e.strerror
            raise
        return True
