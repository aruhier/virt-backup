.. _backup:

======
Backup
======

This page describes how the backup process works.

.. contents:: Table of Contents
   :depth: 3

Principle
---------

- A complete backup is defined by its definition. A definition is a json file, stored next to the backup, containing
  informations such as the domain name, the disk backups, path to the backup, etc. This is the file listed when doing
  ``virt-backup list -D domain``.
- A pending backup is defined by its ``pending_info``. The ``pending_info`` is a definition with some additional
  attributes computed when running the backup. It is stored next to the backup, and removed when the backup is
  complete. It is used to rebuild a temp backup if a crash happened, and clean everything.


How it works
------------

When backuping multiple groups, first virt-backup will build all the groups with the given rules, then merge it into
one. It allows to have a unique entry point to start everything, and deduplicate the similar backups. Read the
:ref:`groups unicity section <backup_groups_unicity>` for more details.

If multithreading is disabled, it then starts the backups one by one. However, if multithreading is enabled, a safety
mechanism is followed if multiple backups target the same domain. Read the :ref:`groups multithreading section
<backup_groups_multithreading>` for more details.

Then, each backups are started. For each backup, the first step is to create the backup directory, and take an external
snapshot of all targeted disks (read the :ref:`domain external snapshot section <backup_dom_ext_snap>` for more
details). This method is used in order to freeze the disks by the time virt-backup backup them, and then merge them
back with the main disks and pivot the domains like before. There is however multiple inconvenient for that: if the
VM is doing a lot of "remove" (freeing blocks), it's more operations as the external snapshot needs to log it. And it
obviously requires temporarily more space.

Then the pending info are dumped on disk, where the backup should be. This step allows to be able to clean
the backup if virt-backup would happen to crash (by using ``virt-backup clean``). It contains the snapshot names and
different informations that are known only when starting the backups.

Now that the disks are frozen, they can be safely copied somewhere. This somewhere is defined by the packager (see the
``virt_backup.backups.packagers`` package). A packager is a way to store a backup, and expose a standard API so the
backup does not have to care about it. Each disks are copied sequentially into the packager.

The definition is dumped again, with all the final info. The pending info are removed, the external snapshots are
cleaned (meaning for each snapshot, a blockcommit is triggered, the external snapshot is removed, the disk is pivot).

If anything goes wrong during the backup, the external snapshot is cleaned, the pending info are removed such as
everything created for the backup (only the backup directory is left).


Groups
------

.. _backup_groups_unicity:

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

.. _backup_groups_multithreading:

Multithreading
~~~~~~~~~~~~~~

Backuping a group can be done in single thread or multithread. As a group can contain the same domain with different
options, some safety have been done to avoid backuping the same domain in parallel. It is needed as the process relies
on external snapshot, doing so would take an external snapshot of a snapshot (with the current implementation).

As it is considered to be a rare case, all backups targeting the same domain are scheduled in a queue. If other domains
are to backup, the backups in these queues are normally handled in parallel of other backups.

.. _backup_dom_ext_snap:

Domain external snapshot
------------------------

A custom helper is implemented to handle the external snapshots (see the ``virt_backup.backups.snapshot`` package). It
uses libvirt to create it, then allows to remove it and pivot back to the main disk by using blockcommit (read `this
libvirt example <https://wiki.libvirt.org/page/Live-disk-backup-with-active-blockcommit>`_ for more details).

Quiesce is an option when creating the snapshot. It allows to communicate with the virt agent present on the domain to
force a sync of the disk before taking the snapshot.
If Quiesce is wanted, when doing the snapshot, it first tries to do it with this option. If it fails, because for
example there is no virt-agent running on this domain, it fallbacks on a snapshot without Quiesce (but logs an error).

Pivoting back to the main disk depends if the domain is up or not. Libvirt does not allow a blockcommit on a shutdown
domain. In this case, ``qemu-img`` is used directly to manually handle the blockcommit. Otherwise, libvirt API is used.

To blockcommit, libvirt uses an event mechanism. Libvirt takes a function that it will call if there is an issue with
the blockcommit, or if it's done. To centralize it, a custom helper ``DomExtSnapshotCallbackRegistrer`` is used (see
the ``virt_backup.backups.snapshot`` package). It stores the callback to call per snapshot path, so when libvirt calls
the register as a callback, it then look for the known snapshots and call the function to trigger a pivot. This
function is handled by the ``DomExtSnapshot``, which aborts the blockjob and removes the snapshot.


.. _backup_packagers:

Packagers
---------

Packagers in virt-backup are a common way to deal with storage. They are defined in the
``virt_backup.backup.packagers`` package. A packager can provide an abstracted way to deal with a folder, archive or
else.

Each packager is split in 2:

- Read packager, inherited from ``virt_backup.backup.packagers._AbstractReadBackupPackager``. Provides mechanisms to
  list backups from a packager and restore a specific backup (by copying it to a given path).
- Write packager, inherited from ``virt_backup.backup.packagers._AbstractWriteBackupPackager``. Provide mechanisms to
  add a new backup in a packager, delete the package and, when possible, remove a specific image from a backup. When
  the package is shareable between backups (for example, with a folder storing all the images of a domain), it also
  provide a way to remove a specific backup from the package.

Splitting in read/write allows more safety when dealing with backups: the write packager is used only when the backup
mechanism absolutely needs it, otherwise the read packager is used.

Available packagers are:

- ``directory``: store the images directly in a directory. Can be a directory per backup, or a directory shared for
  multiple backups.
- ``tar``: store the backups in a tar archive. Can handle compression.
- ``zstd``: store the backups in a zstd archive. Compression level is customizable. Can also handle multithreading for
  the compression itself.
