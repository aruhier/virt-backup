import logging
import lxml.etree

from packaging.version import parse as version_parser

from virt_backup.domains import get_xml_block_of_disk
from . import definition as definition_compat


logger = logging.getLogger("virt_backup")


def convert(pending_info):
    converters = (ToV0_4(), V0_4ToV0_5_2())
    for c in converters:
        def_version = version_parser(pending_info["version"])
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


class V0_4ToV0_5_2(PendingInfoConverter):
    from_version_to = ("0.4.0", "0.5.2")
    _parsed_versions = (version_parser("0.4.0"), version_parser("0.5.2"))

    def convert(self, pending_info):
        pending_info["version"] = self.from_version_to[1]

        for disk, prop in pending_info.get("disks", dict()).items():
            if "type" not in prop:
                break
        else:
            # All disks have a type set, no need to convert.
            return

        dom_xml = lxml.etree.fromstring(
            pending_info["domain_xml"], lxml.etree.XMLParser(resolve_entities=False)
        )

        for disk, prop in pending_info.get("disks", dict()).items():
            if "type" in prop:
                continue

            disk_xml = get_xml_block_of_disk(dom_xml, disk)
            prop["type"] = disk_xml.xpath("driver")[0].get("type")
