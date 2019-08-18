from abc import ABC, abstractmethod
from enum import Enum
import logging

from virt_backup.exceptions import BackupPackagerNotOpenedError


logger = logging.getLogger("virt_backup")


def _opened_only(f):
    def wrapper(self, *args, **kwargs):
        self.assert_opened()
        return f(self, *args, **kwargs)

    return wrapper


class _AbstractBackupPackager(ABC):
    closed = True

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

    def log(self, level, message, *args, **kwargs):
        if self.name:
            message = "{}: {}".format(self.name, message)
        logger.log(level, message, *args, **kwargs)


class _AbstractReadBackupPackager(_AbstractBackupPackager, ABC):

    @abstractmethod
    def restore(self, name, target):
        pass


class _AbstractWriteBackupPackager(_AbstractBackupPackager, ABC):

    @abstractmethod
    def add(self, src, name=None):
        pass


from .directory import ReadBackupPackagerDir, WriteBackupPackagerDir
from .tar import ReadBackupPackagerTar, WriteBackupPackagerTar


class ReadBackupPackagers(Enum):
    directory = ReadBackupPackagerDir
    tar = ReadBackupPackagerTar


class WriteBackupPackagers(Enum):
    directory = WriteBackupPackagerDir
    tar = WriteBackupPackagerTar
