import glob
import logging
import os
import re
import shutil
import zstandard as zstd

from virt_backup.exceptions import ImageNotFoundError
from . import (
    _AbstractBackupPackager,
    _AbstractReadBackupPackager,
    _AbstractWriteBackupPackager,
    _opened_only,
    _closed_only,
)


class _AbstractBackupPackagerZSTD(_AbstractBackupPackager):
    _mode = ""

    def __init__(self, name, path, name_prefix, compression_lvl=None):
        super().__init__(name)

        #: Directory path to store the archives in.
        self.path = path

        #: Each file from this package will be stored as one separated archive.
        #: Their name will be prefixed by prefix_name
        self.name_prefix = name_prefix

        self.compression_lvl = compression_lvl

    @property
    def complete_path(self):
        return self.path

    def archive_path(self, name):
        """
        WARNING: it does not check that the archive actually exists,
        just returns the path it should have
        """
        return os.path.join(self.path, self._gen_archive_name(name))

    def _gen_archive_name(self, filename):
        return "{}_{}.zstd".format(self.name_prefix, filename)

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
        results = []
        pattern = re.compile(r"{}_(.*)\.zstd$".format(self.name_prefix))
        for i in glob.glob(os.path.join(self.complete_path, "*.zstd")):
            m = pattern.match(os.path.basename(i))
            if m:
                results.append(m.group(1))

        return results


class ReadBackupPackagerZSTD(_AbstractReadBackupPackager, _AbstractBackupPackagerZSTD):
    _mode = "r"

    @_opened_only
    def restore(self, name, target):
        if name not in self.list():
            raise ImageNotFoundError(self.archive_path(name), self.complete_path)

        if not os.path.exists(target) and target.endswith("/"):
            os.makedirs(target)
        if os.path.isdir(target):
            target = os.path.join(target, name)

        dctx = zstd.ZstdDecompressor()
        with open(self.archive_path(name), "rb") as ifh:
            with open(target, "wb") as ofh:
                dctx.copy_stream(ifh, ofh)

        return target


class WriteBackupPackagerZSTD(
    _AbstractWriteBackupPackager, _AbstractBackupPackagerZSTD
):
    _mode = "x"

    @_opened_only
    def add(self, src, name=None):
        name = name or os.path.basename(src)
        self.log(logging.DEBUG, "Add %s into %s", src, self.archive_path(name))
        cctx = zstd.ZstdCompressor()
        with open(src, "rb") as ifh:
            with open(self.archive_path(name), "wb") as ofh:
                cctx.copy_stream(ifh, ofh)

        return self.archive_path(name)

    @_opened_only
    def remove(self, name):
        if name not in self.list():
            raise ImageNotFoundError(self.archive_path(name), self.complete_path)

        os.remove(self.archive_path(name))

    @_closed_only
    def remove_package(self):
        if not os.path.exists(self.complete_path):
            raise FileNotFoundError(self.complete_path)

        return shutil.rmtree(self.complete_path)
