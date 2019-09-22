from virt_backup.exceptions import UnsupportedPackagerError
from . import (
    _AbstractBackupPackager, _AbstractReadBackupPackager,
    _AbstractWriteBackupPackager
)


class UnsupportedBackupPackager(_AbstractBackupPackager):
    packager = ""
    reason = None

    def __init__(self, *args, **kwargs):
        raise UnsupportedPackagerError(self.packager, self.reason)


class UnsupportedReadBackupPackager(
        _AbstractReadBackupPackager, UnsupportedBackupPackager
):
    pass


class UnsupportedWriteBackupPackager(
        _AbstractWriteBackupPackager, UnsupportedBackupPackager
):
    pass


class UnsupportedReadBackupPackagerZSTD(UnsupportedReadBackupPackager):
    packager = "zstd"


class UnsupportedWriteBackupPackagerZSTD(UnsupportedWriteBackupPackager):
    packager = "zstd"
