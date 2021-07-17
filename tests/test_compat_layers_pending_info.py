from deepdiff import DeepDiff
from packaging.version import parse as version_parser
import pytest

from virt_backup.compat_layers.pending_info import V0_4ToV0_5_2, convert, ToV0_4


class TestV0_1ToV0_4:
    @pytest.mark.parametrize(
        "pending_info,expected",
        [
            (
                {
                    "compression": "gz",
                    "compression_lvl": 6,
                    "domain_id": 3,
                    "domain_name": "test-domain",
                    "version": "0.1.0",
                    "date": 1569890041,
                    "tar": "20191001-003401_3_test-domain.tar.gz",
                },
                {
                    "name": "20191001-003401_3_test-domain",
                    "domain_id": 3,
                    "domain_name": "test-domain",
                    "version": "0.4.0",
                    "date": 1569890041,
                    "packager": {
                        "type": "tar",
                        "opts": {
                            "compression": "gz",
                            "compression_lvl": 6,
                        },
                    },
                },
            ),
            (
                {
                    "domain_id": 3,
                    "domain_name": "test-domain",
                    "version": "0.1.0",
                    "date": 1569890041,
                },
                {
                    "name": "20191001-003401_3_test-domain",
                    "domain_id": 3,
                    "domain_name": "test-domain",
                    "version": "0.4.0",
                    "date": 1569890041,
                    "packager": {
                        "type": "directory",
                        "opts": {},
                    },
                },
            ),
            (
                {
                    "name": "20191001-003401_3_test-domain",
                    "domain_id": 3,
                    "domain_name": "test-domain",
                    "version": "0.4.0",
                    "date": 1569890041,
                    "packager": {
                        "type": "tar",
                        "opts": {},
                    },
                },
                {
                    "name": "20191001-003401_3_test-domain",
                    "domain_id": 3,
                    "domain_name": "test-domain",
                    "version": "0.4.0",
                    "date": 1569890041,
                    "packager": {
                        "type": "tar",
                        "opts": {},
                    },
                },
            ),
        ],
    )
    def test_convert(self, pending_info, expected):
        c = ToV0_4()
        c.convert(pending_info)

        diff = DeepDiff(pending_info, expected)
        assert not diff, "diff found between converted and expected pending_info"

    @pytest.mark.parametrize(
        "version,expected",
        [
            ("0.1.0", True),
            ("0.4.0", False),
            ("0.5.0", False),
        ],
    )
    def test_is_needed(self, version, expected):
        c = ToV0_4()
        assert c.is_needed(version_parser(version)) == expected


class TestV0_4ToV0_5_2:
    @pytest.mark.parametrize(
        "pending_info,expected",
        [
            (
                {
                    "compression": "gz",
                    "compression_lvl": 6,
                    "domain_id": 3,
                    "domain_name": "test-domain",
                    "version": "0.4.0",
                    "date": 1569890041,
                    "tar": "20191001-003401_3_test-domain.tar.gz",
                    "packager": {
                        "type": "tar",
                        "opts": {
                            "compression": "gz",
                            "compression_lvl": 6,
                        },
                    },
                },
                {
                    "compression": "gz",
                    "compression_lvl": 6,
                    "domain_id": 3,
                    "domain_name": "test-domain",
                    "version": "0.5.2",
                    "date": 1569890041,
                    "tar": "20191001-003401_3_test-domain.tar.gz",
                    "packager": {
                        "type": "tar",
                        "opts": {
                            "compression": "gz",
                            "compression_lvl": 6,
                        },
                    },
                },
            ),
            (
                {
                    "name": "20191001-003401_3_test-domain",
                    "domain_id": 3,
                    "domain_name": "test-domain",
                    "version": "0.4.0",
                    "date": 1569890041,
                    "packager": {
                        "type": "tar",
                        "opts": {},
                    },
                    "domain_xml": "<domain type='kvm' id='3'>\n <name>vm-test-domain</name>\n <uuid>a0b93945-e5f6-46b0-8c5a-9220882fa93c</uuid>\n  <devices>\n <disk type='file' device='disk'>\n      <driver name='qemu' type='qcow2'/>\n      <source file='/foo/vda.qcow2'/>\n      <backingStore/>\n      <target dev='vda' bus='virtio'/>\n      <alias name='virtio-disk0'/>\n      <address type='pci' domain='0x0000' bus='0x00' slot='0x07' function='0x0'/>\n    </disk>\n    </devices>\n  </domain>\n",
                    "disks": {
                        "vda": {
                            "src": "/foo/vda.qcow2",
                            "snapshot": "/foo/vda.snapshot",
                            "target": "/foo/target_vda.qcow2",
                        },
                    },
                },
                {
                    "name": "20191001-003401_3_test-domain",
                    "domain_id": 3,
                    "domain_name": "test-domain",
                    "version": "0.5.2",
                    "date": 1569890041,
                    "packager": {
                        "type": "tar",
                        "opts": {},
                    },
                    "domain_xml": "<domain type='kvm' id='3'>\n <name>vm-test-domain</name>\n <uuid>a0b93945-e5f6-46b0-8c5a-9220882fa93c</uuid>\n  <devices>\n <disk type='file' device='disk'>\n      <driver name='qemu' type='qcow2'/>\n      <source file='/foo/vda.qcow2'/>\n      <backingStore/>\n      <target dev='vda' bus='virtio'/>\n      <alias name='virtio-disk0'/>\n      <address type='pci' domain='0x0000' bus='0x00' slot='0x07' function='0x0'/>\n    </disk>\n    </devices>\n  </domain>\n",
                    "disks": {
                        "vda": {
                            "src": "/foo/vda.qcow2",
                            "snapshot": "/foo/vda.snapshot",
                            "target": "/foo/target_vda.qcow2",
                            "type": "qcow2",
                        },
                    },
                },
            ),
            (
                {
                    "name": "20191001-003401_3_test-domain",
                    "domain_id": 3,
                    "domain_name": "test-domain",
                    "version": "0.4.0",
                    "date": 1569890041,
                    "packager": {
                        "type": "tar",
                        "opts": {},
                    },
                    "domain_xml": "<domain type='kvm' id='3'>\n <name>vm-test-domain</name>\n <uuid>a0b93945-e5f6-46b0-8c5a-9220882fa93c</uuid>\n  <devices>\n <disk type='file' device='disk'>\n      <driver name='qemu' type='qcow2'/>\n      <source file='/foo/vda.qcow2'/>\n <backingStore/>\n      <target dev='vda' bus='virtio'/>\n <alias name='virtio-disk0'/>\n      <address type='pci' domain='0x0000' bus='0x00' slot='0x07' function='0x0'/>\n </disk>\n    <disk type='file' device='disk'>\n      <driver name='qemu' type='raw'/>\n      <source file='/foo/vdb.qcow2'/>\n      <backingStore/>\n      <target dev='vdb' bus='virtio'/>\n      <alias name='virtio-disk1'/>\n      <address type='pci' domain='0x0000' bus='0x01' slot='0x07' function='0x0'/>\n    </disk>\n    </devices>\n  </domain>\n",
                    "disks": {
                        "vda": {
                            "src": "/foo/vda.qcow2",
                            "snapshot": "/foo/vda.snapshot",
                            "target": "/foo/target_vda.qcow2",
                            "type": "qcow2",
                        },
                        "vdb": {
                            "src": "/foo/vdb.img",
                            "snapshot": "/foo/vdb.snapshot",
                            "target": "/foo/target_vdb.img",
                        },
                    },
                },
                {
                    "name": "20191001-003401_3_test-domain",
                    "domain_id": 3,
                    "domain_name": "test-domain",
                    "version": "0.5.2",
                    "date": 1569890041,
                    "packager": {
                        "type": "tar",
                        "opts": {},
                    },
                    "domain_xml": "<domain type='kvm' id='3'>\n <name>vm-test-domain</name>\n <uuid>a0b93945-e5f6-46b0-8c5a-9220882fa93c</uuid>\n  <devices>\n <disk type='file' device='disk'>\n      <driver name='qemu' type='qcow2'/>\n      <source file='/foo/vda.qcow2'/>\n <backingStore/>\n      <target dev='vda' bus='virtio'/>\n <alias name='virtio-disk0'/>\n      <address type='pci' domain='0x0000' bus='0x00' slot='0x07' function='0x0'/>\n </disk>\n    <disk type='file' device='disk'>\n      <driver name='qemu' type='raw'/>\n      <source file='/foo/vdb.qcow2'/>\n      <backingStore/>\n      <target dev='vdb' bus='virtio'/>\n      <alias name='virtio-disk1'/>\n      <address type='pci' domain='0x0000' bus='0x01' slot='0x07' function='0x0'/>\n    </disk>\n    </devices>\n  </domain>\n",
                    "disks": {
                        "vda": {
                            "src": "/foo/vda.qcow2",
                            "snapshot": "/foo/vda.snapshot",
                            "target": "/foo/target_vda.qcow2",
                            "type": "qcow2",
                        },
                        "vdb": {
                            "src": "/foo/vdb.img",
                            "snapshot": "/foo/vdb.snapshot",
                            "target": "/foo/target_vdb.img",
                            "type": "raw",
                        },
                    },
                },
            ),
        ],
    )
    def test_convert(self, pending_info, expected):
        c = V0_4ToV0_5_2()
        c.convert(pending_info)

        diff = DeepDiff(pending_info, expected)
        assert not diff, "diff found between converted and expected pending_info"

    @pytest.mark.parametrize(
        "version,expected",
        [
            ("0.4.0", True),
            ("0.5.2", False),
            ("0.6.2", False),
        ],
    )
    def test_is_needed(self, version, expected):
        c = V0_4ToV0_5_2()
        assert c.is_needed(version_parser(version)) == expected


@pytest.mark.parametrize(
    "pending_info,expected",
    [
        (
            {
                "compression": "gz",
                "compression_lvl": 6,
                "domain_id": 3,
                "domain_name": "test-domain",
                "domain_xml": "<domain type='kvm' id='3'>\n <name>vm-test-domain</name>\n <uuid>a0b93945-e5f6-46b0-8c5a-9220882fa93c</uuid>\n  <devices>\n <disk type='file' device='disk'>\n      <driver name='qemu' type='qcow2'/>\n      <source file='/foo/vda.qcow2'/>\n      <backingStore/>\n      <target dev='vda' bus='virtio'/>\n      <alias name='virtio-disk0'/>\n      <address type='pci' domain='0x0000' bus='0x00' slot='0x07' function='0x0'/>\n    </disk>\n    </devices>\n  </domain>\n",
                "disks": {
                    "vda": {
                        "src": "/tmp/test/vda.qcow2",
                        "snapshot": "/tmp/test/vda.qcow2.snap",
                        "target": "20191001-003401_3_test-domain_vda.qcow2",
                    },
                },
                "version": "0.1.0",
                "date": 1569890041,
                "tar": "20191001-003401_3_test-domain.tar.gz",
            },
            {
                "name": "20191001-003401_3_test-domain",
                "domain_id": 3,
                "domain_name": "test-domain",
                "domain_xml": "<domain type='kvm' id='3'>\n <name>vm-test-domain</name>\n <uuid>a0b93945-e5f6-46b0-8c5a-9220882fa93c</uuid>\n  <devices>\n <disk type='file' device='disk'>\n      <driver name='qemu' type='qcow2'/>\n      <source file='/foo/vda.qcow2'/>\n      <backingStore/>\n      <target dev='vda' bus='virtio'/>\n      <alias name='virtio-disk0'/>\n      <address type='pci' domain='0x0000' bus='0x00' slot='0x07' function='0x0'/>\n    </disk>\n    </devices>\n  </domain>\n",
                "disks": {
                    "vda": {
                        "src": "/tmp/test/vda.qcow2",
                        "snapshot": "/tmp/test/vda.qcow2.snap",
                        "target": "20191001-003401_3_test-domain_vda.qcow2",
                        "type": "qcow2",
                    },
                },
                "version": "0.5.2",
                "date": 1569890041,
                "packager": {
                    "type": "tar",
                    "opts": {
                        "compression": "gz",
                        "compression_lvl": 6,
                    },
                },
            },
        ),
        (
            {
                "domain_id": 3,
                "domain_name": "test-domain",
                "version": "0.1.0",
                "date": 1569890041,
            },
            {
                "name": "20191001-003401_3_test-domain",
                "domain_id": 3,
                "domain_name": "test-domain",
                "version": "0.5.2",
                "date": 1569890041,
                "packager": {
                    "type": "directory",
                    "opts": {},
                },
            },
        ),
        (
            {
                "name": "20191001-003401_3_test-domain",
                "domain_id": 3,
                "domain_name": "test-domain",
                "version": "0.4.0",
                "date": 1569890041,
                "packager": {
                    "type": "tar",
                    "opts": {},
                },
            },
            {
                "name": "20191001-003401_3_test-domain",
                "domain_id": 3,
                "domain_name": "test-domain",
                "version": "0.5.2",
                "date": 1569890041,
                "packager": {
                    "type": "tar",
                    "opts": {},
                },
            },
        ),
    ],
)
def test_convert(pending_info, expected):
    """
    Test conversion from the minimum version supported to the last version supported.
    """
    convert(pending_info)
    diff = DeepDiff(pending_info, expected)
    assert (
        not diff
    ), "diff found between converted pending_info and expected pending_info"
