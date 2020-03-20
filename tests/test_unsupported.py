import pytest

from virt_backup.exceptions import UnsupportedPackagerError
from virt_backup.backups.packagers import ReadBackupPackagers, WriteBackupPackagers
from virt_backup.backups.packagers.unsupported import (
    UnsupportedReadBackupPackagerZSTD,
    UnsupportedWriteBackupPackagerZSTD,
)


@pytest.mark.no_extra
@pytest.mark.no_zstd
class TestUnsupportedZSTD:
    def test_zstd_unsupported(self):
        assert ReadBackupPackagers.zstd.value == UnsupportedReadBackupPackagerZSTD
        assert WriteBackupPackagers.zstd.value == UnsupportedWriteBackupPackagerZSTD

    def test_unsupported_error(self):
        packagers = (ReadBackupPackagers.zstd.value, WriteBackupPackagers.zstd.value)
        for packager in packagers:
            with pytest.raises(UnsupportedPackagerError):
                packager()
