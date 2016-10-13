#!/usr/bin/env python3

import libvirt
import logging
import sys
import threading

from .group import groups_from_dict, BackupGroup
from .config import get_config, Config


logging.basicConfig(level=logging.DEBUG)


def vir_event_loop_native_run():
    while True:
        libvirt.virEventRunDefaultImpl()


def vir_event_loop_native_start():
    libvirt.virEventRegisterDefaultImpl()
    eventLoopThread = threading.Thread(
        target=vir_event_loop_native_run, name="libvirtEventLoop"
    )
    eventLoopThread.setDaemon(True)
    eventLoopThread.start()


def build_main_backup_group(groups):
    main_group = BackupGroup()
    for g in groups:
        for d in g.backups:
            main_group.add_dombackup(d)
    return main_group


def start_backups():
    vir_event_loop_native_start()

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
        groups = [g for g in groups_from_dict(config["groups"], conn)
                  if g.autostart]
        main_group = build_main_backup_group(groups)
        main_group.start()


if __name__ == "__main__":
    start_backups()
