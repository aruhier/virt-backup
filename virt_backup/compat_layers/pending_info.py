import logging

from packaging.version import parse as version_parser

from . import definition as definition_compat


logger = logging.getLogger("virt_backup")


def convert(pending_info):
    def_version = version_parser(pending_info["version"])
    converters = (ToV0_4(),)
    for c in converters:
        if c.is_needed(def_version):
            logger.debug(
                "pending_info %s needs convertion update to v%s",
                pending_info.get("name") or pending_info["domain_name"],
                c.from_version_to[1],
            )
            c.convert(pending_info)


class PendingInfoConverter(definition_compat.DefConverter):
    pass


class ToV0_4(definition_compat.ToV0_4):
    pass
