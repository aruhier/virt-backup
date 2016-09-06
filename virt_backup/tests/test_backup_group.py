
import pytest

from virt_backup.virt_backup import BackupGroup

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
