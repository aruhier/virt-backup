#!/usr/bin/env python3

import arrow
import defusedxml.lxml
import glob
import json
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
        # TODO: raise an exception if a disk was part of the filter but not
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

    def _dump_json_definition(self, definition):
        """
        Dump the backup definition as json

        Definition will describe our backup, with the date, backuped
        disks names and other informations
        """
        backup_date = arrow.get(definition["date"]).to("local")
        definition_path = os.path.join(
            self.target_dir,
            "{}.{}".format(self._main_backup_name_format(backup_date), "json")
        )
        with open(definition_path, "w") as json_definition:
            json.dump(definition, json_definition, indent=4)

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

    def get_definition(self):
        """
        Get a json defining this backup
        """
        return {
            "disks": tuple(self.disks.keys()),
            "compression": self.compression,
            "compression_lvl": self.compression_lvl,
            "domain_id": self.dom.ID(), "domain_name": self.dom.name(),
            "domain_xml": self.dom.XMLDesc()
        }

    def backup_img(self, disk, target, target_filename=None):
        """
        Backup a disk image

        :param disk: path of the image to backup
        :param target: dir or filename to copy into/as
        :param target_filename: destination file will have this name, or keep
                                the original one. target has to be a dir
                                (if not exists, will be created)
        :returns backup_path: complete path of our backup
        """
        if self.compression:
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
            if self.compression == "xz":
                backup_path = target.fileobj._fp.name
            else:
                backup_path = target.fileobj.name
        else:
            # target is a directory if target_filename is set, or an existing
            # directory or a destination file
            if target_filename is not None:
                if not os.path.isdir(target):
                    os.makedirs(target)
            target = os.path.join(target, target_filename or disk)
            logger.debug("Copy {} as {}".format(disk, target))
            copy_file_progress(disk, target, buffersize=10*1024*1024)
            backup_path = target

        logger.debug("{} successfully copied".format(disk))
        return os.path.abspath(backup_path)

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

    def _backup_disk(self, disk, disk_properties, backup_target, definition):
        """
        Backup a disk and complete the definition by adding this disk

        :param disk: diskname to backup
        :param disk_properties: dictionary discribing our disk (typically
                                contained in self.disks[disk])
        :param backup_target: target path of our backup
        :param definition: dictionary representing the domain backup
        """
        snapshot_date = arrow.get(definition["date"]).to("local")
        logger.info(
            "Backup disk {} of domain {}".format(disk, self.dom.name())
        )
        target_img = "{}.{}".format(
            self._disk_backup_name_format(snapshot_date, disk),
            disk_properties["type"]
        )
        backup_path = self.backup_img(
            disk_properties["src"], backup_target, target_img
        )
        if self.compression:
            if not definition.get("files", None):
                # all disks will be compacted in the same tar, so already
                # store it in definition if it was not set before
                definition["tar"] = os.path.basename(backup_path)
        definition["files"][disk] = target_img

    def _blockcommit_disk_and_wait(self, disk):
        """
        Block commit and wait for the pivot to be triggered

        Will allow to merge the external snapshot previously created with the
        disk main image

        :param disk: diskname to blockcommit
        """
        logger.info("Starts to blockcommit {} to pivot snapshot".format(disk))
        self.dom.blockCommit(
            disk, None, None, 0,
            (
                libvirt.VIR_DOMAIN_BLOCK_COMMIT_ACTIVE +
                libvirt.VIR_DOMAIN_BLOCK_COMMIT_SHALLOW
            )
        )
        self._wait_for_pivot.wait(timeout=self.timeout)

    def start(self):
        """
        Start the entire backup process for all disks in self.disks
        """
        backup_target = None
        self._wait_for_pivot.clear()
        print("Backup started for domain {}".format(self.dom.name()))
        definition = self.get_definition()
        try:
            callback_id = self.conn.domainEventRegisterAny(
                None, libvirt.VIR_DOMAIN_EVENT_ID_BLOCK_JOB,
                self.pivot_callback, None
            )
            self.external_snapshot()

            # all of our disks are frozen, so the backup date is right now
            snapshot_date = arrow.now()
            definition["date"] = snapshot_date.timestamp

            backup_target = (
                self.target_dir if self.compression is None
                else self.get_new_tar(self.target_dir, snapshot_date)
            )
            # TODO: handle backingStore cases
            for disk, prop in self.disks.items():
                self._backup_disk(disk, prop, backup_target, definition)
                self._blockcommit_disk_and_wait(disk)

            self._dump_json_definition(definition)
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
            _disks = self._get_disks(*dev_disks)
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
