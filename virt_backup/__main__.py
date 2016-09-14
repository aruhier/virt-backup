#!/usr/bin/env python3

import libvirt
import logging
import sys
import threading

from .virt_backup import groups_from_dict
from .config import get_config, Config


logging.basicConfig(level=logging.DEBUG)


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


def start_backups():
    virEventLoopNativeStart()

    config = Config(defaults={"debug": False, })
    try:
        config.from_dict(get_config())
    except FileNotFoundError:
        sys.exit(1)

    conn = libvirt.open(None)
    if conn is None:
        print('Failed to open connection to the hypervisor')
        sys.exit(1)
    conn.setKeepAlive(5, 3)

    if config.get("groups", None):
        groups = groups_from_dict(config["groups"], conn)
        for g in groups:
            if g.autostart:
                g.start()


if __name__ == "__main__":
    start_backups()
