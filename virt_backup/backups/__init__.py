import logging
import os
from virt_backup.domains import get_domain_disks_of


__all__ = [
    "DomBackup", "DomCompleteBackup", "DomExtSnapshotCallbackRegistrer",
    "build_dom_complete_backup_from_def", "build_dom_backup_from_pending_info"
]


logger = logging.getLogger("virt_backup")


class _BaseDomBackup():
    def _parse_dom_xml(self):
        """
        Parse the domain's definition
        """
        raise NotImplementedError

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
        # TODO: could be shared, but target_dir and backup_dir have to be
        # renamed
        raise NotImplementedError


from .complete import DomCompleteBackup, build_dom_complete_backup_from_def
from .packagers import ReadBackupPackagers, WriteBackupPackagers
from .pending import DomBackup, build_dom_backup_from_pending_info
from .snapshot import DomExtSnapshotCallbackRegistrer
