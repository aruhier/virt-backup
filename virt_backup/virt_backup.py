#!/usr/bin/env python3

import datetime
import defusedxml.lxml
import libvirt
import logging
import lxml.etree
import os
import tarfile
import threading
from tqdm import tqdm
from virt_backup.tools import copy_file_progress, get_progress_bar_tar


logger = logging.getLogger("virt_backup")


class BackupGroup():
    """
    Group of libvirt domain backups
    """
    @property
    def target_dir(self):
        return self._target_dir

    @target_dir.setter
    def target_dir(self, val):
        """
        Change the target dir for all attached backups
        """
        for b in self.backups:
            b.target = val

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
            self.backups.append(
                DomBackup(dom=dom, dev_disks=disks, target_dir=self.target_dir)
            )

    def start(self):
        """
        Start to backup all DomBackup objects attached
        """
        for b in self.backups:
            b.start()

    def __init__(self, domlst=None, target_dir=None):
        """
        :param domlst: domain and disks to backup. If specified, has to be a
                       dict, where key would be the domain to backup, and value
                       an iterable containing the disks name to backup. Value
                       could be None
        """
        #: list of DomBackup
        self.backups = list()

        #: directory where backups will be saved
        self._target_dir = target_dir

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
        str_snapdate = snapdate.strftime("%Y%m%d-%H%M")
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
            mode = "x:{}".format(self.compression)
            extension = "tar.{}".format(self.compression)
        else:
            mode = "x"
            extension = "tar"

        if not os.path.isdir(target):
            os.path.makedirs(target)

        complete_path = os.path.join(
            target,
            "{}.{}".format(
                self._main_backup_name_format(snapshot_date), extension
            )
        )
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
