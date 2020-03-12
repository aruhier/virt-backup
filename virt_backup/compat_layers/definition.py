from abc import ABC, abstractmethod
import logging
import re

import arrow
from packaging.version import parse as version_parser
import yaml


logger = logging.getLogger("virt_backup")


def convert(definition):
    def_version = version_parser(definition["version"])
    converters = (ToV0_4(),)
    for c in converters:
        if c.is_needed(def_version):
            logger.debug(
                "definition %s needs convertion update to v%s",
                definition.get("name") or definition["domain_name"],
                c.from_version_to[1],
            )
            c.convert(definition)


class DefConverter(ABC):
    from_version_to = ()
    _parsed_versions = ()

    @abstractmethod
    def convert(self, config):
        pass

    def is_needed(self, def_parsed_version):
        return self._parsed_versions[0] <= def_parsed_version < self._parsed_versions[1]


class ToV0_4(DefConverter):
    """
    Convert from v0.1 to v0.4
    """

    from_version_to = ("0.1.0", "0.4.0")
    _parsed_versions = (version_parser("0.1.0"), version_parser("0.4.0"))

    def convert(self, definition):
        self.convert_compression(definition)
        self.convert_name(definition)
        definition["version"] = self.from_version_to[1]

    def convert_compression(self, definition):
        if "compression" in definition:
            old_compression = definition.pop("compression")
            new_packager = ""
            new_packager_opts = {}

            if old_compression is None:
                new_packager = "directory"
            else:
                new_packager = "tar"
                if old_compression != "tar":
                    new_packager_opts["compression"] = old_compression

            definition["packager"] = {
                "type": new_packager,
                "opts": new_packager_opts or {},
            }
        elif "packager" not in definition:
            definition["packager"] = {"type": "directory", "opts": {}}

        if "compression_lvl" in definition:
            compression_lvl = definition.pop("compression_lvl")
            definition["packager"]["opts"]["compression_lvl"] = compression_lvl

    def convert_name(self, definition):
        if "tar" in definition:
            archive_name_search = re.match(r"(.*)\.tar\.?.*$", definition["tar"])
            if archive_name_search:
                definition["name"] = archive_name_search.group(1)
            else:
                definition["name"] = definition["tar"]
            definition.pop("tar")

        if "name" not in definition:
            snapdate = arrow.get(definition["date"])
            str_snapdate = snapdate.strftime("%Y%m%d-%H%M%S")
            definition["name"] = "{}_{}_{}".format(
                str_snapdate, definition["domain_id"], definition["domain_name"]
            )
