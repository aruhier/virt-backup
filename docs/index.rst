Welcome to virt-backup's documentation!
=======================================

virt-backup does hot external backups of your `Libvirt <https://libvirt.org/>`_ guests, using the
BlockCommit feature. The goal is to do an automatic backup system, with
optional compression, and be able to easily restore a backup.

virt-backup is based around groups: a group contains a list of domains to backup, that can be matched by regex.
Each group contains its own configuration, specifying how to store the backups (compression, directory, etc.),
where to store them, the retention by period of time when a cleanup is called, etc.


Features
--------

* Hot backup one or multiple qemu/raw disk, snapshoting everything at the same time.
* Cold backup a qemu/raw disk.
* Multithreading: can backup multiple domains in parallel.
* Supports multiple targets for backups:

    * Directory: just copies images in a directory.
    * Tar: stores all images of a backup in a tar file (with optional xz/gz/bzip2 compression).
    * ZSTD: compresses the images using ZSTD algorithm (supports multithreading).

* Restore a backup to a folder.
* List all backups, by VM name.
* Clean backup, with configurable time retention (number of backups to keep,
  per domain, per hours/day/weeks/months/years)


Limitations
-----------

* Only supports file type disks (qemu, raw, etc.). Does not support LVM or any block disk.
* Does not handle Libvirt external snapshots. BackingStores are just ignored
  and only the current running disk is backup.
* virt-backup has to run on each hypervisor. It has to be able to read the
  disks in order to backup them, and it uses the same disk path  as configured
  in Libvirt.


.. toctree::
   :maxdepth: 2
   :caption: Contents:

   quickstart
   config
   backup
   data_map
   clean

Indices and tables
==================
* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`
