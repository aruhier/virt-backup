#!/usr/bin/env python3

import libvirt
import os
from virt_backup.tools import copy_file_progress


def backup_img(disk, target, compress=False):
    print("start backup")
    copy_file_progress(disk, target)
    print("over")


def pivot_callback(conn, dom, disk, event_id, status, *args):
    if status == libvirt.VIR_DOMAIN_BLOCK_JOB_READY:
        print(disk)
        backup_img(disk, "/mnt/kvm/backups/{}.qcow2".format(dom.ID()))
        dom.blockJobAbort(disk, libvirt.VIR_DOMAIN_BLOCK_JOB_ABORT_PIVOT)
        os.remove(disk)
        print("done")
