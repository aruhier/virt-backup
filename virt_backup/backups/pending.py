import arrow
import defusedxml.lxml
import json
import libvirt
import logging
import lxml.etree
import os
import subprocess
import tarfile

import virt_backup
from virt_backup.backups.packagers import ReadBackupPackagers, WriteBackupPackagers
from virt_backup.compat_layers.pending_info import (
    convert as compat_convert_pending_info,
)
from virt_backup.domains import get_xml_block_of_disk
from virt_backup.tools import copy_file
from . import _BaseDomBackup
from .snapshot import DomExtSnapshot


logger = logging.getLogger("virt_backup")


def build_dom_backup_from_pending_info(
    pending_info, backup_dir, conn, callbacks_registrer
):
    compat_convert_pending_info(pending_info)
    kwargs = {
        "dom": conn.lookupByName(pending_info["domain_name"]),
        "backup_dir": backup_dir,
        "dev_disks": tuple(pending_info.get("disks", {}).keys()),
        "callbacks_registrer": callbacks_registrer,
    }
    if pending_info.get("packager"):
        kwargs["packager"] = pending_info["packager"].get("type")
        kwargs["packager_opts"] = pending_info["packager"].get("opts", {})

    backup = DomBackup(**kwargs)
    backup.pending_info = pending_info

    return backup


class DomBackup(_BaseDomBackup):
    """
    Libvirt domain backup
    """

    def __init__(
        self,
        dom,
        backup_dir=None,
        dev_disks=None,
        packager="tar",
        packager_opts=None,
        conn=None,
        timeout=None,
        disks=None,
        ext_snapshot_helper=None,
        callbacks_registrer=None,
    ):
        """
        :param dev_disks: list of disks dev names to backup. Disks will be
                          searched in the domain to pull more informations, and
                          an exception will be thrown if one of them is not
                          found
        :param disks: dictionary of disks to backup, in this form:
                      `{"src": disk_path, "type": disk_format}`. Prefer
                      using dev disks when possible.
        """
        #: domain to backup. Has to be a libvirt.virDomain object
        self.dom = dom

        #: directory where backups will be saved
        self.backup_dir = backup_dir

        #: disks to backups. If None, will backup every vm disks
        self.disks = {}
        if dev_disks:
            self.disks.update(self._get_self_domain_disks(*dev_disks))
        if disks:
            self.disks.update(self._get_self_domain_disks(*disks))
        if not self.disks:
            self.disks = self._get_self_domain_disks()

        #: string indicating how to compress the backups:
        #    * None/dir: no compression, backups will be only copied
        #    * "tar": backups will be packaged in a tarfile (compression available
        #        through packager_opts)
        self.packager = packager or "directory"

        #: dict of packager options.
        self.packager_opts = dict(packager_opts) if packager_opts else {}

        #: libvirt connection to use. If not sent, will use the connection used
        #  for self.domain
        self.conn = self.dom._conn if conn is None else conn

        #: timeout when waiting for the block pivot to end. Infinite wait if
        #  timeout is None
        self.timeout = timeout

        #: droppable helper to take and clean external snapshots. Can be
        #  construct with an ext_snapshot_helper to clean the snapshots of an
        #  aborted backup. Starting a backup will erase this helper.
        self._ext_snapshot_helper = ext_snapshot_helper

        #: used to redistribute events received by libvirt, as one event cannot
        #  be registered for multiple times. Necessary if no
        #  `ext_snapshot_helper` is given.
        self._callbacks_registrer = callbacks_registrer

        if not (ext_snapshot_helper or callbacks_registrer):
            raise AttributeError(
                "callbacks_registrer needed if no ext_snapshot_helper is given"
            )

        #: useful info collected during a pending backup, allowing to clean
        #  the backup if anything goes wrong
        self.pending_info = {}

        #: store the backup name (usually generated with the internal format)
        self._name = ""

        #: Used as lock when the backup is already running
        self._running = False

    @property
    def running(self):
        return self._running

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
        dom_all_disks = self._get_self_domain_disks()
        if not dev_disks:
            self.disks = dom_all_disks
        for dev in dev_disks:
            if dev in self.disks:
                continue
            self.disks[dev] = dom_all_disks[dev]

    def start(self):
        """
        Start the entire backup process for all disks in self.disks
        """
        assert not self.running
        assert self.dom and self.backup_dir
        if not os.path.exists(self.backup_dir):
            os.mkdir(self.backup_dir)

        logger.info("%s: Backup started", self.dom.name())
        definition = self.get_definition()
        definition["disks"] = {}

        try:
            self._running = True
            self._ext_snapshot_helper = DomExtSnapshot(
                self.dom, self.disks, self._callbacks_registrer, self.conn, self.timeout
            )

            snapshot_date, definition = self._snapshot_and_save_date(definition)

            self._name = self._main_backup_name_format(snapshot_date)
            definition["name"], self.pending_info["name"] = self._name, self._name
            self._dump_json_definition(definition)
            self._dump_pending_info()

            packager = self._get_packager()
            # TODO: handle backingStore cases
            with packager:
                for disk, prop in self.disks.items():
                    self._backup_disk(disk, prop, packager, definition)
                    self._ext_snapshot_helper.clean_for_disk(disk)

            self._dump_json_definition(definition)
            self.post_backup()
            self._clean_pending_info()
        except:
            self.clean_aborted()
            raise
        finally:
            self._running = False
        logger.info("%s: Backup finished", self.dom.name())

    def _get_packager(self):
        assert self._name, "_name attribute needs to be defined to get a packager"
        return self._get_write_packager(self._name)

    def _snapshot_and_save_date(self, definition):
        """
        Take a snapshot of all disks to backup and mark date into definition

        All disks are frozen when external snapshots have been taken, so we
        consider this step to be the backup date.

        :return snapshot_date, definition: return snapshot_date as `arrow`
            type, and the updated definition
        """
        snapshot_metadatas = self._ext_snapshot_helper.start()

        # all of our disks are snapshot, so the backup date is right now
        definition["date"] = snapshot_metadatas["date"].timestamp

        self.pending_info = definition.copy()
        self.pending_info["disks"] = {
            disk: {
                "src": prop["src"],
                "snapshot": snapshot_metadatas["disks"][disk]["snapshot"],
            }
            for disk, prop in self.disks.items()
        }
        self._dump_pending_info()

        return snapshot_metadatas["date"], definition

    def get_definition(self):
        """
        Get a json defining this backup
        """
        return {
            "domain_id": self.dom.ID(),
            "domain_name": self.dom.name(),
            "domain_xml": self.dom.XMLDesc(),
            "packager": {"type": self.packager, "opts": self.packager_opts},
            "version": virt_backup.VERSION,
        }

    def _backup_disk(self, disk, disk_properties, packager, definition):
        """
        Backup a disk and complete the definition by adding this disk

        :param disk: diskname to backup
        :param disk_properties: dictionary discribing our disk (typically
                                contained in self.disks[disk])
        :param packager: a BackupPackager object
        :param definition: dictionary representing the domain backup
        """
        snapshot_date = arrow.get(definition["date"]).to("local")
        logger.info("%s: Backup disk %s", self.dom.name(), disk)
        bak_img = "{}.{}".format(
            self._disk_backup_name_format(snapshot_date, disk), disk_properties["type"]
        )
        self.pending_info["disks"][disk]["target"] = bak_img
        self._dump_pending_info()

        if definition.get("disks", None) is None:
            definition["disks"] = {}
        definition["disks"][disk] = bak_img

        packager.add(disk_properties["src"], bak_img)

    def _disk_backup_name_format(self, snapdate, disk_name, *args, **kwargs):
        """
        Backup name format for each disk when no compression/compacting is set

        :param snapdate: date when external snapshots have been created
        :param disk_name: disk name currently being backup
        """
        return "{}_{}".format(self._main_backup_name_format(snapdate), disk_name)

    def post_backup(self):
        """
        Post backup process

        Unregister callback and close backup_target if is tarfile
        """
        if self._ext_snapshot_helper is not None:
            self._ext_snapshot_helper.clean()
            self._ext_snapshot_helper = None
        self._running = False

    def _parse_dom_xml(self):
        """
        Parse the domain's definition
        """
        return defusedxml.lxml.fromstring(self.dom.XMLDesc())

    def _dump_json_definition(self, definition):
        """
        Dump the backup definition as json

        Definition will describe our backup, with the date, backuped
        disks names and other informations
        """
        backup_date = arrow.get(definition["date"]).to("local")
        definition_path = os.path.join(
            self.backup_dir,
            "{}.{}".format(self._main_backup_name_format(backup_date), "json"),
        )
        with open(definition_path, "w") as json_definition:
            json.dump(definition, json_definition, indent=4)

    def _dump_pending_info(self):
        """
        Dump the temporary changes done, as json

        Useful
        """
        json_path = self._get_pending_info_json_path()
        with open(json_path, "w") as json_pending_info:
            json.dump(self.pending_info, json_pending_info, indent=4)

    def _clean_pending_info(self):
        os.remove(self._get_pending_info_json_path())
        self.pending_info = {}

    def _get_pending_info_json_path(self):
        backup_date = arrow.get(self.pending_info["date"]).to("local")
        json_path = os.path.join(
            self.backup_dir,
            "{}.{}.pending".format(self._main_backup_name_format(backup_date), "json"),
        )
        return json_path

    def clean_aborted(self):
        is_ext_snap_helper_needed = (
            not self._ext_snapshot_helper and self.pending_info.get("disks", None)
        )
        if is_ext_snap_helper_needed:
            self._ext_snapshot_helper = DomExtSnapshot(
                self.dom, self.disks, self._callbacks_registrer, self.conn, self.timeout
            )
            self._ext_snapshot_helper.metadatas = {
                "disks": {
                    disk: {"src": val["src"], "snapshot": val["snapshot"]}
                    for disk, val in self.pending_info["disks"].items()
                }
            }

        if self._ext_snapshot_helper:
            self._ext_snapshot_helper.clean()

        # If the name couldn't have been written, no packager has been created.
        if "name" in self.pending_info:
            packager = self._get_write_packager(self.pending_info["name"])
            try:
                self._clean_packager(packager)
            except FileNotFoundError:
                logger.info(
                    "%s: Packager not found, nothing to clean.", self.dom.name()
                )
        try:
            self._clean_pending_info()
        except FileNotFoundError:
            # Pending info had no time to be filled, so had not be dumped.
            pass

    def _clean_packager(self, packager):
        """
        If the package is shareable, will remove each disk backup then will
        only remove the packager if empty.
        """
        if packager.is_shareable:
            targets = (d["target"] for d in self.pending_info["disks"].values())
            with packager:
                for target in targets:
                    packager.remove(target)
                if packager.list():
                    # Other non related backups still exists, do not delete
                    # the package.
                    return

        packager.remove_package()

    def compatible_with(self, dombackup):
        """
        Is compatible with dombackup ?

        If the target is the same for both dombackup and self, same thing for
        packager and packager_opts, self and dombackup are considered
        compatibles.
        """
        same_domain = dombackup.dom.ID() == self.dom.ID()
        if not same_domain:
            return False

        attributes_to_compare = ("backup_dir", "packager")
        for a in attributes_to_compare:
            if getattr(self, a) != getattr(dombackup, a):
                return False

        # compare the packager_opts by converting them to json and diffing the strings
        same_package_opts = json.dumps(
            self.packager_opts, sort_keys=True
        ) == json.dumps(dombackup.packager_opts, sort_keys=True)
        if not same_package_opts:
            return False

        return True

    def merge_with(self, dombackup):
        self.add_disks(*dombackup.disks.keys())
        timeout = self.timeout or dombackup.timeout
        self.timeout = timeout
