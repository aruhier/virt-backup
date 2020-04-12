import logging
import os
import shutil

from virt_backup.exceptions import CancelledError, ImageNotFoundError
from . import (
    _AbstractBackupPackager,
    _AbstractReadBackupPackager,
    _AbstractShareableWriteBackupPackager,
    _opened_only,
    _closed_only,
)


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

    def _copy_file(self, src, dst, stop_event=None, buffersize=2 ** 20):
        if not os.path.exists(dst) and dst.endswith("/"):
            os.makedirs(dst)
        if os.path.isdir(dst):
            dst = os.path.join(dst, os.path.basename(src))

        if stop_event and stop_event.is_set():
            raise CancelledError()
        with open(src, "rb") as fsrc, open(dst, "xb") as fdst:
            while True:
                if stop_event and stop_event.is_set():
                    raise CancelledError()
                data = fsrc.read(buffersize)
                if not data:
                    break

                if stop_event and stop_event.is_set():
                    raise CancelledError()
                fdst.write(data)
        return dst


class ReadBackupPackagerDir(_AbstractReadBackupPackager, _AbstractBackupPackagerDir):
    @_opened_only
    def restore(self, name, target, stop_event=None):
        src = os.path.join(self.path, name)
        if not os.path.exists(src):
            raise ImageNotFoundError(name, self.path)

        self.log(logging.DEBUG, "Restore %s in %s", src, target)
        return self._copy_file(src, target, stop_event=stop_event)


class WriteBackupPackagerDir(
    _AbstractShareableWriteBackupPackager, _AbstractBackupPackagerDir
):
    @_opened_only
    def add(self, src, name=None, stop_event=None):
        if not name:
            name = os.path.basename(src)
        target = os.path.join(self.path, name)
        self.log(logging.DEBUG, "Copy %s as %s", src, target)
        self._copy_file(src, target, stop_event=stop_event)

        return target

    @_opened_only
    def remove(self, name):
        target = os.path.join(self.path, name)
        self.log(logging.DEBUG, "Remove file %s", target)
        os.remove(target)

    @_closed_only
    def remove_package(self, stop_event=None):
        if not os.path.exists(self.complete_path):
            raise FileNotFoundError(self.complete_path)

        return shutil.rmtree(self.complete_path)
