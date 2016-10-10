#!/usr/bin/env python3


class DiskNotFound(Exception):
    """
    Disk not found in a domain
    """
    def __init__(self, disk):
        self.disk = disk

    def __str__(self):
        return "DiskNotFound: disk {} not found".format(self.disk)
