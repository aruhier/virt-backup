#!/usr/bin/env python3

import datetime
import defusedxml.lxml
import libvirt
import logging
import lxml.etree
import os
import re
import tarfile
import threading
from tqdm import tqdm
from virt_backup.tools import copy_file_progress, get_progress_bar_tar


logger = logging.getLogger("virt_backup")


def search_domains_regex(pattern, conn):
    """
    Yield all domains matching with a regex

    :param pattern: regex to match on all domain names listed by libvirt
    :param conn: connection with libvirt
    """
    c_pattern = re.compile(pattern)
    for domain in conn.listAllDomains():
        domain_name = domain.name()
        if c_pattern.match(domain_name):
            yield domain_name


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
                    backup_group.add_backup(domain, matches.get("disks", ()))

        return backup_group

    for group_name, group_properties in groups_dict.items():
        yield build(group_name, group_properties)


class BackupGroup():
    """
    Group of libvirt domain backups
    """
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

    def add_backup(self, dom, disks=()):
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
                self.add_backup(dom, disks)


class DomBackup():
    """
    Libvirt domain backup
    """
    def _parse_xml(self):
        """
        Parse the domain's definition
        """
        return defusedxml.lxml.fromstring(self.dom.XMLDesc())

    def _get_disks(self, *filter_dev):
        """
        Get disks from the domain xml

        :param filter_dev: return only disks for which the dev name matches
                           with one in filter_dev. If no parameter, will return
                           every disks.
        """
        dom_xml = self._parse_xml()
        disks = {}
        for elem in dom_xml.xpath("devices/disk"):
            try:
                if elem.get("device", None) == "disk":
                    dev = elem.xpath("target")[0].get("dev")
                    if len(filter_dev) and dev not in filter_dev:
                        continue
                    src = elem.xpath("source")[0].get("file")
                    disk_type = elem.xpath("driver")[0].get("type")

                    disks[dev] = {"src": src, "type": disk_type}
            except IndexError:
                continue
        # TODO: raise an exception if a disk was is the filter but in fact not
        #       found in the domain
        return disks

    def _main_backup_name_format(self, snapdate, *args, **kwargs):
        """
        Main backup name format

        Extracted in its own function so it can be easily override

        :param snapdate: date when external snapshots have been created
        """
        str_snapdate = snapdate.strftime("%Y%m%d-%H%M%S")
        return "{}_{}_{}".format(str_snapdate, self.dom.ID(), self.dom.name())

    def _disk_backup_name_format(self, snapdate, disk_name, *args, **kwargs):
        """
        Backup name format for each disk when no compression/compacting is set

        :param snapdate: date when external snapshots have been created
        :param disk_name: disk name currently being backup
        """
        return (
            "{}_{}".format(self._main_backup_name_format(snapdate), disk_name)
        )

    def add_disks(self, *dev_disks):
        """
        Add disk by dev name

        .. warning::

            Adding a disk during a backup is not recommended, as the current
            disks list could be inaccurate. It will pull the informations
            about the current disks attached to the domain, but the backup
            process creates temporary external snapshots, changing the current
            disks attached. This should not be an issue when the backingStore
            property will be correctly handled, but for now it is.

        :param dev_disk: dev name of the new disk to backup. If not indicated,
                         will add all disks.
        """
        dom_all_disks = self._get_disks()
        if len(dev_disks) == 0:
            self.disks = dom_all_disks
        for dev in dev_disks:
            if dev in self.disks:
                continue
            self.disks[dev] = dom_all_disks[dev]

    def backup_img(self, disk, target, target_filename=None):
        """
        Backup a disk image

        :param disk: path of the image to backup
        :param target: dir or filename to copy into/as
        :param target_filename: destination file will have this name, or keep
                                the original one. target has to be a dir
                                (if not exists, will be created)
        """
        if self.compression is None:
            if target_filename is not None:
                if not os.path.isdir(target):
                    os.makedirs(target)
                target = os.path.join(target, target_filename)
            logger.debug("Copy {} as {}".format(disk, target))
            copy_file_progress(disk, target, buffersize=10*1024*1024)
        else:
            # target is a tarfile.TarFile
            total_size = os.path.getsize(disk)
            tqdm_kwargs = {
                "total": total_size, "unit": "B", "unit_scale": True,
                "ncols": 0
            }
            logger.debug("Copy {}…".format(disk))
            with tqdm(**tqdm_kwargs) as pbar:
                target.fileobject = get_progress_bar_tar(pbar)
                target.add(disk, arcname=target_filename)
        logger.debug("{} successfully copied".format(disk))

    def get_new_tar(self, target, snapshot_date):
        """
        Get a new tar for this backup

        self._main_backup_name_format will be used to generate a new tar name

        :param target: directory path that will contain our tar. If not exists,
                       will be created.
        """
        if self.compression not in (None, "tar"):
            mode = "w:{}".format(self.compression)
            extension = "tar.{}".format(self.compression)
        else:
            mode = "w"
            extension = "tar"

        if not os.path.isdir(target):
            os.path.makedirs(target)

        complete_path = os.path.join(
            target,
            "{}.{}".format(
                self._main_backup_name_format(snapshot_date), extension
            )
        )
        if os.path.exists(complete_path):
            raise FileExistsError
        return tarfile.open(complete_path, mode)

    def pivot_callback(self, conn, dom, disk, event_id, status, *args):
        """
        Pivot the snapshot

        If the received domain matches with the one associated to this backup,
        abort the blockjob and pivot it.
        """
        domain_matches = dom.ID() == self.dom.ID()
        if status == libvirt.VIR_DOMAIN_BLOCK_JOB_READY and domain_matches:
            dom.blockJobAbort(disk, libvirt.VIR_DOMAIN_BLOCK_JOB_ABORT_PIVOT)
            os.remove(disk)
            self._wait_for_pivot.set()

    def gen_snapshot_xml(self):
        """
        Generate a xml defining the snapshot
        """
        root_el = lxml.etree.Element("domainsnapshot")
        xml_tree = root_el.getroottree()

        descr_el = lxml.etree.Element("description")
        root_el.append(descr_el)
        descr_el.text = "Pre-backup external snapshot"

        disks_el = lxml.etree.Element("disks")
        root_el.append(disks_el)
        for d in sorted(self.disks.keys()):
            disk_el = lxml.etree.Element("disk")
            disk_el.attrib["name"] = d
            disk_el.attrib["snapshot"] = "external"
            disks_el.append(disk_el)

        return lxml.etree.tostring(xml_tree, pretty_print=True).decode()

    def external_snapshot(self):
        """
        Create an external snapshot in order to freeze the base image
        """
        snap_xml = self.gen_snapshot_xml()
        self.dom.snapshotCreateXML(
            snap_xml,
            (
                libvirt.VIR_DOMAIN_SNAPSHOT_CREATE_DISK_ONLY +
                libvirt.VIR_DOMAIN_SNAPSHOT_CREATE_ATOMIC +
                libvirt.VIR_DOMAIN_SNAPSHOT_CREATE_NO_METADATA
            )
        )

    def start(self):
        """
        Start the entire backup process for all disks in self.disks
        """
        backup_target = None
        self._wait_for_pivot.clear()
        print("Backup started for domain {}".format(self.dom.name()))
        try:
            callback_id = self.conn.domainEventRegisterAny(
                None, libvirt.VIR_DOMAIN_EVENT_ID_BLOCK_JOB,
                self.pivot_callback, None
            )
            self.external_snapshot()
            snapshot_date = datetime.datetime.now()
            backup_target = (
                self.target_dir if self.compression is None
                else self.get_new_tar(self.target_dir, snapshot_date)
            )

            # TODO: handle backingStore cases
            # TODO: add a json containing our backup metadata
            for disk, prop in self.disks.items():
                logger.info(
                    "Backup disk {} of domain {}".format(disk, self.dom.name())
                )
                target_img = "{}.{}".format(
                    self._disk_backup_name_format(snapshot_date, disk),
                    prop["type"]
                )
                self.backup_img(prop["src"], backup_target, target_img)

                logger.info(
                    "Starts to blockcommit {} to pivot snapshot".format(disk)
                )
                self.dom.blockCommit(
                    disk, None, None, 0,
                    (
                        libvirt.VIR_DOMAIN_BLOCK_COMMIT_ACTIVE +
                        libvirt.VIR_DOMAIN_BLOCK_COMMIT_SHALLOW
                    )
                )
                self._wait_for_pivot.wait(timeout=self.timeout)
        finally:
            self.conn.domainEventDeregisterAny(callback_id)
            if isinstance(backup_target, tarfile.TarFile):
                backup_target.close()
            # TODO: remove our broken backup if it failed
        print("Backup finished for domain {}".format(self.dom.name()))

    def __init__(self, dom, target_dir=None, dev_disks=None, compression="tar",
                 compression_lvl=None, conn=None, timeout=None, _disks=None):
        """
        :param dev_disks: list of disks dev names to backup. Disks will be
                          searched in the domain to pull more informations, and
                          an exception will be thrown if one of them is not
                          found
        """
        #: domain to backup. Has to be a libvirt.virDomain object
        self.dom = dom

        #: directory where backups will be saved
        self.target_dir = target_dir

        #: disks to backups. If None, will backup every vm disks
        if dev_disks:
            _disks = self._get_disks(dev_disks)
        self.disks = self._get_disks() if _disks is None else _disks

        #: string indicating how to compress the backups:
        #    * None: no compression, backups will be only copied
        #    * "tar": backups will not be compressed, but packaged in a tar
        #    * "gz"/"bz2"/"xz": backups will be compressed in a tar +
        #        compression selected. For more informations, read the
        #        documentation about the mode argument of tarfile.open
        self.compression = compression

        #: If compression, indicates the lvl to use
        self.compression_lvl = compression_lvl

        #: libvirt connection to use. If not sent, will use the connection used
        #  for self.domain
        self.conn = self.dom._conn if conn is None else conn

        #: timeout when waiting for the block pivot to end. Infinite wait if
        #  timeout is None
        self.timeout = timeout

        #: used to trigger when block pivot ends
        self._wait_for_pivot = threading.Event()
