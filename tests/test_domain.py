import pytest

from virt_backup.domains import (
    search_domains_regex,
    get_domain_disks_of,
    get_domain_incompatible_disks_of,
)
from virt_backup.exceptions import DiskNotFoundError

from helper.virt_backup import MockDomain


def test_get_domain_disks_of(build_mock_domain):
    domain = build_mock_domain
    vda = get_domain_disks_of(domain.XMLDesc(), "vda", "vdb")

    assert "vda" in vda


def test_get_domain_incompatible_disks_of(build_mock_domain):
    domain = build_mock_domain
    disks = get_domain_incompatible_disks_of(domain.XMLDesc())

    assert disks == ("vdz",)


def test_get_domain_disks_of_disk_not_found(build_mock_domain):
    domain = build_mock_domain
    with pytest.raises(DiskNotFoundError):
        get_domain_disks_of(domain.XMLDesc(), "vda", "vdc")


def test_search_domains_regex(build_mock_libvirtconn):
    conn = build_mock_libvirtconn
    domain_names = ("dom1", "dom2", "dom3", "test")
    conn._domains = [MockDomain(name=dom_name, _conn=conn) for dom_name in domain_names]

    matches = list(sorted(search_domains_regex(r"^dom\d$", conn)))
    expected = list(sorted(domain_names))
    expected.remove("test")

    assert matches == expected


def test_search_domains_regex_not_found(build_mock_libvirtconn, build_mock_domain):
    """
    Search a non existing domain
    """
    conn = build_mock_libvirtconn
    conn._domains = [build_mock_domain]

    matches = list(search_domains_regex("^dom$", conn))
    assert matches == []
