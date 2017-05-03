#!/usr/bin/env python3

import arrow
from collections import defaultdict
import libvirt
import logging
import os
import re

from virt_backup.domain import (
    DomBackup, search_domains_regex, list_backups_by_domain,
    build_dom_complete_backup_from_def
)


logger = logging.getLogger("virt_backup")


def matching_libvirt_domains_from_config(host, conn):
    """
    Return matching domains with the host definition

    Will be mainly used by config,

    :param host: domain name or custom regex to match on multiple domains
    :param conn: connection with libvirt
    :returns {"domains": (domain_name, ), "exclude": bool}: exclude will
        indicate if the domains need to be explicitly excluded of the backup
        group or not (for example, if a user wants to exclude all domains
        starting by a certain pattern). Domains will not be libvirt.virDomain
        objects, but just domain names (easier to manage the include/exclude
        feature)
    """
    if isinstance(host, str):
        pattern = host
    else:
        try:
            pattern = host["host"]
        except KeyError as e:
            logger.error(
                "Configuration error, missing host for lines: \n"
                "{}".format(host)
            )
            raise e
    matches = pattern_matching_domains_in_libvirt(pattern, conn)
    # not useful to continue if no domain matches or if the host variable
    # doesn't bring any property for our domain (like which disks to backup)
    if not isinstance(host, dict) or not matches["domains"]:
        return matches

    if host.get("disks", None):
        matches["disks"] = sorted(host["disks"])
    return matches


def pattern_matching_domains_in_libvirt(pattern, conn):
    """
    Parse the host pattern as written in the config and find matching hosts

    :param pattern: pattern to match on one or several domain names
    :param conn: connection with libvirt
    """
    exclude, pattern = _handle_possible_exclusion_host_pattern(pattern)
    if pattern.startswith("r:"):
        pattern = pattern[2:]
        domains = search_domains_regex(pattern, conn)
    elif pattern.startswith("g:"):
        domains = _include_group_domains(pattern)
    else:
        try:
            # will raise libvirt.libvirtError if the domain is not found
            conn.lookupByName(pattern)
            domains = (pattern,)
        except libvirt.libvirtError as e:
            logger.error(e)
            domains = tuple()

    return {"domains": domains, "exclude": exclude}


def domains_matching_with_patterns(domains, patterns):
    include, exclude = set(), set()
    for pattern in patterns:
        for domain in domains:
            pattern_comparaison = is_domain_matching_with(domain, pattern)
            if not pattern_comparaison["matches"]:
                continue
            if pattern_comparaison["exclude"]:
                exclude.add(domain)
            else:
                include.add(domain)
    return include.difference(exclude)


def is_domain_matching_with(domain_name, pattern):
    """
    Parse the host pattern as written in the config and check if the domain
    name matches

    :param domain_name: domain name
    :param pattern: pattern to match on
    :returns: {matches: bool, exclude: bool}
    """
    exclude, pattern = _handle_possible_exclusion_host_pattern(pattern)
    if pattern.startswith("r:"):
        pattern = pattern[2:]
        matches = re.match(pattern, domain_name)
    elif pattern.startswith("g:"):
        # TODO: to implement
        pass
    else:
        matches = pattern == domain_name

    return {"matches": matches, "exclude": exclude}


def _handle_possible_exclusion_host_pattern(pattern):
    """
    Check if pattern starts with "!", meaning matching hosts will be excluded

    :returns: exclude, sanitized_pattern
    """
    # if the pattern starts with !, exclude the matching domains
    exclude = pattern.startswith("!")
    if exclude:
        # clean pattern to remove the '!' char
        pattern = pattern[1:]
    return exclude, pattern


def _include_group_domains(pattern):
    pattern = pattern[2:]
    # TODO: option to include another group into this one. It would
    # need to include all domains of this group.
    # domains =
    return []


def groups_from_dict(groups_dict, conn):
    """
    Construct and yield BackupGroups from a dict (typically as stored in
    config)

    :param groups_dict: dict of groups properties (take a look at the
                        config syntax for more info)
    :param conn: connection with libvirt
    """
    def build(name, properties):
        hosts = properties.pop("hosts")
        include, exclude = [], []
        for host in hosts:
            matches = matching_libvirt_domains_from_config(host, conn)
            if not matches.get("domains", None):
                continue
            if matches["exclude"]:
                exclude += list(matches["domains"])
            else:
                matches.pop("exclude")
                include.append(matches)

        logger.debug("Include domains: {}".format(include))
        logger.debug("Exclude domains: {}".format(exclude))

        # replace some properties by the correct ones
        if properties.get("target", None):
            properties["target_dir"] = properties.pop("target")

        backup_group = BackupGroup(name=name, conn=conn, **properties)
        for i in include:
            for domain_name in i["domains"]:
                if domain_name not in exclude:
                    domain = conn.lookupByName(domain_name)
                    backup_group.add_domain(domain, matches.get("disks", ()))

        return backup_group

    for group_name, group_properties in groups_dict.items():
        yield build(group_name, group_properties)


class BackupGroup():
    """
    Group of libvirt domain backups
    """
    def __init__(self, name="unnamed", domlst=None, autostart=True,
                 directory_by_domain=False, **default_bak_param):
        """
        :param domlst: domain and disks to backup. If specified, has to be a
                       dict, where key would be the domain to backup, and value
                       an iterable containing the disks name to backup. Value
                       could be None
        """
        #: list of DomBackup
        self.backups = list()

        #: group name, "unnamed" by default
        self.name = name

        #: does this group have to be autostarted from the main function or not
        self.autostart = autostart

        #: default attributes for new created domain backups. Keys and values
        #  correspond to what a DomBackup object expect as attributes
        self.default_bak_param = default_bak_param

        if domlst:
            for bak_item in domlst:
                try:
                    dom, disks = bak_item
                except TypeError:
                    dom, disks = (bak_item, ())
                self.add_domain(dom, disks)

    def add_domain(self, dom, disks=()):
        """
        Add a domain and disks to backup in this group

        If a backup already exists for the domain, will add the disks to the
        first backup found

        :param dom: dom to backup
        :param disks: disks to backup and attached to dom
        """
        try:
            # if a backup of `dom` already exists, add the disks to the first
            # backup found
            existing_bak = next(self.search(dom))
            existing_bak.add_disks(*disks)
        except StopIteration:
            # spawn a new DomBackup instance otherwise
            self.backups.append(DomBackup(
                dom=dom, dev_disks=disks, **self.default_bak_param
            ))

    def add_dombackup(self, dombackup):
        """
        Add a DomBackup to this group

        If a backup already exists for the same domain with the same
        properties, will add the disks to the first backup found

        :param dombackup: dombackup to add
        """
        for existing_bak in self.search(dombackup.dom):
            if existing_bak.compatible_with(dombackup):
                existing_bak.merge_with(dombackup)
                return
        else:
            self.backups.append(dombackup)

    def search(self, dom):
        """
        Search for a domain

        :param dom: domain to search the associated DomBackup object.
                    libvirt.virDomain object
        :returns: a generator of DomBackup matching
        """
        for backup in self.backups:
            if backup.dom == dom:
                yield backup

    def propagate_default_backup_attr(self):
        """
        Propagate default backup attributes to all attached backups
        """
        for backup in self.backups:
            for attr, val in self.default_bak_param.items():
                setattr(backup, attr, val)

    def start(self):
        """
        Start to backup all DomBackup objects attached
        """
        for b in self.backups:
            self._ensure_backup_is_set_in_domain_dir(b)
            b.start()

    def _ensure_backup_is_set_in_domain_dir(self, dombackup):
        """
        Ensure that a dombackup is set to be in a directory having the name of
        the related Domain
        """
        if not dombackup.target_dir:
            return

        if os.path.dirname(dombackup.target_dir) != dombackup.dom.name():
            dombackup.target_dir = os.path.join(
                dombackup.target_dir, dombackup.dom.name()
            )


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
                build_dom_complete_backup_from_def(definition, self.backup_dir)
                for _, definition in backups_def[dom_name]
            ]

        self.backups = backups

    def clean(self, hourly="*", daily="*", weekly="*", monthly="*",
              yearly="*"):
        for domain, domain_backups in self.backups:
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
                        domain_backups, period, periodly
                    ))
            for b in keep_backups.difference(set(domain_backups)):
                remove_backup(b)

    def _keep_n_periodly_backups(self, sorted_backups, period, n):
        if not n:
            return []

        grouped_backups = self._group_backup_by_period(sorted_backups, period)

        # will keep all yearly backups
        if n == "*":
            n = 0
        return set(
            backups[0] for group, backups in list(grouped_backups.items())[-n:]
        )

    def _group_backup_by_period(self, sorted_backups, period):
        grouped_backups = defaultdict(list)
        periods = ("hour", "day", "week", "month", "year")
        for backup in sorted_backups:
            key = tuple(
                getattr(backup.date, p)
                for p in periods[periods.index(period):]
            )
            grouped_backups[key].append(backup)
        return grouped_backups

    def remove_backup(self, dombackup):
        raise NotImplementedError()
