import logging
import os
import re
import shutil
import tarfile

from virt_backup.exceptions import ImageNotFoundError
from . import (
    _AbstractBackupPackager,
    _AbstractReadBackupPackager,
    _AbstractWriteBackupPackager,
    _opened_only,
    _closed_only,
)


class _AbstractBackupPackagerTar(_AbstractBackupPackager):
    _tarfile = None
    _mode = ""

    def __init__(
        self, name, path, archive_name, compression=None, compression_lvl=None
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

        mode = "{}:{}".format(mode_prefix, mode_suffix) if mode_suffix else mode_prefix
        return tarfile.open(self.complete_path, mode, **extra_args)

    @_opened_only
    def close(self):
        self._tarfile.close()
        self.closed = True

    @_opened_only
    def list(self):
        return self._tarfile.getnames()


class ReadBackupPackagerTar(_AbstractReadBackupPackager, _AbstractBackupPackagerTar):
    _mode = "r"

    def __init__(
        self, name, path, archive_name, compression=None, compression_lvl=None
    ):
        # Do not set compression_lvl on readonly, as it can trigger some errors (with
        # XZ for example)
        super().__init__(name, path, archive_name, compression)

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
            shutil.copyfileobj(self._tarfile.extractfile(disk_tarinfo), ftarget)

            return target


class WriteBackupPackagerTar(_AbstractWriteBackupPackager, _AbstractBackupPackagerTar):
    _mode = "x"

    @_opened_only
    def add(self, src, name=None):
        self.log(logging.DEBUG, "Add %s into %s", src, self.complete_path)
        self._tarfile.add(src, arcname=name or os.path.basename(src))
        return self.complete_path

    @_closed_only
    def remove_package(self):
        if not os.path.exists(self.complete_path):
            raise FileNotFoundError(self.complete_path)

        return os.remove(self.complete_path)
