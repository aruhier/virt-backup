
import pytest

from virt_backup.virt_backup import (
    BackupGroup, search_domains_regex, parse_host_pattern,
    match_domains_from_config
)

from helper.virt_backup import MockDomain


def test_backup_group():
    backup_group = BackupGroup()

    assert len(backup_group.backups) == 0


def test_backup_group_with_domain(fixture_build_mock_domain):
    dom = fixture_build_mock_domain
    backup_group = BackupGroup(domlst=((dom, None),))

    assert len(backup_group.backups) == 1
    assert backup_group.backups[0].dom == dom


def test_backup_group_add_backup(fixture_build_mock_domain):
    backup_group = BackupGroup()
    dom = fixture_build_mock_domain

    backup_group.add_backup(dom)
    assert len(backup_group.backups) == 1
    assert backup_group.backups[0].dom == dom


def test_backup_group_dedup_backup_domain(fixture_build_mock_domain):
    """
    Test to add 2 times the same backup and check that it's not duplicated
    """
    dom = fixture_build_mock_domain
    backup_group = BackupGroup(domlst=(dom, ))

    backup_group.add_backup(dom)
    assert len(backup_group.backups) == 1


def test_backup_group_search(fixture_build_mock_domain):
    dom = fixture_build_mock_domain
    backup_group = BackupGroup(domlst=(dom, ))

    dombak = next(backup_group.search(dom))
    assert dombak == backup_group.backups[0]


def test_backup_group_search_not_found(fixture_build_mock_domain):
    dom = fixture_build_mock_domain
    backup_group = BackupGroup()

    with pytest.raises(StopIteration):
        next(backup_group.search(dom))


def test_backup_group_start(fixture_build_mock_domain, mocker):
    backup_group = BackupGroup(domlst=(fixture_build_mock_domain, ))
    backup_group.backups[0].start = mocker.stub()

    backup_group.start()
    assert backup_group.backups[0].start.called


def test_backup_group_propagate_attr(fixture_build_mock_domain):
    backup_group = BackupGroup(
        domlst=(fixture_build_mock_domain, ), compression="xz"
    )
    assert backup_group.backups[0].compression == "xz"

    backup_group.default_bak_param["target_dir"] = "/test"
    assert backup_group.backups[0].target_dir is None
    backup_group.propagate_default_backup_attr()
    assert backup_group.backups[0].target_dir == "/test"


def test_backup_group_propagate_attr_multiple_domains(mocker):
    backup_group = BackupGroup(
        domlst=(
            MockDomain(_conn=mocker.stub()), MockDomain(_conn=mocker.stub())
        ), compression="xz"
    )
    for b in backup_group.backups:
        assert b.compression == "xz"

    backup_group.default_bak_param["target_dir"] = "/test"
    for b in backup_group.backups:
        assert b.target_dir is None

    backup_group.propagate_default_backup_attr()
    for b in backup_group.backups:
        assert b.target_dir is "/test"


def test_search_domains_regex(fixture_build_mock_libvirtconn):
    conn = fixture_build_mock_libvirtconn
    domain_names = ("dom1", "dom2", "dom3", "test")
    conn._domains = [
        MockDomain(name=dom_name, _conn=conn) for dom_name in domain_names
    ]

    matches = list(sorted(search_domains_regex("^dom\d$", conn)))
    expected = list(sorted(domain_names))
    expected.remove("test")

    assert matches == expected


def test_search_domains_regex_not_found(
        fixture_build_mock_libvirtconn, fixture_build_mock_domain):
    """
    Search a non existing domain
    """
    conn = fixture_build_mock_libvirtconn
    conn._domains = [fixture_build_mock_domain]

    matches = list(search_domains_regex("^dom$", conn))
    assert matches == []


def test_parse_host_pattern_regex(fixture_build_mock_libvirtconn_filled):
    conn = fixture_build_mock_libvirtconn_filled
    matches = parse_host_pattern("r:^matching.?$", conn)
    domains = tuple(sorted(matches["domains"]))
    exclude = matches["exclude"]

    assert domains == ("matching", "matching2")
    assert exclude is False


def test_parse_host_pattern_direct_name(fixture_build_mock_libvirtconn_filled):
    """
    Test parse_host_pattern directly with a domain name
    """
    conn = fixture_build_mock_libvirtconn_filled
    matches = parse_host_pattern("matching", conn)
    domains = tuple(sorted(matches["domains"]))
    exclude = matches["exclude"]

    assert domains == ("matching",)
    assert exclude is False


def test_match_domains_from_config(fixture_build_mock_libvirtconn_filled):
    conn = fixture_build_mock_libvirtconn_filled
    host_config = {"host": "matching", "disks": ["vda", "vdb"]}

    matches = match_domains_from_config(host_config, conn)
    domains = tuple(sorted(matches["domains"]))
    exclude, disks = matches["exclude"], tuple(sorted(matches["disks"]))

    assert domains == ("matching",)
    assert exclude is False
    assert disks == ("vda", "vdb")


def test_match_domains_from_config_unexisting(
        fixture_build_mock_libvirtconn_filled):
    """
    Test match_domains_from_config with a non existing domain
    """
    conn = fixture_build_mock_libvirtconn_filled
    host_config = {"host": "nonexisting", "disks": ["vda", "vdb"]}

    matches = match_domains_from_config(host_config, conn)
    domains = tuple(sorted(matches["domains"]))
    exclude = matches["exclude"]

    assert domains == tuple()
    assert exclude is False


def test_match_domains_from_config_str(fixture_build_mock_libvirtconn_filled):
    """
    Test match_domains_from_config with a str pattern
    """
    conn = fixture_build_mock_libvirtconn_filled
    host_config = "r:matching\d?"

    matches = match_domains_from_config(host_config, conn)
    domains = tuple(sorted(matches["domains"]))
    exclude = matches["exclude"]

    assert domains == ("matching", "matching2")
    assert exclude is False
