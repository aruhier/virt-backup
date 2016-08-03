#!/usr/bin/env python3

import libvirt
import logging
import sys
import time
import threading

from .virt_backup import DomBackup


logging.basicConfig(level=logging.DEBUG)


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


def start_backup():
    virEventLoopNativeStart()
    conn = libvirt.open(None)
    if conn is None:
        print('Failed to open connection to the hypervisor')
        sys.exit(1)

    try:
        dom0 = conn.lookupByName(GUEST_TEST_NAME)
    except:
        print('Failed to find the main domain')
        sys.exit(1)

    dbkup = DomBackup(dom0, target_dir="/mnt/kvm/backups", conn=conn)
    dbkup.start()

    conn.setKeepAlive(5, 3)
    while True:
        time.sleep(1)


if __name__ == "__main__":
    start_backup()
