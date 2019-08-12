from abc import ABC, abstractmethod
from enum import Enum
import logging
import os
import re
import shutil
import tarfile

from virt_backup.exceptions import (
    ImageNotFoundError, BackupPackagerNotOpenedError
)


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


class _AbstractBackupPackagerDir(_AbstractBackupPackager):
    """
    Images are just copied in a directory
    """

    def __init__(self, name, path):
        super().__init__(name)
        self.path = path

    @property
    def complete_path(self):
        return self.path

    def open(self):
        if not os.path.isdir(self.path):
            os.makedirs(self.path)

        self.closed = False
        return self

    @_opened_only
    def close(self):
        self.closed = True

    @_opened_only
    def list(self):
        return os.listdir(self.path)

    def _copy_file(self, src, dst, buffersize=None):
        if not os.path.exists(dst) and dst.endswith("/"):
            os.makedirs(dst)
        if os.path.isdir(dst):
            dst = os.path.join(dst, os.path.basename(src))

        with open(src, "rb") as fsrc, open(dst, "xb") as fdst:
            shutil.copyfileobj(fsrc, fdst, buffersize)
        return dst


class ReadBackupPackagerDir(
        _AbstractReadBackupPackager, _AbstractBackupPackagerDir
):

    @_opened_only
    def restore(self, name, target):
        src = os.path.join(self.path, name)
        if not os.path.exists(src):
            raise ImageNotFoundError(name, self.path)

        self.log(logging.DEBUG, "Restore %s in %s", src, target)
        return self._copy_file(src, target)


class WriteBackupPackagerDir(
        _AbstractWriteBackupPackager, _AbstractBackupPackagerDir
):

    @_opened_only
    def add(self, src, name=None):
        if not name:
            name = os.path.basename(src)
        target = os.path.join(self.path, name)
        self.log(logging.DEBUG, "Copy %s as %s", src, target)
        self._copy_file(src, target)

        return target


class _AbstractBackupPackagerTar(_AbstractBackupPackager):
    _tarfile = None
    _mode = ""

    def __init__(
            self, name, path, archive_name, compression=None,
            compression_lvl=None
    ):
        super().__init__(name)

        #: directory path to store the tarfile in
        self.path = path

        #: tarfile archive name (does not have to contain an extension, what
        #: will be computed automatically)
        self.archive_name = archive_name

        self.compression = compression
        self.compression_lvl = compression_lvl

    @property
    def complete_path(self):
        if self.compression not in (None, "tar"):
            extension = "tar.{}".format(self.compression)
        else:
            extension = "tar"

        if re.match(r".*\.tar\.?.*$", self.archive_name):
            complete_path = os.path.join(self.path, self.archive_name)
        else:
            complete_path = os.path.join(
                self.path, "{}.{}".format(self.archive_name, extension)
            )

        return complete_path

    def open(self):
        self._tarfile = self._open_tar(self._mode)
        self.closed = False
        return self

    def _open_tar(self, mode_prefix):
        extra_args = {}
        if self.compression not in (None, "tar"):
            mode_suffix = "{}".format(self.compression)
            if self.compression_lvl:
                if self.compression == "xz":
                    extra_args["preset"] = self.compression_lvl
                else:
                    extra_args["compresslevel"] = self.compression_lvl
        else:
            mode_suffix = ""

        if not os.path.isdir(self.path):
            os.makedirs(self.path)

        mode = (
            "{}:{}".format(mode_prefix, mode_suffix) if mode_suffix
            else mode_prefix
        )
        return tarfile.open(
            self.complete_path, mode, **extra_args
        )

    @_opened_only
    def close(self):
        self._tarfile.close()
        self.closed = True

    @_opened_only
    def list(self):
        return self._tarfile.getnames()


class ReadBackupPackagerTar(
        _AbstractReadBackupPackager, _AbstractBackupPackagerTar
):
    _mode = "r"

    @_opened_only
    def restore(self, name, target):
        try:
            disk_tarinfo = self._tarfile.getmember(name)
        except KeyError:
            raise ImageNotFoundError(name, self.complete_path)

        if not os.path.exists(target) and target.endswith("/"):
            os.makedirs(target)
        if os.path.isdir(target):
            target = os.path.join(target, name)

        self._tarfile.fileobj.flush()
        with open(target, "xb") as ftarget:
            shutil.copyfileobj(
                self._tarfile.extractfile(disk_tarinfo), ftarget
            )

            return target


class WriteBackupPackagerTar(
        _AbstractWriteBackupPackager, _AbstractBackupPackagerTar
):
    _mode = "x"

    @_opened_only
    def add(self, src, name=None):
        self.log(logging.DEBUG, "Add %s into %s", src, self.complete_path)
        self._tarfile.add(src, arcname=name or os.path.basename(src))
        return self.complete_path


class ReadBackupPackagers(Enum):
    directory = ReadBackupPackagerDir
    tar = ReadBackupPackagerTar


class WriteBackupPackagers(Enum):
    directory = WriteBackupPackagerDir
    tar = WriteBackupPackagerTar
