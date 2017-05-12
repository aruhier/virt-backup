
from collections import defaultdict
import glob
import json
import logging
import os

from virt_backup.backups import build_dom_complete_backup_from_def
from .pattern import domains_matching_with_patterns


logger = logging.getLogger("virt_backup")


def list_backups_by_domain(backup_dir):
    """
    Group all avaible backups by domain, in a dict

    Backups have to respect the structure: backup_dir/domain_name/*backups*

    :returns: {domain_name: [(definition_path, definition_dict), …], …}
    :rtype: dict
    """
    backups = {}
    for json_file in glob.glob(os.path.join(backup_dir, "*/*.json")):
        logger.debug("{} detected".format(json_file))
        with open(json_file, "r") as definition_file:
            try:
                definition = json.load(definition_file)
            except Exception as e:
                logger.debug("Error for file {}: {}".format(json_file, e))
                continue
        domain_name = definition["domain_name"]
        if domain_name not in backups:
            backups[domain_name] = []
        backups[domain_name].append((json_file, definition))
    return backups


def complete_groups_from_dict(groups_dict):
    """
    Construct and yield CompleteBackupGroups from a dict (typically as stored
    in config)

    :param groups_dict: dict of groups properties (take a look at the
                        config syntax for more info)
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

        complete_backup_group = CompleteBackupGroup(name=name, **attrs)
        return complete_backup_group

    for group_name, group_properties in groups_dict.items():
        yield build(group_name, group_properties)


class CompleteBackupGroup():
    """
    Group of complete libvirt domain backups
    """
    def __init__(
        self, name="unnamed", backup_dir=None, hosts=None, backups=None
    ):
        #: dict of domains and their backups (CompleteDomBackup)
        self.backups = backups or dict()

        #: hosts_patterns
        self.hosts = hosts or []

        self.name = name

        #: Base backup directory
        self.backup_dir = backup_dir

    def scan_backup_dir(self):
        if not self.backup_dir:
            raise NotADirectoryError("backup_dir not defined")

        backups_def = list_backups_by_domain(self.backup_dir)
        backups = {}
        domains_to_include = domains_matching_with_patterns(
            backups_def.keys(), self.hosts
        )
        for dom_name in domains_to_include:
            backups[dom_name] = [
                build_dom_complete_backup_from_def(
                    definition,
                    backup_dir=os.path.dirname(definition_filename),
                    definition_filename=definition_filename
                )
                for definition_filename, definition in backups_def[dom_name]
            ]

        self.backups = backups

    def clean(self, hourly="*", daily="*", weekly="*", monthly="*",
              yearly="*"):
        backups_removed = set()
        for domain, domain_backups in self.backups.items():
            domain_backups = sorted(domain_backups, key=lambda b: b.date)
            keep_backups = set()

            period_tuples = (
                ("hour", "hourly"), ("day", "daily"), ("week", "weekly"),
                ("month", "monthly"), ("year", "yearly"),
            )
            for period, periodly in period_tuples:
                n_to_keep = locals()[periodly]
                if n_to_keep:
                    keep_backups.update(self._keep_n_periodly_backups(
                        domain_backups, period, n_to_keep
                    ))

            backups_to_remove = set(domain_backups).difference(keep_backups)
            for b in backups_to_remove:
                logger.info(
                    "Cleaning backup {} for domain {}".format(b.date, domain)
                )
                b.delete()
                self.backups[domain].remove(b)
                backups_removed.add(b)

        return backups_removed

    def _keep_n_periodly_backups(self, sorted_backups, period, n):
        if not n:
            return []

        grouped_backups = self._group_backup_by_period(sorted_backups, period)

        # will keep all yearly backups
        if n == "*":
            n = 0
        return set(
            backups[0] for group, backups in
            sorted(grouped_backups.items())[-n:]
        )

    def _group_backup_by_period(self, sorted_backups, period):
        grouped_backups = defaultdict(list)
        periods = ("hour", "day", "week", "month", "year")
        for backup in sorted_backups:
            key = tuple(
                getattr(backup.date, p)
                for p in reversed(periods[periods.index(period):])
            )
            grouped_backups[key].append(backup)
        return grouped_backups
