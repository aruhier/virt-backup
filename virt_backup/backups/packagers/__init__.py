from abc import ABC, abstractmethod
from enum import Enum
import logging

from virt_backup.exceptions import (
    BackupPackagerNotOpenedError,
    BackupPackagerOpenedError,
)


logger = logging.getLogger("virt_backup")


def _opened_only(f):
    def wrapper(self, *args, **kwargs):
        self.assert_opened()
        return f(self, *args, **kwargs)

    return wrapper


def _closed_only(f):
    def wrapper(self, *args, **kwargs):
        self.assert_closed()
        return f(self, *args, **kwargs)

    return wrapper


class _AbstractBackupPackager(ABC):
    closed = True
    #: is_shareable indicates if the same packager can be shared with multiple
    #: backups.
    is_shareable = False

    def __init__(self, name=None):
        #: Used for logging
        self.name = name

    def __enter__(self):
        return self.open()

    def __exit__(self, *exc):
        self.close()

    @property
    def complete_path(self):
        pass

    @abstractmethod
    def open(self):
        return self

    @abstractmethod
    def close(self):
        pass

    @abstractmethod
    def list(self):
        pass

    def assert_opened(self):
        if self.closed:
            raise BackupPackagerNotOpenedError(self)

    def assert_closed(self):
        if not self.closed:
            raise BackupPackagerOpenedError(self)

    def log(self, level, message, *args, **kwargs):
        if self.name:
            message = "{}: {}".format(self.name, message)
        logger.log(level, message, *args, **kwargs)


class _AbstractReadBackupPackager(_AbstractBackupPackager, ABC):
    @abstractmethod
    def restore(self, name, target):
        pass


class _AbstractWriteBackupPackager:
    @abstractmethod
    def add(self, src, name=None):
        pass

    @abstractmethod
    def remove_package(self):
        pass


class _AbstractShareableWriteBackupPackager(_AbstractBackupPackager, ABC):
    is_shareable = True

    @abstractmethod
    def remove(self, name):
        pass


from .directory import ReadBackupPackagerDir, WriteBackupPackagerDir
from .tar import ReadBackupPackagerTar, WriteBackupPackagerTar

try:
    from .zstd import ReadBackupPackagerZSTD, WriteBackupPackagerZSTD
except ImportError as e:
    from .unsupported import (
        UnsupportedReadBackupPackagerZSTD,
        UnsupportedWriteBackupPackagerZSTD,
    )

    ReadBackupPackagerZSTD, WriteBackupPackagerZSTD = (
        UnsupportedReadBackupPackagerZSTD,
        UnsupportedWriteBackupPackagerZSTD,
    )
    error = str(e)
    ReadBackupPackagerZSTD.reason, WriteBackupPackagerZSTD.reason = (error, error)


class ReadBackupPackagers(Enum):
    directory = ReadBackupPackagerDir
    tar = ReadBackupPackagerTar
    zstd = ReadBackupPackagerZSTD


class WriteBackupPackagers(Enum):
    directory = WriteBackupPackagerDir
    tar = WriteBackupPackagerTar
    zstd = WriteBackupPackagerZSTD
