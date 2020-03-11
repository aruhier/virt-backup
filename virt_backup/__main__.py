#!/usr/bin/env python3

import argparse
import arrow
import libvirt
import logging
import sys
import threading
from collections import defaultdict

from virt_backup.exceptions import BackupNotFoundError, BackupsFailureInGroupError
from virt_backup.groups import groups_from_dict, BackupGroup, complete_groups_from_dict
from virt_backup.backups import DomExtSnapshotCallbackRegistrer
from virt_backup.config import get_config, Config
from virt_backup.tools import InfoFilter
from virt_backup import APP_NAME, VERSION, compat_layers


logger = logging.getLogger("virt_backup")


def cli_run():
    return parse_args_and_run(build_parser())


def build_parser():
    parser = argparse.ArgumentParser(
        description="Backup and restore your kvm libvirt domains"
    )

    # Start/Stop/Show command
    sp_action = parser.add_subparsers()

    sp_backup = sp_action.add_parser("backup", aliases=["bak"], help=("backup groups"))
    sp_backup.add_argument(
        "groups", metavar="group", type=str, nargs="*", help="domain group to backup"
    )
    sp_backup.set_defaults(func=start_backups)

    sp_restore = sp_action.add_parser("restore", help=("restore backup"))
    sp_restore.add_argument("group", metavar="group", help="domain group")
    sp_restore.add_argument("domain_name", metavar="domain", help="domain name")
    sp_restore.add_argument(
        "--date", metavar="date", help="backup date (default: last backup)"
    )
    sp_restore.add_argument("target_dir", metavar="target_dir", help="backup date")
    sp_restore.set_defaults(func=restore_backup)

    sp_clean = sp_action.add_parser("clean", aliases=["cl"], help=("clean groups"))
    sp_clean.add_argument(
        "groups", metavar="group", type=str, nargs="*", help="domain group to clean"
    )
    sp_clean_broken_opts = sp_clean.add_mutually_exclusive_group()
    sp_clean_broken_opts.add_argument(
        "-b",
        "--broken-only",
        help="only clean broken backups",
        dest="broken_only",
        action="store_true",
    )
    sp_clean_broken_opts.add_argument(
        "-B",
        "--no-broken",
        help="do not clean broken backups",
        dest="no_broken",
        action="store_true",
    )
    sp_clean.set_defaults(func=clean_backups)

    sp_list = sp_action.add_parser("list", aliases=["ls"], help=("list groups"))
    sp_list.add_argument(
        "groups", metavar="group", type=str, nargs="*", help="domain group to clean"
    )
    sp_list.add_argument(
        "-D",
        "--domain",
        metavar="domain_name",
        dest="domains_names",
        action="append",
        default=[],
        help="show list of backups for specific domain",
    )
    sp_list.add_argument(
        "-a",
        "--all",
        help="show all domains matching, even without backup",
        dest="list_all",
        action="store_true",
    )
    sp_list.add_argument(
        "-s",
        "--short",
        help="short version, do not print details",
        dest="short",
        action="store_true",
    )
    sp_list.set_defaults(func=list_groups)

    # Debug option
    parser.add_argument(
        "-d",
        "--debug",
        help="enable debug, verbose output",
        dest="debug",
        action="store_true",
    )
    parser.add_argument(
        "--version", action="version", version="{} {}".format(APP_NAME, VERSION)
    )

    return parser


def parse_args_and_run(parser):
    # Parse argument
    args = parser.parse_args()

    stdout_handler = logging.StreamHandler(sys.stdout)
    stdout_handler.setLevel(logging.DEBUG)
    stdout_handler.addFilter(InfoFilter())

    stderr_handler = logging.StreamHandler()
    stderr_handler.setLevel(logging.WARNING)
    log_handlers = (stdout_handler, stderr_handler)

    if args.debug:
        logging.basicConfig(
            level=logging.DEBUG,
            format="%(levelname)s:%(name)s:%(message)s",
            handlers=log_handlers,
        )
    else:
        logging.basicConfig(
            level=logging.INFO, format="%(message)s", handlers=log_handlers
        )

    # Execute correct function, or print usage
    if hasattr(args, "func"):
        args.func(parsed_args=args)
    else:
        parser.print_help()
        sys.exit(1)


def start_backups(parsed_args, *args, **kwargs):
    vir_event_loop_native_start()

    config = get_setup_config()
    conn = get_setup_conn(config)
    callbacks_registrer = DomExtSnapshotCallbackRegistrer(conn)

    if config.get("groups", None):
        groups = build_all_or_selected_groups(
            config, conn, callbacks_registrer, parsed_args.groups
        )
        main_group = build_main_backup_group(groups)
        nb_threads = config.get("threads", 0)
        try:
            try:
                with callbacks_registrer:
                    if nb_threads > 1 or nb_threads == 0:
                        main_group.start_multithread(nb_threads=nb_threads)
                    else:
                        main_group.start()
            except BackupsFailureInGroupError as e:
                logger.error(e)
                sys.exit(2)
        except KeyboardInterrupt:
            print("Cancelled…")
            sys.exit(1)


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


def restore_backup(parsed_args, *args, **kwargs):
    vir_event_loop_native_start()

    config = get_setup_config()
    conn = get_setup_conn(config)
    callbacks_registrer = DomExtSnapshotCallbackRegistrer(conn)
    try:
        group = next(
            get_usable_complete_groups(
                config, [parsed_args.group], conn, callbacks_registrer
            )
        )
    except StopIteration:
        logger.critical("Group {} not found".format(parsed_args.group))
        sys.exit(1)
    group.scan_backup_dir()

    domain_name = parsed_args.domain_name
    target_dir = parsed_args.target_dir
    target_date = arrow.get(parsed_args.date) if parsed_args.date else None

    if target_date:
        backup = group.get_backup_at_date(domain_name, target_date)
    else:
        try:
            backup = group.backups[domain_name][-1]
        except KeyError:
            raise BackupNotFoundError

    with callbacks_registrer:
        backup.restore_to(target_dir)


def clean_backups(parsed_args, *args, **kwargs):
    vir_event_loop_native_start()

    config = get_setup_config()
    conn = get_setup_conn(config)
    callbacks_registrer = DomExtSnapshotCallbackRegistrer(conn)
    groups = get_usable_complete_groups(
        config, parsed_args.groups, conn, callbacks_registrer
    )

    with callbacks_registrer:
        for g in groups:
            g.scan_backup_dir()
            current_group_config = config.get_groups()[g.name]
            clean_params = {
                "hourly": current_group_config.get("hourly", 5),
                "daily": current_group_config.get("daily", 5),
                "weekly": current_group_config.get("weekly", 5),
                "monthly": current_group_config.get("monthly", 5),
                "yearly": current_group_config.get("yearly", 5),
            }
            for k, v in clean_params.items():
                if v is None:
                    clean_params[k] = "*"

            if not parsed_args.broken_only:
                print(
                    "Backups removed for group {}: {}".format(
                        g.name or "Undefined", len(g.clean(**clean_params))
                    )
                )
            if not parsed_args.no_broken:
                print(
                    "Broken backups removed for group {}: {}".format(
                        g.name or "Undefined", len(g.clean_broken_backups())
                    )
                )


def list_groups(parsed_args, *args, **kwargs):
    vir_event_loop_native_start()
    config = get_setup_config()
    conn = get_setup_conn(config)
    callbacks_registrer = DomExtSnapshotCallbackRegistrer(conn)

    complete_groups = {g.name: g for g in get_usable_complete_groups(config)}
    if parsed_args.list_all:
        backups_by_group = _get_all_hosts_and_bak_by_groups(
            parsed_args.groups, config, conn, callbacks_registrer
        )
    else:
        backups_by_group = {}
        for cmplgroup in complete_groups.values():
            cmplgroup.scan_backup_dir()
            backups_by_group[cmplgroup.name] = cmplgroup.backups.copy()
    for group_name, dom_backups in backups_by_group.items():
        if parsed_args.domains_names:
            return list_detailed_backups_for_domain(
                complete_groups[group_name],
                parsed_args.domains_names,
                short=parsed_args.short,
            )
        print(" {}\n{}\n".format(group_name, (2 + len(group_name)) * "="))
        print(
            "Total backups: {} hosts, {} backups".format(
                len(dom_backups), sum(len(backups) for backups in dom_backups.values())
            )
        )
        if not parsed_args.short:
            print("Hosts:")
            # TODO: Should also print hosts matching in libvirt but not backup
            # yet
            for dom, backups in sorted(dom_backups.items()):
                print("\t{}: {} backup(s)".format(dom, len(backups)))


def _get_all_hosts_and_bak_by_groups(group_names, config, conn, callbacks_registrer):
    complete_groups = get_usable_complete_groups(config)
    pending_groups = build_all_or_selected_groups(config, conn, callbacks_registrer)

    backups_by_group = {}
    for pgroup in pending_groups:
        backups_by_group[pgroup.name] = {b.dom.name(): tuple() for b in pgroup.backups}

    for cgroup in complete_groups:
        cgroup.scan_backup_dir()
        backups_by_group[cgroup.name].update(cgroup.backups)

    return backups_by_group


def list_detailed_backups_for_domain(group, domains_names, short=False):
    group.hosts = domains_names
    group.scan_backup_dir()
    if not group.backups:
        return

    print(" {}\n{}\n".format(group.name, (2 + len(group.name)) * "="))
    for d, backups in group.backups.items():
        print("{}: {} backup(s)".format(d, len(backups)))
        if not short:
            for b in reversed(sorted(backups, key=lambda x: x.date)):
                print(
                    "\t{}: {}".format(
                        b.date, b.get_complete_path_of(b.definition_filename)
                    )
                )


def get_setup_config():
    config = Config(defaults={"debug": False,})
    try:
        loaded_config = get_config()
    except FileNotFoundError:
        sys.exit(1)

    compat_layers.config.convert_warn(loaded_config)
    config.from_dict(loaded_config)
    return config


def get_setup_conn(config):
    if config.get("username", None):
        conn = _get_auth_conn(config)
    else:
        conn = libvirt.open(config["uri"])
    if conn is None:
        print("Failed to open connection to the hypervisor")
        sys.exit(1)
    conn.setKeepAlive(5, 3)
    return conn


def _get_auth_conn(config):
    def request_cred(credentials, user_data):
        for credential in credentials:
            if credential[0] == libvirt.VIR_CRED_AUTHNAME:
                credential[4] = config.get("username")
            elif credential[0] == libvirt.VIR_CRED_PASSPHRASE:
                credential[4] = config.get("password")
        return 0

    auth = [
        [libvirt.VIR_CRED_AUTHNAME, libvirt.VIR_CRED_PASSPHRASE],
        request_cred,
        None,
    ]
    return libvirt.openAuth(config["uri"], auth, 0)


def get_usable_complete_groups(
    config, only_groups_in=None, conn=None, callbacks_registrer=None
):
    groups = complete_groups_from_dict(
        config.get_groups(), conn=conn, callbacks_registrer=callbacks_registrer
    )
    for g in groups:
        if not g.backup_dir:
            continue
        elif only_groups_in and g.name not in only_groups_in:
            continue
        yield g


def build_all_or_selected_groups(config, conn, callbacks_registrer, groups=None):
    if not groups:
        groups = [
            g
            for g in groups_from_dict(config["groups"], conn, callbacks_registrer)
            if g.autostart
        ]
    else:
        groups = [
            g
            for g in groups_from_dict(config["groups"], conn, callbacks_registrer)
            if g.name in groups
        ]
    return groups


if __name__ == "__main__":
    cli_run()
