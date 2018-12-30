class BackupNotFoundError(Exception):
    def __init__(self):
        super().__init__("backup not found")


class BackupsFailureInGroupError(Exception):
    def __init__(self, completed_backups, exceptions):
        """
        :param completed_backups: dictionary of completed backups.
                                  {dom_name: completed_backup}
        :param exceptions: dictionary of exceptions. {dom_name: exception}
        """
        super().__init__(
            "backups failed for domains: {}".format(
                ", ".join(sorted(exceptions.keys()))
            )
        )
        self.completed_backups = completed_backups
        self.exceptions = exceptions


class DiskNotFoundError(Exception):
    """
    Disk not found in a domain
    """
    def __init__(self, disk):
        super().__init__("disk {} not found".format(disk))


class DomainNotFoundError(Exception):
    def __init__(self, domain):
        super().__init__("domain {} not found".format(domain))


class DomainRunningError(Exception):
    """
    Domain is running when a task would need it to be shutdown
    """
    def __init__(self, domain):
        message = (
            "DomainRunningError: domain {} need to be shutdown to perform the "
            "task"
        ).format(domain)
        super().__init__(message)


class SnapshotNotStarted(Exception):
    def __init__(self):
        super().__init__("snapshot not started")


class DiskNotSnapshot(Exception):
    def __init__(self, disk):
        super().__init__("disk {} not snapshot".format(disk))
