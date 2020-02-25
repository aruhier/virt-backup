import errno
import logging
import os
import appdirs
import yaml

from virt_backup import APP_NAME


logger = logging.getLogger("virt_backup")

os.environ["XDG_CONFIG_DIRS"] = "/etc"
CONFIG_DIRS = (
    appdirs.user_config_dir(APP_NAME),
    appdirs.site_config_dir(APP_NAME),
)
CONFIG_FILENAME = "config.yml"


def get_config(custom_path=None):
    """
    Get config file and load it with yaml

    :returns: loaded config in yaml, as a dict object
    """
    if custom_path:
        config_path = custom_path
    else:
        for d in CONFIG_DIRS:
            config_path = os.path.join(d, CONFIG_FILENAME)
            if os.path.isfile(config_path):
                break
    try:
        with open(config_path, "r") as config_file:
            return yaml.safe_load(config_file)
    except FileNotFoundError as e:
        logger.debug(e)
        if custom_path:
            logger.error("Configuration file {} not found.".format(custom_path))
        else:
            logger.error(
                "No configuration file can be found. Please create a "
                "config.yml in one of these directories:\n"
                "{}".format(", ".join(CONFIG_DIRS))
            )
        raise FileNotFoundError


class Config(dict):
    """
    Works like a dict but can be filled directly from a yaml configuration
    file. Inspired from the Flask Config class (a part of their code has been
    copied here).

    :param defaults: an optional dictionary of default values
    """

    def __init__(self, defaults=None):
        dict.__init__(self, defaults or {})
        self.refresh_global_logger_lvl()

    def refresh_global_logger_lvl(self):
        if self.get("debug", None):
            logging.getLogger("virt_backup").setLevel(logging.DEBUG)
        else:
            logging.getLogger("virt_backup").setLevel(logging.INFO)

    def from_dict(self, conf_dict):
        """
        Copy values from dict
        """
        self.update(conf_dict)

    def from_str(self, conf_str):
        """
        Read configuration from string
        """
        self.from_dict(yaml.safe_load(conf_str))

    def from_yaml(self, filename, silent=False):
        """
        Updates the values in the config from a yaml file.

        :param filename: filename of the config.
        :param silent: set to ``True`` if you want silent failure for missing
                       files.
        """
        filename = os.path.join(filename)
        try:
            with open(filename) as conf_yaml:
                self.from_dict(yaml.safe_load(conf_yaml))
        except IOError as e:
            if silent and e.errno in (errno.ENOENT, errno.EISDIR):
                return False
            e.strerror = "Unable to load configuration file (%s)" % e.strerror
            raise
        return True

    def get_groups(self):
        """
        Get backup groups with default values
        """
        groups = {}
        for g, prop in self.get("groups", {}).items():
            d = self.get("default", {}).copy()
            d.update(prop)
            groups[g] = d
        return groups
