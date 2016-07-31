#!/usr/bin/env python3

import libvirt
import os
from virt_backup.tools import copy_file_progress


class DomBackup():
    """
    Libvirt domain backup
    """
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
        #: TODO

    def external_snapshot(self):
        snap_xml = self.gen_snapshot_xml()
        try:
            self.domain.snapshotCreateXML(
                snap_xml,
                (
                    libvirt.VIR_DOMAIN_SNAPSHOT_CREATE_DISK_ONLY +
                    libvirt.VIR_DOMAIN_SNAPSHOT_CREATE_ATOMIC +
                    libvirt.VIR_DOMAIN_SNAPSHOT_CREATE_NO_METADATA
                )
            )
        except:
            print("Backup already exists, pass…")

    def start(self, conn):
        event_register_args = (
            None, libvirt.VIR_DOMAIN_EVENT_ID_BLOCK_JOB, self.pivot_callback,
            None
        )
        try:
            conn.domainEventRegisterAny(*event_register_args)
            self.external_snapshot()
            for disk in self.disks:
                self.backup_img(disk, self.target_dir)
                self.domain.blockCommit(
                    disk, None, None, 0,
                    (
                        libvirt.VIR_DOMAIN_BLOCK_COMMIT_ACTIVE +
                        libvirt.VIR_DOMAIN_BLOCK_COMMIT_SHALLOW
                    )
                )
        finally:
            #: TODO: block this step with an event
            conn.domainEventDeregisterAny(*event_register_args)

    def __init__(self, domain, target_dir=None, disks=None):
        self.domain = domain
        self.target_dir = target_dir
        self.disks = [] if disks is None else disks
