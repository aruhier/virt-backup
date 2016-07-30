#!/usr/bin/env python3

import libvirt
import threading
import os
import sys
import time
from tqdm import tqdm


# Domain id used to test the result
GUEST_TEST_NAME = "ubuntu15.10"


def virEventLoopNativeRun():
    while True:
        libvirt.virEventRunDefaultImpl()


def virEventLoopNativeStart():
    libvirt.virEventRegisterDefaultImpl()
    eventLoopThread = threading.Thread(
        target=virEventLoopNativeRun, name="libvirtEventLoop"
    )
    eventLoopThread.setDaemon(True)
    eventLoopThread.start()


def copy_file_progress(src, dst, buffersize=512*1024):
    total_size = os.path.getsize(src)
    if not os.path.exists(dst) and dst.endswith("/"):
        os.mkdir(dst)
    if os.path.isdir(dst):
        dst = os.path.join(dst, os.basename(src))

    # Load tqdm with size counter instead of files counter
    with tqdm(total=total_size, unit='B', unit_scale=True, ncols=0) as pbar, \
            open(src, "rb") as fsrc, open(dst, "wb") as fdst:
        while True:
            buf = fsrc.read(buffersize)
            if not buf:
                break
            fdst.write(buf)
            pbar.update(len(buf))


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

virEventLoopNativeStart()
conn = libvirt.open(None)
if conn is None:
    print('Failed to open connection to the hypervisor')
    sys.exit(1)
conn.domainEventRegisterAny(None, libvirt.VIR_DOMAIN_EVENT_ID_BLOCK_JOB,
                            pivot_callback, None)

try:
    dom0 = conn.lookupByName(GUEST_TEST_NAME)
except:
    print('Failed to find the main domain')
    sys.exit(1)

print("Domain 0: id %d running %s" % (dom0.ID(), dom0.OSType()))
print(dom0.info())

with open("snaptest.xml") as snap:
    snap_xml = "".join(snap.readlines())
try:
    dom0.snapshotCreateXML(
        snap_xml,
        (
            libvirt.VIR_DOMAIN_SNAPSHOT_CREATE_DISK_ONLY +
            libvirt.VIR_DOMAIN_SNAPSHOT_CREATE_ATOMIC +
            libvirt.VIR_DOMAIN_SNAPSHOT_CREATE_NO_METADATA
        )
    )
except:
    print("Backup already exists, pass…")
dom0.blockCommit(
    "vda", None, None, 0,
    (
        libvirt.VIR_DOMAIN_BLOCK_COMMIT_ACTIVE +
        libvirt.VIR_DOMAIN_BLOCK_COMMIT_SHALLOW
    )
)

conn.setKeepAlive(5, 3)
while True:
    time.sleep(1)
