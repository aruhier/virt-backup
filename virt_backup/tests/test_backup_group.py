
import pytest

from virt_backup.virt_backup import BackupGroup


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
