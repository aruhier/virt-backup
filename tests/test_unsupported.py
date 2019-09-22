import pytest

from virt_backup.exceptions import UnsupportedPackagerError
from virt_backup.backups.packagers import (
    ReadBackupPackagers, WriteBackupPackagers
)
from virt_backup.backups.packagers.unsupported import (
    UnsupportedReadBackupPackagerZSTD, UnsupportedWriteBackupPackagerZSTD
)


@pytest.mark.no_extra
@pytest.mark.no_zstd
class UnsupportedZSTD():

    def test_zstd_unsupported(self):
        assert isinstance(
            ReadBackupPackagers.zstd, UnsupportedReadBackupPackagerZSTD
        )
        assert isinstance(
            WriteBackupPackagers.zstd, UnsupportedWriteBackupPackagerZSTD
        )

    def test_unsupported_error(self):
        for packager in ReadBackupPackagers.zstd, WriteBackupPackagers.zstd:
            with pytest.raises(UnsupportedPackagerError):
                packager()
