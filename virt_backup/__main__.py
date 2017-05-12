#!/usr/bin/env python3

import argparse
import libvirt
import logging
import sys
import threading

from .groups import groups_from_dict, BackupGroup, complete_groups_from_dict
from .config import get_config, Config
from . import APP_NAME, VERSION


logging.basicConfig(level=logging.DEBUG)


def parse_args():
    parser = argparse.ArgumentParser(
        description="Backup and restore your kvm libvirt domains"
    )

    # Start/Stop/Show command
    sp_action = parser.add_subparsers()

    sp_backup = sp_action.add_parser("backup", help=("backup groups"))
    sp_backup.add_argument("groups", metavar="group", type=str, nargs="*",
                           help="domain group to backup")
    sp_backup.set_defaults(func=start_backups)

    sp_clean = sp_action.add_parser("clean", help=("clean groups"))
    sp_clean.add_argument("groups", metavar="group", type=str, nargs="*",
                          help="domain group to clean")
    sp_clean.set_defaults(func=clean_backups)

    sp_clean = sp_action.add_parser("list", help=("list groups"))
    sp_clean.add_argument("groups", metavar="group", type=str, nargs="*",
                          help="domain group to clean")
    sp_clean.add_argument("-s", "--short",
                          help="short version, do not print details",
                          dest="short", action="store_true")
    sp_clean.set_defaults(func=list_groups)

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
    groups = get_usable_complete_groups(config, parsed_args.groups)
    for g in groups:
        g.scan_backup_dir()
        current_group_config = config.get_groups()[g.name]
        clean_params = {
            "hourly": current_group_config.get("hourly", "*"),
            "daily": current_group_config.get("daily", "*"),
            "weekly": current_group_config.get("weekly", "*"),
            "monthly": current_group_config.get("monthly", "*"),
            "yearly": current_group_config.get("yearly", "*"),
        }
        print("Backups removed for group {}: {}".format(
            g.name or "Undefined", len(g.clean(**clean_params))
        ))


def list_groups(parsed_args, *args, **kwargs):
    config = get_setup_config()
    groups = get_usable_complete_groups(config, parsed_args.groups)
    for g in groups:
        g.scan_backup_dir()
        print(" {}\n{}\n".format(g.name, (2 + len(g.name))*"="))
        print("Total backups: {} hosts, {} backups".format(
            len(g.backups), sum(len(backups) for backups in g.backups.values())
        ))
        if not parsed_args.short:
            print("Hosts:")
            # TODO: Should also print hosts matching in libvirt but not backup
            # yet
            for dom, backups in g.backups.items():
                print("\t{}: {} backup(s)".format(dom, len(backups)))


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


def get_usable_complete_groups(config, only_groups_in=None):
    groups = complete_groups_from_dict(config.get_groups())
    for g in groups:
        if not g.backup_dir:
            continue
        elif only_groups_in and g.name not in only_groups_in:
            continue
        yield g


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
