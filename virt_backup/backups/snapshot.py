from collections import defaultdict
import logging
import os
import subprocess
import threading
import arrow
import defusedxml.lxml
import libvirt
import lxml.etree

from virt_backup.domains import get_domain_disks_of, get_xml_block_of_disk
from virt_backup.exceptions import DiskNotSnapshot, SnapshotNotStarted


logger = logging.getLogger("virt_backup")


class DomExtSnapshotCallbackRegistrer:

    _callback_id = None

    def __init__(self, conn):
        #: register callbacks, `{snapshot_path: callback}`
        self.callbacks = {}

        #: libvirt connection to use
        self.conn = conn

    def __enter__(self):
        return self.open()

    def __exit__(self, *exc):
        self.close()

    def open(self):
        self._callback_id = self.conn.domainEventRegisterAny(
            None, libvirt.VIR_DOMAIN_EVENT_ID_BLOCK_JOB, self.event_callback, None
        )

    def close(self):
        self.conn.domainEventDeregisterAny(self._callback_id)

    def event_callback(self, conn, dom, snap, event_id, status, *args):
        if status != libvirt.VIR_DOMAIN_BLOCK_JOB_READY:
            if status == libvirt.VIR_DOMAIN_BLOCK_JOB_FAILED:
                logger.error("Block job failed for snapshot %s", snap)

            return

        if snap not in self.callbacks:
            logger.error("Callback for snapshot %s called but not existing", snap)
            return None

        return self.callbacks[snap](conn, dom, snap, event_id, status, *args)


class DomExtSnapshot:
    """
    Libvirt domain backup
    """

    metadatas = None

    def __init__(self, dom, disks, callbacks_registrer, conn=None, timeout=None):
        #: domain to snapshot. Has to be a libvirt.virDomain object
        self.dom = dom

        self.disks = disks

        self._callbacks_registrer = callbacks_registrer

        #: timeout when waiting for the block pivot to end. Infinite wait if
        #  timeout is None
        self.timeout = timeout

        #: libvirt connection to use. If not sent, will use the connection used
        #  for self.domain
        self.conn = self.dom._conn if conn is None else conn

        #: used to trigger when block pivot ends, by snapshot path
        self._wait_for_pivot = defaultdict(threading.Event)

    def start(self):
        """
        Start the external snapshot
        """
        snapshot = self.external_snapshot()

        # all of our disks are frozen, so the backup date is right now
        snapshot_date = arrow.now()

        self.metadatas = {
            "date": snapshot_date,
            "disks": {
                disk: {
                    "src": prop["src"],
                    "snapshot": self._get_snapshot_path(prop["src"], snapshot),
                }
                for disk, prop in self.disks.items()
            },
        }

        return self.metadatas

    def external_snapshot(self):
        """
        Create an external snapshot in order to freeze the base image
        """
        snap_xml = self.gen_libvirt_snapshot_xml()
        return self.dom.snapshotCreateXML(
            snap_xml,
            (
                libvirt.VIR_DOMAIN_SNAPSHOT_CREATE_DISK_ONLY
                + libvirt.VIR_DOMAIN_SNAPSHOT_CREATE_ATOMIC
                + libvirt.VIR_DOMAIN_SNAPSHOT_CREATE_NO_METADATA
            ),
        )

    def gen_libvirt_snapshot_xml(self):
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

        all_domain_disks = get_domain_disks_of(
            defusedxml.lxml.fromstring(self.dom.XMLDesc())
        )
        for d in sorted(all_domain_disks.keys()):
            disk_el = lxml.etree.Element("disk")
            disk_el.attrib["name"] = d
            # Skipped disks need to have an entry, with a snapshot value
            # explicitly set to "no", otherwise libvirt will be created a
            # snapshot for them.
            disk_el.attrib["snapshot"] = "external" if d in self.disks else "no"
            disks_el.append(disk_el)

        return lxml.etree.tostring(xml_tree, pretty_print=True).decode()

    def _get_snapshot_path(self, parent_disk_path, snapshot):
        return "{}.{}".format(os.path.splitext(parent_disk_path)[0], snapshot.getName())

    def clean(self):
        if not self.metadatas:
            raise SnapshotNotStarted()

        disks = tuple(self.metadatas["disks"].keys())
        snapshot_paths = tuple(
            os.path.abspath(self.metadatas["disks"][disk]["snapshot"]) for disk in disks
        )
        try:
            for disk in disks:
                try:
                    self.clean_for_disk(disk)
                except Exception as e:
                    logger.critical(
                        (
                            "Failed to clean temp files of disk {} " "for domain {}: {}"
                        ).format(disk, self.dom.name(), e)
                    )
                    raise
        finally:
            for snapshot in snapshot_paths:
                self._callbacks_registrer.callbacks.pop(snapshot, None)

    def clean_for_disk(self, disk):
        if not self.metadatas:
            raise SnapshotNotStarted()
        elif disk not in self.metadatas["disks"]:
            raise DiskNotSnapshot(disk)

        snapshot_path = os.path.abspath(self.metadatas["disks"][disk]["snapshot"])
        disk_path = os.path.abspath(self.metadatas["disks"][disk]["src"])

        # Do not commit and pivot if our snapshot is not the current top disk
        current_disk_path = (
            get_xml_block_of_disk(self.dom.XMLDesc(), disk)
            .xpath("source")[0]
            .get("file")
        )
        if os.path.abspath(current_disk_path) != snapshot_path:
            logger.warning(
                "It seems that the domain configuration (and specifically the "
                "one related to its disks) has been changed. The current disk "
                "will not be committed nor pivoted with the external "
                "snapshot, to not break the backing chain.\n\n"
                "You might want to manually check, where your domain image is "
                "stored, if no temporary file is remaining ({}).".format(
                    os.path.dirname(current_disk_path)
                )
            )
            return

        if self.dom.isActive():
            self.blockcommit_disk(disk)
        else:
            self._qemu_img_commit(disk_path, snapshot_path)
            self._manually_pivot_disk(disk, disk_path)
            os.remove(snapshot_path)

        self.metadatas["disks"].pop(disk)
        self._callbacks_registrer.callbacks.pop(snapshot_path, None)

    def blockcommit_disk(self, disk):
        """
        Block commit

        Will allow to merge the external snapshot previously created with the
        disk main image
        Wait for the pivot to be triggered in case of active blockcommit.

        :param disk: diskname to blockcommit
        """
        snapshot_path = os.path.abspath(self.metadatas["disks"][disk]["snapshot"])
        self._callbacks_registrer.callbacks[snapshot_path] = self._pivot_callback

        logger.debug("%s: blockcommit %s to pivot snapshot", self.dom.name(), disk)
        self.dom.blockCommit(
            disk,
            None,
            None,
            0,
            (
                libvirt.VIR_DOMAIN_BLOCK_COMMIT_ACTIVE
                + libvirt.VIR_DOMAIN_BLOCK_COMMIT_SHALLOW
            ),
        )

        self._wait_for_pivot[snapshot_path].wait(timeout=self.timeout)
        self._wait_for_pivot.pop(snapshot_path)

    def _pivot_callback(self, conn, dom, snap, event_id, status, *args):
        """
        Pivot the snapshot

        If the received domain matches with the one associated to this backup,
        abort the blockjob, pivot it and delete the snapshot.
        """
        domain_matches = dom.ID() == self.dom.ID()
        if status == libvirt.VIR_DOMAIN_BLOCK_JOB_READY and domain_matches:
            dom.blockJobAbort(snap, libvirt.VIR_DOMAIN_BLOCK_JOB_ABORT_PIVOT)
            os.remove(snap)
            self._wait_for_pivot[os.path.abspath(snap)].set()

    def _qemu_img_commit(self, parent_disk_path, snapshot_path):
        """
        Use qemu-img to BlockCommit

        Libvirt does not allow to blockcommit a inactive domain, so have to use
        qemu-img instead.
        """
        return subprocess.check_call(
            ("qemu-img", "commit", "-b", parent_disk_path, snapshot_path)
        )

    def _manually_pivot_disk(self, disk, src):
        """
        Replace the disk src

        :param disk: disk name
        :param src: new disk path
        """
        dom_xml = defusedxml.lxml.fromstring(self.dom.XMLDesc())

        disk_xml = get_xml_block_of_disk(dom_xml, disk)
        disk_xml.xpath("source")[0].set("file", src)

        if self.conn.getLibVersion() >= 3000000:
            # update a disk is broken in libvirt < 3.0
            return self.dom.updateDeviceFlags(
                defusedxml.lxml.tostring(disk_xml).decode(),
                libvirt.VIR_DOMAIN_AFFECT_CONFIG,
            )
        else:
            return self.conn.defineXML(defusedxml.lxml.tostring(dom_xml).decode())
