
import pytest

from virt_backup.group import (
    BackupGroup, parse_host_pattern, match_domains_from_config,
    groups_from_dict
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


def test_parse_host_pattern_regex(fixture_build_mock_libvirtconn_filled):
    conn = fixture_build_mock_libvirtconn_filled
    matches = parse_host_pattern("r:^matching.?$", conn)
    domains = tuple(sorted(matches["domains"]))
    exclude = matches["exclude"]

    assert domains == ("matching", "matching2")
    assert not exclude


def test_parse_host_pattern_direct_name(fixture_build_mock_libvirtconn_filled):
    """
    Test parse_host_pattern directly with a domain name
    """
    conn = fixture_build_mock_libvirtconn_filled
    matches = parse_host_pattern("matching", conn)
    domains = tuple(sorted(matches["domains"]))
    exclude = matches["exclude"]

    assert domains == ("matching",)
    assert not exclude


def test_parse_host_pattern_exclude(fixture_build_mock_libvirtconn_filled):
    """
    Test parse_host_pattern with a pattern excluding a domain
    """
    conn = fixture_build_mock_libvirtconn_filled
    matches = parse_host_pattern("!matching", conn)
    domains = tuple(sorted(matches["domains"]))
    exclude = matches["exclude"]

    assert domains == ("matching",)
    assert exclude


def test_match_domains_from_config(fixture_build_mock_libvirtconn_filled):
    conn = fixture_build_mock_libvirtconn_filled
    host_config = {"host": "matching", "disks": ["vda", "vdb"]}

    matches = match_domains_from_config(host_config, conn)
    domains = tuple(sorted(matches["domains"]))
    exclude, disks = matches["exclude"], tuple(sorted(matches["disks"]))

    assert domains == ("matching",)
    assert not exclude
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
    assert not exclude


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
    assert not exclude


def test_groups_from_dict(fixture_build_mock_libvirtconn_filled):
    """
    Test groups_from_dict with only one group
    """
    conn = fixture_build_mock_libvirtconn_filled
    groups_config = {
        "test": {
            "target": "/mnt/test",
            "compression": "tar",
            "hosts": [
                {"host": "r:^matching\d?$", "disks": ["vda", "vdb"]},
                "!matching2", "nonexisting"
            ],
        },
    }

    groups = tuple(groups_from_dict(groups_config, conn))
    assert len(groups) == 1
    test_group = groups[0]

    target, compression = (
        test_group.default_bak_param[k] for k in ("target_dir", "compression")
    )
    assert target == "/mnt/test"
    assert compression == "tar"

    dombackups = test_group.backups
    assert len(dombackups) == 1

    matching_backup = dombackups[0]
    assert matching_backup.dom.name() == "matching"
    assert tuple(sorted(matching_backup.disks.keys())) == ("vda", "vdb")


def test_groups_from_dict_multiple_groups(
        fixture_build_mock_libvirtconn_filled):
    """
    Test match_domains_from_config with a str pattern
    """
    conn = fixture_build_mock_libvirtconn_filled
    groups_config = {
        "test0": {
            "target": "/mnt/test0",
            "compression": "tar",
            "hosts": ["matching2", ],
        },
        "test1": {
            "target": "/mnt/test1",
            "hosts": ["matching", "a"],
        },
    }

    groups = tuple(groups_from_dict(groups_config, conn))
    assert len(groups) == 2
    group0, group1 = groups

    assert sorted((group0.name, group1.name)) == ["test0", "test1"]
