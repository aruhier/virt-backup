#!/usr/bin/env python3

import defusedxml
import libvirt
import lxml
import os
from virt_backup.tools import copy_file_progress


class DomBackup():
    """
    Libvirt domain backup
    """
    def _parse_xml(self):
        """
        Parse the domain's definition
        """
        return defusedxml.lxml.fromstring(self.dom.XMLDesc())

    def _get_disks(self):
        """
        Get disks from the domain xml
        """
        dom_xml = self._parse_xml()
        for elem in dom_xml.xpath("devices/disk"):
            try:
                if elem.get("device", None) == "disk":
                    yield elem.xpath("target")[0].get("dev")
            except IndexError:
                continue

    def backup_img(self, disk, target, compress=False):
        print("start backup")
        copy_file_progress(disk, target)
        print("backup over")

    def pivot_callback(self, conn, dom, disk, event_id, status, *args):
        domain_matches = dom.ID() == self.dom.ID()
        if status == libvirt.VIR_DOMAIN_BLOCK_JOB_READY and domain_matches:
            print(disk)
            self.backup_img(disk, "/mnt/kvm/backups/{}.qcow2".format(dom.ID()))
            dom.blockJobAbort(disk, libvirt.VIR_DOMAIN_BLOCK_JOB_ABORT_PIVOT)
            os.remove(disk)
            print("done")

    def gen_snapshot_xml(self):
        """
        Generate a xml defining the snapshot
        """
        root_el = lxml.etree.Element("domainsnapshot")
        xml_tree = root_el.getroottree()

        descr_el = lxml.etree.Element("description")
        root_el.append(descr_el)
        descr_el.text = "Pre-backup external snapshot"

        disks_el = lxml.etree.Element("disks")
        root_el.append(disks_el)
        for d in self.disks:
            disk_el = lxml.etree.Element("disk")
            disk_el.attrib["name"] = d
            disk_el.attrib["snapshot"] = "external"
            disks_el.append(disk_el)

        return lxml.etree.tostring(xml_tree, pretty_print=True)

    def external_snapshot(self):
        snap_xml = self.gen_snapshot_xml()
        try:
            self.dom.snapshotCreateXML(
                snap_xml,
                (
                    libvirt.VIR_DOMAIN_SNAPSHOT_CREATE_DISK_ONLY +
                    libvirt.VIR_DOMAIN_SNAPSHOT_CREATE_ATOMIC +
                    libvirt.VIR_DOMAIN_SNAPSHOT_CREATE_NO_METADATA
                )
            )
        except:
            print("Backup already exists, pass…")

    def start(self):
        event_register_args = (
            None, libvirt.VIR_DOMAIN_EVENT_ID_BLOCK_JOB, self.pivot_callback,
            None
        )
        try:
            self.conn.domainEventRegisterAny(*event_register_args)
            self.external_snapshot()
            for disk in self.disks:
                self.backup_img(disk, self.target_dir)
                self.dom.blockCommit(
                    disk, None, None, 0,
                    (
                        libvirt.VIR_DOMAIN_BLOCK_COMMIT_ACTIVE +
                        libvirt.VIR_DOMAIN_BLOCK_COMMIT_SHALLOW
                    )
                )
        finally:
            #: TODO: block this step with an event
            self.conn.domainEventDeregisterAny(*event_register_args)

    def __init__(self, dom, target_dir=None, disks=None, conn=None):
        self.dom = dom
        self.conn = self.dom._conn if conn is None else conn
        self.target_dir = target_dir
        self.disks = self._get_disks() if disks is None else disks
