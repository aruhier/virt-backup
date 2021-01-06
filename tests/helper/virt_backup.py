import os
import arrow
import libvirt
import lxml
import lxml.etree

from virt_backup.backups import (
    DomBackup,
    DomExtSnapshotCallbackRegistrer,
    ReadBackupPackagers,
    WriteBackupPackagers,
)
from virt_backup.groups import BackupGroup


CUR_PATH = os.path.dirname(os.path.realpath(__file__))


class MockDomain:
    """
    Simulate a libvirt domain
    """

    def XMLDesc(self):
        """
        Return the definition of a testing domain
        """
        return lxml.etree.tostring(self.dom_xml, pretty_print=True).decode()

    def ID(self):
        return self.dom_xml.get("id")

    def name(self):
        return self.dom_xml.xpath("name")[0].text

    def state(self):
        return self._state

    def isActive(self):
        state_id = self.state()[0]
        return state_id >= 1 and state_id <= 3

    def set_name(self, name):
        elem_name = self.dom_xml.xpath("name")[0]
        if elem_name is None:
            elem_name = self.dom_xml.makeelement("name")
            self.dom_xml.insert(0, elem_name)
        elem_name.text = name

    def set_id(self, id):
        self.dom_xml.set("id", str(id))

    def set_state(self, state_id, reason_id):
        self._state = [state_id, reason_id]

    def set_storage_basedir(self, basedir):
        """
        Change the basedir of all attached disks

        :param basedir: new basedir
        """
        for elem in self.dom_xml.xpath("devices/disk"):
            try:
                if (
                    elem.get("device", None) == "disk"
                    and elem.get("type", None) == "file"
                ):
                    src = elem.xpath("source")[0]
                    img = src.get("file")
                    new_path = os.path.join(basedir, os.path.basename(img))
                    src.set("file", new_path)
            except IndexError:
                continue

    def snapshotCreateXML(self, xmlDesc, flags=0):
        return self._mock_snapshot(xmlDesc, flags)

    def set_mock_snapshot_create(self, mock):
        self._mock_snapshot = mock

    def updateDeviceFlags(self, xml, flags):
        new_device_xml = lxml.etree.fromstring(
            xml, lxml.etree.XMLParser(resolve_entities=False)
        )

        address = new_device_xml.get("address")
        device_to_replace = self._find_device_with_address(address)

        self.dom_xml.xpath("devices")[0].replace(device_to_replace, new_device_xml)

    def _find_device_with_address(self, address):
        for elem in self.dom_xml.xpath("devices/*"):
            try:
                if elem.get("address", None) == address:
                    return elem
            except IndexError:
                continue
        raise Exception("Device not found")

    def __init__(self, _conn, name="test", id=1, *args, **kwargs):
        self._conn = _conn
        self._state = [1, 1]
        self._mock_snapshot = lambda *args: MockSnapshot(name)

        with open(os.path.join(CUR_PATH, "testdomain.xml")) as dom_xmlfile:
            self.dom_xml = lxml.etree.fromstring(
                dom_xmlfile.read(), lxml.etree.XMLParser(resolve_entities=False)
            )
        self.set_id(id)
        self.set_name(name)


class MockSnapshot:
    def getName(self):
        return self._name

    def __init__(self, name):
        self._name = name


class MockConn:
    """
    Simulate a libvirt connection
    """

    _libvirt_version = 3000000

    def listAllDomains(self):
        return self._domains

    def lookupByName(self, name):
        for d in self._domains:
            if d.name() == name:
                return d
        raise libvirt.libvirtError("Domain not found")

    def defineXML(self, xml):
        md = MockDomain(_conn=self)
        md.dom_xml = lxml.etree.fromstring(
            xml, lxml.etree.XMLParser(resolve_entities=False)
        )
        for _, d in enumerate(self._domains):
            if d.ID() == md.ID():
                d.dom_xml = md.dom_xml
                return d

        self._domains.append(md)
        return md

    def getLibVersion(self):
        return self._libvirt_version

    def __init__(self, _domains=None, *args, **kwargs):
        self._domains = _domains or []


def build_complete_backup_files_from_domainbackup(dbackup, date):
    """
    :returns definition: updated definition from backuped files
    """
    definition = dbackup.get_definition()
    definition["date"] = date.int_timestamp
    definition["disks"] = {}

    backup_dir = dbackup.backup_dir
    definition["path"] = backup_dir

    definition["name"] = dbackup._main_backup_name_format(
        arrow.get(definition["date"]).to("local")
    )
    packager = dbackup._get_write_packager(definition["name"])

    with packager:
        for disk in dbackup.disks:
            # create empty files as our backup images
            img_name = "{}.qcow2".format(
                dbackup._disk_backup_name_format(date, disk),
            )
            definition["disks"][disk] = img_name

            img_complete_path = os.path.join(backup_dir, img_name)
            with open(img_complete_path, "w"):
                pass
            if dbackup.packager != "directory":
                packager.add(img_complete_path, img_name)
                os.remove(img_complete_path)
    return definition


def build_completed_backups(backup_dir):
    domain_names = ("a", "b", "vm-10", "matching", "matching2")
    backup_properties = (
        (arrow.get("2016-07-08 19:40:02").to("local"), "directory", {}),
        (arrow.get("2016-07-08 18:40:02").to("local"), "directory", {}),
        (arrow.get("2016-07-08 18:30:02").to("local"), "directory", {}),
        (arrow.get("2016-07-08 17:40:02").to("local"), "directory", {}),
        (arrow.get("2016-07-07 19:40:02").to("local"), "directory", {}),
        (arrow.get("2016-07-07 21:40:02").to("local"), "directory", {}),
        (arrow.get("2016-07-06 20:40:02").to("local"), "directory", {}),
        (arrow.get("2016-04-08 19:40:02").to("local"), "directory", {}),
        (arrow.get("2014-05-01 00:30:00").to("local"), "tar", {}),
        (arrow.get("2016-03-08 14:28:13").to("local"), "tar", {"compression": "xz"}),
    )
    conn = MockConn()
    for domain_id, domain_name in enumerate(domain_names):
        domain_bdir = os.path.join(backup_dir, domain_name)
        os.mkdir(domain_bdir)
        domain = MockDomain(conn, name=domain_name, id=domain_id)
        dbackup = build_dombackup(domain, domain_bdir, dev_disks=("vda", "vdb"))

        for bakdate, packager, packager_opts in backup_properties:
            dbackup.packager = packager
            dbackup.packager_opts = packager_opts.copy()

            definition = build_complete_backup_files_from_domainbackup(dbackup, bakdate)
            dbackup._dump_json_definition(definition)
        # create a bad json file
        with open(os.path.join(domain_bdir, "badfile.json"), "w"):
            pass

    return (domain_names, (bp[0] for bp in backup_properties))


def build_dombackup(dom, *dombackup_args, **dombackup_kwargs):
    callbacks_registrer = DomExtSnapshotCallbackRegistrer(dom._conn)
    return DomBackup(
        dom,
        *dombackup_args,
        callbacks_registrer=callbacks_registrer,
        **dombackup_kwargs
    )


def build_backup_group(conn, *group_args, **group_kwargs):
    callbacks_registrer = DomExtSnapshotCallbackRegistrer(conn)
    return BackupGroup(
        *group_args, callbacks_registrer=callbacks_registrer, **group_kwargs
    )
