from abc import ABC, abstractmethod
import logging
import os
from virt_backup.domains import get_domain_disks_of


__all__ = [
    "DomBackup",
    "DomCompleteBackup",
    "DomExtSnapshotCallbackRegistrer",
    "build_dom_complete_backup_from_def",
    "build_dom_backup_from_pending_info",
]


logger = logging.getLogger("virt_backup")


class _BaseDomBackup(ABC):
    backup_dir = ""
    dom = None
    packager = ""
    packager_opts = None

    def _parse_dom_xml(self):
        """
        Parse the domain's definition
        """
        raise NotImplementedError

    def _main_backup_name_format(self, snapdate, *args, **kwargs):
        """
        Main backup name format

        Extracted in its own function so it can be easily override

        :param snapdate: date when external snapshots have been created
        """
        str_snapdate = snapdate.strftime("%Y%m%d-%H%M%S")
        return "{}_{}_{}".format(str_snapdate, self.dom.ID(), self.dom.name())

    def _get_read_packager(self, name):
        kwargs = self._get_packager_kwargs(name)
        return getattr(ReadBackupPackagers, self.packager).value(**kwargs)

    def _get_write_packager(self, name):
        kwargs = self._get_packager_kwargs(name)
        return getattr(WriteBackupPackagers, self.packager).value(**kwargs)

    def _get_packager_kwargs(self, name):
        """
        Get packager returns an adapted packager and update the pending info and
        definition.
        """
        kwargs = {"name": name, "path": self.backup_dir, **self.packager_opts}
        specific_kwargs = {}
        if self.packager == "tar":
            specific_kwargs["archive_name"] = name
        elif self.packager == "zstd":
            specific_kwargs["name_prefix"] = name
        kwargs.update(specific_kwargs)

        return kwargs

    def _get_self_domain_disks(self, *filter_dev):
        dom_xml = self._parse_dom_xml()
        return get_domain_disks_of(dom_xml, *filter_dev)

    def _delete_with_error_printing(self, file_to_remove):
        try:
            os.remove(self.get_complete_path_of(file_to_remove))
        except Exception as e:
            logger.error("Error removing {}: {}".format(file_to_remove, e))

    def _clean_packager(self, packager, disks):
        """
        If the package is shareable, will remove each disk backup then will
        only remove the packager if empty.
        """
        if packager.is_shareable:
            with packager:
                for d in disks:
                    packager.remove(d)
                if packager.list():
                    # Other non related backups still exists, do not delete
                    # the package.
                    return

        packager.remove_package()

    def get_complete_path_of(self, filename):
        return os.path.join(self.backup_dir, filename)


from .complete import DomCompleteBackup, build_dom_complete_backup_from_def
from .packagers import ReadBackupPackagers, WriteBackupPackagers
from .pending import DomBackup, build_dom_backup_from_pending_info
from .snapshot import DomExtSnapshotCallbackRegistrer
