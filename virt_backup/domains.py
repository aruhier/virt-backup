import logging
import re
import lxml.etree

from virt_backup.exceptions import DiskNotFoundError


logger = logging.getLogger("virt_backup")


def get_domain_disks_of(dom_xml, *filter_dev):
    """
    Get disks from the domain xml

    :param dom_xml: domain xml to extract the disks from
    :param filter_dev: return only disks for which the dev name matches
                       with one in filter_dev. If no parameter, will return
                       every disks.
    """
    if isinstance(dom_xml, str):
        dom_xml = lxml.etree.fromstring(
            dom_xml, lxml.etree.XMLParser(resolve_entities=False)
        )
    filter_dev = sorted(list(filter_dev))
    disks = {}
    for elem in dom_xml.xpath("devices/disk"):
        try:
            if elem.get("device", None) != "disk":
                continue

            if elem.get("type", None) != "file":
                logger.debug(
                    "Disk %s is not a file, which not compatible with virt-backup",
                    elem.xpath("target")[0].get("dev"),
                )
                continue

            dev = elem.xpath("target")[0].get("dev")
            if filter_dev and dev not in filter_dev:
                continue
            src = elem.xpath("source")[0].get("file")
            disk_type = elem.xpath("driver")[0].get("type")

            disks[dev] = {"src": src, "type": disk_type}

            # all disks captured
            if filter_dev in list(sorted(disks.keys())):
                break
        except IndexError:
            continue

    for disk in filter_dev:
        if disk not in disks:
            raise DiskNotFoundError(disk)

    return disks


def get_domain_incompatible_disks_of(dom_xml, *filter_dev):
    """
    Get incompatible (non snapshotable) disks from the domain xml

    :param dom_xml: domain xml to extract the disks from
    """
    if isinstance(dom_xml, str):
        dom_xml = lxml.etree.fromstring(
            dom_xml, lxml.etree.XMLParser(resolve_entities=False)
        )
    disks = []
    for elem in dom_xml.xpath("devices/disk"):
        try:
            if elem.get("device", None) != "disk":
                continue

            if elem.get("type", None) == "file":
                continue

            dev = elem.xpath("target")[0].get("dev")
            disks.append(dev)
        except IndexError:
            continue

    return tuple(sorted(disks))


def get_xml_block_of_disk(dom_xml, disk):
    if isinstance(dom_xml, str):
        dom_xml = lxml.etree.fromstring(
            dom_xml, lxml.etree.XMLParser(resolve_entities=False)
        )
    for elem in dom_xml.xpath("devices/disk"):
        try:
            if elem.get("device", None) == "disk":
                dev = elem.xpath("target")[0].get("dev")
                if dev == disk:
                    return elem
        except IndexError:
            continue
    raise DiskNotFoundError(disk)


def search_domains_regex(pattern, conn):
    """
    Yield all domains matching with a regex

    :param pattern: regex to match on all domain names listed by libvirt
    :param conn: connection with libvirt
    """
    c_pattern = re.compile(pattern)
    for domain in conn.listAllDomains():
        domain_name = domain.name()
        if c_pattern.match(domain_name):
            yield domain_name
