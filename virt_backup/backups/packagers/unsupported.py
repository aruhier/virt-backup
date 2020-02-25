from virt_backup.exceptions import UnsupportedPackagerError
from . import (
    _AbstractBackupPackager,
    _AbstractReadBackupPackager,
    _AbstractWriteBackupPackager,
)


class UnsupportedBackupPackager(_AbstractBackupPackager):
    packager = ""
    reason = None

    def __init__(self, *args, **kwargs):
        raise UnsupportedPackagerError(self.packager, self.reason)

    def open(self):
        pass

    def close(self):
        pass

    def list(self):
        pass


class UnsupportedReadBackupPackager(
    _AbstractReadBackupPackager, UnsupportedBackupPackager
):
    def restore(self, name, target):
        pass


class UnsupportedWriteBackupPackager(
    _AbstractWriteBackupPackager, UnsupportedBackupPackager
):
    def add(self, src, name=None):
        pass

    def remove_package(self, name):
        pass


class UnsupportedReadBackupPackagerZSTD(UnsupportedReadBackupPackager):
    packager = "zstd"


class UnsupportedWriteBackupPackagerZSTD(UnsupportedWriteBackupPackager):
    packager = "zstd"
