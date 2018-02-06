import logging
import os

from virt_backup.backups import DomBackup, build_dom_complete_backup_from_def
from virt_backup.domains import search_domains_regex
from .pattern import matching_libvirt_domains_from_config


logger = logging.getLogger("virt_backup")


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

        sanitize_properties(properties)

        backup_group = BackupGroup(name=name, conn=conn, **properties)
        for i in include:
            for domain_name in i["domains"]:
                if domain_name not in exclude:
                    domain = conn.lookupByName(domain_name)
                    backup_group.add_domain(domain, matches.get("disks", ()))

        return backup_group

    def sanitize_properties(properties):
        # replace some properties by the correct ones
        if properties.get("target", None):
            properties["target_dir"] = properties.pop("target")

        # pop params related to complete groups only
        for prop in ("hourly", "daily", "weekly", "monthly", "yearly"):
            try:
                properties.pop(prop)
            except KeyError:
                continue

        return properties

    for group_name, group_properties in groups_dict.items():
        yield build(group_name, group_properties.copy())


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
