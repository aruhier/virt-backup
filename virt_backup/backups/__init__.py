
from virt_backup.domains import get_domain_disks_of


__all__ = [
    "DomBackup", "DomCompleteBackup",
    "build_dom_complete_backup_from_def"
]


class _BaseDomBackup():
    def _parse_dom_xml(self):
        """
        Parse the domain's definition
        """
        raise NotImplementedError

    def _get_self_domain_disks(self, *filter_dev):
        dom_xml = self._parse_dom_xml()
        return get_domain_disks_of(dom_xml, *filter_dev)


from .complete import DomCompleteBackup, build_dom_complete_backup_from_def
from .pending import DomBackup
