#!/usr/bin/env python3

import argparse
import libvirt
import logging
import sys
import threading

from .group import groups_from_dict, BackupGroup
from .config import get_config, Config
from . import APP_NAME, VERSION


logging.basicConfig(level=logging.DEBUG)


def parse_args():
    parser = argparse.ArgumentParser(
        description="Backup and restore your kvm libvirt domains"
    )

    # Start/Stop/Show command
    sp_action = parser.add_subparsers()

    sp_backup = sp_action.add_parser("backup", help=("backup a group"))
    sp_backup.add_argument("groups", metavar="group", type=str, nargs="*",
                           help="domain group to backup")
    sp_backup.set_defaults(func=start_backups)

    # Debug option
    parser.add_argument("-d", "--debug", help="set the debug level",
                        dest="debug", action="store_true")
    parser.add_argument(
        "--version", action="version",
        version="{} {}".format(APP_NAME, VERSION)
    )
    arg_parser = parser

    # Parse argument
    args = arg_parser.parse_args()

    if args.debug:
        logging.basicConfig(level=logging.DEBUG)

    # Execute correct function, or print usage
    if hasattr(args, "func"):
        args.func(parsed_args=args)
    else:
        arg_parser.print_help()
        sys.exit(1)


def start_backups(parsed_args, *args, **kwargs):
    vir_event_loop_native_start()

    config = get_setup_config()
    conn = get_setup_conn(config)

    if config.get("groups", None):
        groups = build_all_or_selected_groups(config, conn, parsed_args.groups)
        main_group = build_main_backup_group(groups)
        main_group.start()


def vir_event_loop_native_start():
    libvirt.virEventRegisterDefaultImpl()
    eventLoopThread = threading.Thread(
        target=vir_event_loop_native_run, name="libvirtEventLoop"
    )
    eventLoopThread.setDaemon(True)
    eventLoopThread.start()


def vir_event_loop_native_run():
    while True:
        libvirt.virEventRunDefaultImpl()


def build_main_backup_group(groups):
    main_group = BackupGroup()
    for g in groups:
        for d in g.backups:
            main_group.add_dombackup(d)
    return main_group


def clean_backups(parsed_args, *args, **kwargs):
    config = get_setup_config()
    # use CompleteBackupGroups


def get_setup_config():
    config = Config(defaults={"debug": False, })
    try:
        config.from_dict(get_config())
    except FileNotFoundError:
        sys.exit(1)
    return config


def get_setup_conn(config):
    conn = libvirt.open(config["uri"])
    if conn is None:
        print('Failed to open connection to the hypervisor')
        sys.exit(1)
    conn.setKeepAlive(5, 3)
    return conn


def build_all_or_selected_groups(config, conn, groups=None):
    if not groups:
        groups = [g for g in groups_from_dict(config["groups"], conn)
                  if g.autostart]
    else:
        groups = [g for g in groups_from_dict(config["groups"], conn)
                  if g.name in groups]
    return groups


if __name__ == "__main__":
    parse_args()
