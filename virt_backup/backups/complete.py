import arrow
import defusedxml.lxml
import logging
import lxml.etree
import os
import shutil
import tarfile

from virt_backup.backups.packagers import ReadBackupPackagers, WriteBackupPackagers
from virt_backup.compat_layers.definition import convert as compat_convert_definition
from virt_backup.domains import get_domain_disks_of
from virt_backup.exceptions import DomainRunningError
from virt_backup.tools import copy_file
from . import _BaseDomBackup


logger = logging.getLogger("virt_backup")


def build_dom_complete_backup_from_def(
    definition, backup_dir, definition_filename=None
):
    compat_convert_definition(definition)
    backup = DomCompleteBackup(
        name=definition["name"],
        dom_name=definition["domain_name"],
        backup_dir=backup_dir,
        date=arrow.get(definition["date"]),
        dom_xml=definition.get("domain_xml", None),
        disks=definition.get("disks", None),
        packager=definition["packager"]["type"],
        packager_opts=definition["packager"].get("opts", {}),
    )

    if definition_filename:
        backup.definition_filename = definition_filename

    return backup


class DomCompleteBackup(_BaseDomBackup):
    def __init__(
        self,
        name,
        dom_name,
        backup_dir,
        date=None,
        dom_xml=None,
        disks=None,
        packager="tar",
        packager_opts=None,
        definition_filename=None,
    ):
        #: domain name
        self.dom_name = dom_name

        #: backup directory path
        self.backup_dir = backup_dir

        #: definition filename
        self.definition_filename = definition_filename

        #: name is the backup name. It is used by the packagers and internal process.
        self.name = name

        #: backup date
        self.date = date

        #: domain XML as it was during the backup
        self.dom_xml = dom_xml

        #: packager name
        self.packager = packager if packager else "directory"

        #: packager options arguments used during compression
        self.packager_opts = packager_opts or {}

        #: expected format: {disk_name1: filename1, disk_name2: filename2, …}
        self.disks = disks

    def restore_replace_domain(self, conn, id=None):
        """
        :param conn: libvirt connection to the hypervisor
        :param id: new id for the restored domain
        """
        dom_xml = self._get_dom_xml_with_other_id(id) if id else self.dom_xml
        return conn.defineXML(dom_xml)

    def _get_dom_xml_with_other_id(self, id):
        parsed_dxml = self._parse_dom_xml()
        parsed_dxml.set("id", str(id))

        return lxml.etree.tostring(parsed_dxml, pretty_print=True).decode()

    def _parse_dom_xml(self):
        return defusedxml.lxml.fromstring(self.dom_xml)

    def restore_and_replace_disk_of(self, disk, domain, disk_to_replace):
        """
        Restore a disk by replacing an old disks

        :param disk: disk name
        :param domain: domain to target
        :param disk_to_replace: which disk of `domain` to replace
        """
        self._ensure_domain_not_running(domain)
        disk_target_path = get_domain_disks_of(domain.XMLDesc(), disk_to_replace)[disk][
            "src"
        ]

        # TODO: restore disk with a correct extension, and not by keeping the
        #       old disk one
        result = self.restore_disk_to(disk, disk_target_path)
        self._copy_disk_driver_with_domain(disk, domain, disk_to_replace)
        return result

    def _ensure_domain_not_running(self, domain):
        if domain.isActive():
            raise DomainRunningError(domain)

    def _copy_disk_driver_with_domain(self, disk, domain, domain_disk):
        disk_xml = self._get_elemxml_of_domain_disk(self._parse_dom_xml(), disk)
        domain_xml = defusedxml.lxml.fromstring(domain.XMLDesc())
        domain_disk_xml = self._get_elemxml_of_domain_disk(domain_xml, domain_disk)

        domain_disk_xml.replace(
            domain_disk_xml.xpath("driver")[0], disk_xml.xpath("driver")[0]
        )

    def _get_elemxml_of_domain_disk(self, dom_xml, disk):
        for elem in dom_xml.xpath("devices/disk"):
            try:
                if elem.get("device", None) == "disk":
                    dev = elem.xpath("target")[0].get("dev")
                    if dev == disk:
                        return elem
            except IndexError:
                continue

    def restore_to(self, target):
        if not os.path.exists(target):
            os.makedirs(target)

        # TODO: store the original images names in the definition file
        disks_src = get_domain_disks_of(self.dom_xml)
        for d in self.disks:
            original_img_name = os.path.basename(disks_src[d]["src"])
            self.restore_disk_to(d, os.path.join(target, original_img_name))
        xml_path = "{}.xml".format(os.path.join(target, self.dom_name))
        with open(xml_path, "w") as xml_file:
            xml_file.write(self.dom_xml)

    def restore_disk_to(self, disk, target):
        """
        :param disk: disk name
        :param target: destination path for the restoration
        """
        packager = self._get_packager()
        with packager:
            return packager.restore(self.disks[disk], target)

    def _get_packager(self):
        return self._get_read_packager(self.name)

    def _get_write_packager(self):
        return super()._get_write_packager(self.name)

    def delete(self):
        if not self.backup_dir:
            raise Exception("Backup dir not defined, cannot clean backup")

        packager = self._get_write_packager()
        self._clean_packager(packager, self.disks.values())
        if self.definition_filename:
            os.remove(self.get_complete_path_of(self.definition_filename))
