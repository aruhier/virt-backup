from collections import defaultdict
import glob
import json
import logging
import os

from virt_backup.backups import (
    build_dom_complete_backup_from_def,
    build_dom_backup_from_pending_info,
)
from virt_backup.exceptions import BackupNotFoundError, DomainNotFoundError
from .pattern import domains_matching_with_patterns


logger = logging.getLogger("virt_backup")


def list_backups_by_domain(backup_dir):
    """
    Group all avaible backups by domain, in a dict

    Backups have to respect the structure: backup_dir/domain_name/*backups*

    :returns: {domain_name: [(definition_path, definition_dict), …], …}
    :rtype: dict
    """
    return _list_json_following_pattern_by_domain(backup_dir, "*/*.json")


def list_broken_backups_by_domain(backup_dir):
    """
    Group all broken backups by domain, in a dict

    Backups have to respect the structure: backup_dir/domain_name/*backups*

    :returns: {domain_name: [(backup_dir, pending_info_dict), …], …}
    :rtype: dict
    """
    return _list_json_following_pattern_by_domain(backup_dir, "*/*.json.pending")


def _list_json_following_pattern_by_domain(directory, glob_pattern):
    backups = {}
    for json_file in glob.glob(os.path.join(directory, glob_pattern)):
        logger.debug("{} detected".format(json_file))
        with open(json_file, "r") as definition_file:
            try:
                metadata = json.load(definition_file)
            except Exception as e:
                logger.debug("Error for file {}: {}".format(json_file, e))
                continue
        domain_name = metadata["domain_name"]
        if domain_name not in backups:
            backups[domain_name] = []
        backups[domain_name].append((json_file, metadata))
    return backups


def complete_groups_from_dict(groups_dict, conn=None, callbacks_registrer=None):
    """
    Construct and yield CompleteBackupGroups from a dict (typically as stored
    in config)

    :param groups_dict: dict of groups properties (take a look at the
                        config syntax for more info)
    :param conn: libvirt connection
    :param callbacks_registrer: handle snapshot events. Required if conn is set
    """

    def build(name, properties):
        attrs = {}
        attrs["hosts"] = []
        for host in properties.get("hosts", []):
            if isinstance(host, str):
                attrs["hosts"].append(host)
            else:
                try:
                    attrs["hosts"].append(host["host"])
                except KeyError as e:
                    logger.error(
                        "Configuration error, missing host for lines: \n"
                        "{}".format(host)
                    )
                    raise e

        if properties.get("target", None):
            attrs["backup_dir"] = properties["target"]

        complete_backup_group = CompleteBackupGroup(
            name=name, conn=conn, callbacks_registrer=callbacks_registrer, **attrs
        )
        return complete_backup_group

    for group_name, group_properties in groups_dict.items():
        yield build(group_name, group_properties)


class CompleteBackupGroup:
    """
    Group of complete libvirt domain backups
    """

    def __init__(
        self,
        name="unnamed",
        backup_dir=None,
        hosts=None,
        conn=None,
        backups=None,
        broken_backups=None,
        callbacks_registrer=None,
    ):
        #: dict of domains and their backups (CompleteDomBackup)
        self.backups = backups or dict()

        #: dict of domains and their broken/aborted backups (DomBackup)
        self.broken_backups = broken_backups or dict()

        #: hosts_patterns
        self.hosts = hosts or []

        self.name = name

        #: base backup directory
        self.backup_dir = backup_dir

        #: connection to libvirt
        self.conn = conn

        #: callbacks registrer, used to clean broken backups. Needed if
        #  self.conn is set.
        self._callbacks_registrer = callbacks_registrer

        if self.conn and not self._callbacks_registrer:
            raise AttributeError("callbacks_registrer needed if conn is given")

    def scan_backup_dir(self):
        if not self.backup_dir:
            raise NotADirectoryError("backup_dir not defined")

        self._build_backups()
        if self.conn:
            self._build_broken_backups()
        else:
            logger.debug(
                "No libvirt connection for group {}, does not scan for "
                "possible broken backups.".format(self.conn)
            )

    def _build_backups(self):
        backups = {}
        backups_by_domain = list_backups_by_domain(self.backup_dir)
        domains_to_include = domains_matching_with_patterns(
            backups_by_domain.keys(), self.hosts
        )
        for dom_name in domains_to_include:
            backups[dom_name] = sorted(
                (
                    build_dom_complete_backup_from_def(
                        definition,
                        backup_dir=os.path.dirname(definition_filename),
                        definition_filename=definition_filename,
                    )
                    for definition_filename, definition in backups_by_domain[dom_name]
                ),
                key=lambda b: b.date,
            )

        self.backups = backups

    def _build_broken_backups(self):
        broken_backups = {}
        broken_backups_by_domain = list_broken_backups_by_domain(self.backup_dir)
        domains_to_include = domains_matching_with_patterns(
            broken_backups_by_domain.keys(), self.hosts
        )
        for dom_name in domains_to_include:
            broken_backups[dom_name] = sorted(
                (
                    build_dom_backup_from_pending_info(
                        pending_info,
                        backup_dir=os.path.dirname(pending_info_json),
                        conn=self.conn,
                        callbacks_registrer=self._callbacks_registrer,
                    )
                    for pending_info_json, pending_info in broken_backups_by_domain[
                        dom_name
                    ]
                ),
                key=lambda b: b.pending_info.get("date", None),
            )

        self.broken_backups = broken_backups

    def get_backup_at_date(self, domain_name, date):
        try:
            backups = self.backups[domain_name]
        except KeyError:
            raise DomainNotFoundError(domain_name)

        for b in backups:
            if b.date == date:
                return b

        raise BackupNotFoundError

    def get_n_nearest_backup(self, domain_name, date, n):
        try:
            backups = self.backups[domain_name]
        except KeyError:
            raise DomainNotFoundError(domain_name)

        diff_list = sorted(backups, key=lambda b: abs(b.date - date))

        return diff_list[:n] if diff_list else None

    def clean(self, hourly=5, daily=5, weekly=5, monthly=5, yearly=5):
        backups_removed = set()
        for domain, domain_backups in self.backups.items():
            domain_backups = sorted(domain_backups, key=lambda b: b.date)
            keep_backups = set()

            keep_backups.update(
                self._keep_n_periodic_backups(domain_backups, "hour", hourly),
                self._keep_n_periodic_backups(domain_backups, "day", daily),
                self._keep_n_periodic_backups(domain_backups, "week", weekly),
                self._keep_n_periodic_backups(domain_backups, "month", monthly),
                self._keep_n_periodic_backups(domain_backups, "year", yearly),
            )

            backups_to_remove = set(domain_backups).difference(keep_backups)
            for b in backups_to_remove:
                logger.info("Cleaning backup {} for domain {}".format(b.date, domain))
                b.delete()
                self.backups[domain].remove(b)
                backups_removed.add(b)

        return backups_removed

    def clean_broken_backups(self):
        backups_removed = set()
        for domain, backups in self.broken_backups.items():
            for backup in backups:
                backup.clean_aborted()
                self.broken_backups[domain].remove(backup)
                backups_removed.add(backup)

        return backups_removed

    def _keep_n_periodic_backups(self, sorted_backups, period, n):
        if not n:
            return []

        grouped_backups = self._group_backup_by_period(sorted_backups, period)

        # will keep all yearly backups
        if n == "*":
            n = 0
        return set(
            backups[0] for group, backups in sorted(grouped_backups.items())[-n:]
        )

    def _group_backup_by_period(self, sorted_backups, period):
        grouped_backups = defaultdict(list)
        periods = ("hour", "day", "week", "month", "year")
        for backup in sorted_backups:
            key = tuple(
                getattr(backup.date, p)
                for p in reversed(periods[periods.index(period) :])
            )
            grouped_backups[key].append(backup)
        return grouped_backups
