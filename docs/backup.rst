.. _backup:

======
Backup
======

This page describes how the backup process works.

.. contents:: Table of Contents
   :depth: 3

Groups
------


Unicity
~~~~~~~

If multiple groups are backup and some share the same domains to backup, virt-backup will try to see if the backups
could be compatible to avoid doing the exact same backup multiple times.

Example of a groups configuration::

  groups:
    group1:
      target: /mnt/kvm/backups

      packager: zstd
      packager_opts:
        compression_lvl: 6

      ## Hosts definition ##
      hosts:
        - "test1"

    group2:
      target: /mnt/kvm/backups

      packager: zstd
      packager_opts:
        compression_lvl: 6

      ## Hosts definition ##
      hosts:
        - "r:test.*"

    group3:
      target: /mnt/kvm/backups_disk1_only

      packager: tar

      ## Hosts definition ##
      hosts:
        - name: "test1"
          disks:
            - disk1

Here `group1` and `group2` will try to backup the domain `test1` with all its disks, with the same compression
parameters and to the same target directory.  Therefore, `test1` can only be backup once.

However, `group3` specifies that only the disk `disk1` of `test1` has to be backup, and put it in a tarfile in a
different target directory. It is not considered as compatible with what `group1` and `group2` specify, therefore it
will be backup a second time.

Running a backup with this configuration will do 2 backups for `test1`: one shared between `group1` and `group2`, one
for `group3`.
