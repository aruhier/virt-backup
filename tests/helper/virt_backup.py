
import arrow
import defusedxml.lxml
import libvirt
import lxml
import os

from virt_backup.domain import DomBackup


CUR_PATH = os.path.dirname(os.path.realpath(__file__))


class MockDomain():
    """
    Simulate a libvirt domain
    """
    def XMLDesc(self):
        """
        Return the definition of a testing domain
        """
        with open(os.path.join(CUR_PATH, "testdomain.xml")) as dom_xmlfile:
            dom_xml_str = dom_xmlfile.read()
        dom_xml = defusedxml.lxml.fromstring(dom_xml_str)
        dom_xml.set("id", str(self._id))
        elem_name = dom_xml.xpath("name")[0]
        if not elem_name:
            elem_name = dom_xml.makeelement("name")
            dom_xml.insert(0, elem_name)
        elem_name.text = self._name
        return lxml.etree.tostring(dom_xml, pretty_print=True).decode()

    def ID(self):
        return self._id

    def name(self):
        return self._name

    def __init__(self, _conn, name="test", id=1, *args, **kwargs):
        self._conn = _conn
        self._name = name
        self._id = id


class MockConn():
    """
    Simulate a libvirt connection
    """
    def listAllDomains(self):
        return self._domains

    def lookupByName(self, name):
        for d in self._domains:
            if d.name() == name:
                return d
        raise libvirt.libvirtError("Domain not found")

    def __init__(self, _domains=None, *args, **kwargs):
        self._domains = _domains or []


def build_completed_backups(backup_dir):
    domain_names = ("a", "b", "vm-10", "matching", "matching2")
    backup_properties = (
        (arrow.get("2016-07-08 18:30:02"), None),
        (arrow.get("2014-05-01 00:30:00"), "tar"),
        (arrow.get("2016-12-08 14:28:13"), "xz"),
    )
    conn = MockConn()
    for domain_id, domain_name in enumerate(domain_names):
        domain_bdir = os.path.join(backup_dir, domain_name)
        os.mkdir(domain_bdir)
        domain = MockDomain(conn, name=domain_name, id=domain_id)
        dbackup = DomBackup(
            domain, domain_bdir, dev_disks=("vda", "vdb")
        )

        for bakdate, compression in backup_properties:
            dbackup.compression = compression
            definition = dbackup.get_definition()
            definition["date"] = bakdate.timestamp
            if compression:
                tar = dbackup.get_new_tar(domain_bdir, bakdate)
                if compression == "xz":
                    definition["tar"] = tar.fileobj._fp.name
                else:
                    definition["tar"] = tar.fileobj.name
            for disk in dbackup.disks:
                # create empty files as our backup images
                img_name = "{}.qcow2".format(
                    dbackup._disk_backup_name_format(bakdate, disk),
                )
                definition["files"][disk] = img_name

                img_complete_path = os.path.join(domain_bdir, img_name)
                with open(img_complete_path, "w"):
                    continue
                if compression:
                    # add img to the tar file and remove it
                    tar.add(img_complete_path)
                    os.path.remove(img_complete_path)
            dbackup._dump_json_definition(definition)

    return (bp[0] for bp in backup_properties)
