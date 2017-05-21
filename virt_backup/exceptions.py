#!/usr/bin/env python3


class BackupNotFoundError(Exception):
    def __str__(self):
        return "BackupNotFoundError: backup not found"


class DiskNotFoundError(Exception):
    """
    Disk not found in a domain
    """
    def __init__(self, disk):
        self.disk = disk

    def __str__(self):
        return "DiskNotFoundError: disk {} not found".format(self.disk)


class DomainNotFoundError(Exception):
    def __init__(self, domain):
        self.domain = domain

    def __str__(self):
        return "DomainNotFoundError: domain {} not found".format(self.domain)


class DomainRunningError(Exception):
    """
    Domain is running when a task would need it to be shutdown
    """
    def __init__(self, domain):
        self.domain = domain

    def __str__(self):
        return (
            "DomainRunningError: domain {} need to be shutdown to perform the "
            "task"
        ).format(self.domain)
