#!/usr/bin/env python3


class DiskNotFoundError(Exception):
    """
    Disk not found in a domain
    """
    def __init__(self, disk):
        self.disk = disk

    def __str__(self):
        return "DiskNotFoundError: disk {} not found".format(self.disk)


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
