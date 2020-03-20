from collections import defaultdict
import concurrent.futures
import logging
import multiprocessing
import os

from virt_backup.backups import DomBackup, build_dom_complete_backup_from_def
from virt_backup.domains import search_domains_regex
from virt_backup.exceptions import BackupsFailureInGroupError
from .pattern import matching_libvirt_domains_from_config


logger = logging.getLogger("virt_backup")


def groups_from_dict(groups_dict, conn, callbacks_registrer):
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

        backup_group = BackupGroup(
            name=name, conn=conn, callbacks_registrer=callbacks_registrer, **properties
        )
        for i in include:
            for domain_name in i["domains"]:
                if domain_name not in exclude:
                    domain = conn.lookupByName(domain_name)
                    backup_group.add_domain(domain, matches.get("disks", ()))

        return backup_group

    def sanitize_properties(properties):
        # replace some properties by the correct ones
        if properties.get("target", None):
            properties["backup_dir"] = properties.pop("target")
        elif properties.get("target_dir", None):
            properties["backup_dir"] = properties.pop("target_dir")

        # pop params related to complete groups only
        for prop in ("hourly", "daily", "weekly", "monthly", "yearly"):
            try:
                properties.pop(prop)
            except KeyError:
                continue

        return properties

    for group_name, group_properties in groups_dict.items():
        yield build(group_name, group_properties.copy())


class BackupGroup:
    """
    Group of libvirt domain backups
    """

    def __init__(
        self, name="unnamed", domlst=None, autostart=True, **default_bak_param
    ):
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
            self.backups.append(
                DomBackup(dom=dom, dev_disks=disks, **self.default_bak_param)
            )

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

        :returns results: dictionary of domain names and their backup
        """
        completed_backups = {}
        error_backups = {}

        for b in self.backups:
            dom_name = b.dom.name()
            try:
                completed_backups[dom_name] = self._start_backup(b)
            except KeyboardInterrupt:
                raise
            except Exception as e:
                error_backups[dom_name] = e
                logger.error("Error with domain %s: %s", dom_name, e)
                logger.exception(e)

        if error_backups:
            raise BackupsFailureInGroupError(completed_backups, error_backups)
        else:
            return completed_backups

    def start_multithread(self, nb_threads=None):
        """
        Start all backups, multi threaded

        It is wanted to avoid running multiple backups on the same domain (if
        the target dir is different for 2 backups of the same domain, for
        example), because of the way backups are done. An external snapshot is
        created then removed, backups would copy the external snapshot of other
        running backups instead of the real disk.

        To avoid this issue, a callback is set for each futures in order to
        notify when they are completed, and put the completed domain in a
        queue.
        If no other backup is to do for this domain, it will be dropped,
        otherwise a backup targeting this domain will be started.
        """
        nb_threads = nb_threads or multiprocessing.cpu_count()

        backups_by_domain = self._group_backups_by_domain()

        completed_backups = {}
        error_backups = {}

        completed_doms = []
        futures = {}
        with concurrent.futures.ThreadPoolExecutor(nb_threads) as executor:
            for backups_for_domain in backups_by_domain.values():
                backup = backups_for_domain.pop()
                future = self._submit_backup_future(executor, backup, completed_doms)
                futures[future] = backup.dom

            while len(futures) < len(self.backups):
                next(concurrent.futures.as_completed(futures))
                dom = completed_doms.pop()
                if backups_by_domain.get(dom):
                    backup = backups_by_domain[dom].pop()
                    future = self._submit_backup_future(
                        executor, backup, completed_doms
                    )
                    futures[future] = backup.dom

        for f in concurrent.futures.as_completed(futures):
            dom_name = futures[f].name()
            try:
                completed_backups[dom_name] = f.result()
            except KeyboardInterrupt:
                raise
            except Exception as e:
                error_backups[dom_name] = e
                logger.error("Error with domain %s: %s", dom_name, e)
                logger.exception(e)

        if error_backups:
            raise BackupsFailureInGroupError(completed_backups, error_backups)
        else:
            return completed_backups

    def _group_backups_by_domain(self):
        backups_by_domain = defaultdict(list)
        for b in self.backups:
            backups_by_domain[b.dom].append(b)

        return backups_by_domain

    def _submit_backup_future(self, executor, backup, completed_doms: list):
        """
        :param completed_doms: list where a completed backup will append its
            domain.
        """
        future = executor.submit(self._start_backup, backup)
        future.add_done_callback(lambda *args: completed_doms.append(backup.dom))

        return future

    def _start_backup(self, backup):
        self._ensure_backup_is_set_in_domain_dir(backup)
        return backup.start()

    def _ensure_backup_is_set_in_domain_dir(self, dombackup):
        """
        Ensure that a dombackup is set to be in a directory having the name of
        the related Domain
        """
        if not dombackup.backup_dir:
            return

        if os.path.dirname(dombackup.backup_dir) != dombackup.dom.name():
            dombackup.backup_dir = os.path.join(
                dombackup.backup_dir, dombackup.dom.name()
            )
