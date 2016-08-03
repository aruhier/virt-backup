#!/usr/bin/env python3

import datetime
import defusedxml.lxml
import libvirt
import lxml.etree
import os
import threading
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
        disks = {}
        for elem in dom_xml.xpath("devices/disk"):
            try:
                if elem.get("device", None) == "disk":
                    dev = elem.xpath("target")[0].get("dev")
                    src = elem.xpath("source")[0].get("file")
                    disk_type = elem.xpath("driver")[0].get("type")

                    disks[dev] = {"src": src, "type": disk_type}
            except IndexError:
                continue
        return disks

    def backup_img(self, disk, target, compress=False):
        copy_file_progress(disk, target, buffersize=10*1024*1024)
        print("backup ok")

    def pivot_callback(self, conn, dom, disk, event_id, status, *args):
        domain_matches = dom.ID() == self.dom.ID()
        if status == libvirt.VIR_DOMAIN_BLOCK_JOB_READY and domain_matches:
            dom.blockJobAbort(disk, libvirt.VIR_DOMAIN_BLOCK_JOB_ABORT_PIVOT)
            os.remove(disk)
            self._wait_for_pivot.set()

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
        for d in sorted(self.disks.keys()):
            disk_el = lxml.etree.Element("disk")
            disk_el.attrib["name"] = d
            disk_el.attrib["snapshot"] = "external"
            disks_el.append(disk_el)

        return lxml.etree.tostring(xml_tree, pretty_print=True).decode()

    def external_snapshot(self):
        snap_xml = self.gen_snapshot_xml()
        self.dom.snapshotCreateXML(
            snap_xml,
            (
                libvirt.VIR_DOMAIN_SNAPSHOT_CREATE_DISK_ONLY +
                libvirt.VIR_DOMAIN_SNAPSHOT_CREATE_ATOMIC +
                libvirt.VIR_DOMAIN_SNAPSHOT_CREATE_NO_METADATA
            )
        )

    def start(self):
        self._wait_for_pivot.clear()
        try:
            callback_id = self.conn.domainEventRegisterAny(
                None, libvirt.VIR_DOMAIN_EVENT_ID_BLOCK_JOB,
                self.pivot_callback, None
            )
            self.external_snapshot()
            # TODO: handle backingStore cases
            # TODO: maybe we should tar everything + put the xml into it?
            for disk, prop in self.disks.items():
                # TODO: allow a user to set the format
                target_img = os.path.join(
                    self.target_dir, "{}-{}-{}.{}".format(
                        self.dom.name(), disk,
                        datetime.datetime.now().strftime("%Y%m%d-%H%M"),
                        prop["type"]
                    )
                )
                self.backup_img(prop["src"], target_img)
                self.dom.blockCommit(
                    disk, None, None, 0,
                    (
                        libvirt.VIR_DOMAIN_BLOCK_COMMIT_ACTIVE +
                        libvirt.VIR_DOMAIN_BLOCK_COMMIT_SHALLOW
                    )
                )
                # TODO: setup a timeout here
                self._wait_for_pivot.wait()
        finally:
            #: TODO: block this step with an event
            self.conn.domainEventDeregisterAny(callback_id)

    def __init__(self, dom, target_dir=None, disks=None, conn=None):
        self.dom = dom
        self.conn = self.dom._conn if conn is None else conn
        self.target_dir = target_dir
        self.disks = self._get_disks() if disks is None else disks
        self._wait_for_pivot = threading.Event()
