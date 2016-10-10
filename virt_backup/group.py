#!/usr/bin/env python3

import libvirt
import logging

from virt_backup.domain import DomBackup, search_domains_regex


logger = logging.getLogger("virt_backup")


def parse_host_pattern(pattern, conn):
    """
    Parse the host pattern as written in the config

    :param pattern: pattern to match on one or several domain names
    :param conn: connection with libvirt
    """
    # if the pattern starts with !, exclude the matching domains
    exclude = pattern.startswith("!")
    if exclude:
        # clean pattern to remove the '!' char
        pattern = pattern[1:]

    if pattern.startswith("r:"):
        pattern = pattern[2:]
        domains = search_domains_regex(pattern, conn)
    elif pattern.startswith("g:"):
        # TODO: option to include another group into this one. It would
        # need to include all domains of this group.
        pattern = pattern[2:]
        # domains =
    else:
        try:
            # will raise libvirt.libvirtError if the domain is not found
            conn.lookupByName(pattern)
            domains = (pattern,)
        except libvirt.libvirtError as e:
            logger.error(e)
            domains = tuple()

    return {"domains": domains, "exclude": exclude}


def match_domains_from_config(host, conn):
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
    matches = parse_host_pattern(pattern, conn)
    # not useful to continue if no domain matches or if the host variable
    # doesn't bring any property for our domain (like which disks to backup)
    if not isinstance(host, dict) or not matches["domains"]:
        return matches

    if host.get("disks", None):
        matches["disks"] = sorted(host["disks"])
    return matches


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
            matches = match_domains_from_config(host, conn)
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
                 **default_bak_param):
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
            b.start()
