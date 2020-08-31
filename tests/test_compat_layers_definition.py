from deepdiff import DeepDiff
from packaging.version import parse as version_parser
import pytest

from virt_backup.compat_layers.definition import convert, ToV0_4


class TestV0_1ToV0_4:
    @pytest.mark.parametrize(
        "definition,expected",
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
    def test_convert(self, definition, expected):
        c = ToV0_4()
        c.convert(definition)

        diff = DeepDiff(definition, expected)
        assert not diff, "diff found between converted and expected definition"

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


@pytest.mark.parametrize(
    "definition,expected",
    [
        (
            {
                "compression": "gz",
                "compression_lvl": 6,
                "domain_id": 3,
                "domain_name": "test-domain",
                "domain_xml": "<domain type='kvm' id='3'></domain>",
                "disks": {
                    "vda": "20191001-003401_3_test-domain_vda.qcow2",
                },
                "version": "0.1.0",
                "date": 1569890041,
                "tar": "20191001-003401_3_test-domain.tar.gz",
            },
            {
                "name": "20191001-003401_3_test-domain",
                "domain_id": 3,
                "domain_name": "test-domain",
                "domain_xml": "<domain type='kvm' id='3'></domain>",
                "disks": {
                    "vda": "20191001-003401_3_test-domain_vda.qcow2",
                },
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
def test_convert(definition, expected):
    """
    Test conversion from the minimum version supported to the last version supported.
    """
    convert(definition)
    diff = DeepDiff(definition, expected)
    assert not diff, "diff found between converted definition and expected definition"
