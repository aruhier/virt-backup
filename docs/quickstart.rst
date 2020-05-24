.. _quickstart:

==========
Quickstart
==========

.. currentmodule:: virt_backup

virt-backup has 4 main functions:
  - :ref:`backup <quickstart_backup>`
  - :ref:`list backups <quickstart_list>`
  - :ref:`restore <quickstart_restore>`
  - :ref:`clean backups <quickstart_clean>`

This page describes how to install virt-backup, create a generic configuration then how to use these 4 functions.

.. contents:: Table of Contents
   :depth: 3


Installation
------------

Run::

  pip3 install virt-backup

Or by using setuptools::

  python3 ./setup.py install

virt-backup is Python 3 compatible only.


Configuration
-------------

.. _quickstart_configuration:


virt-backup is based around the definition of groups. Groups can include or exclude as many domains as needed,
and define the backup properties: compression, disks to backup, where to store the backups, retention, etc..

Groups definition is the biggest part of the configuration.

The configuration is a yaml file. Here is a quite generic one::

  ---

  ########################
  #### Global options ####
  ########################

  ## Be more verbose ##
  debug: False

  ## How many threads (simultaneous backups) to run. Use 0 to use all CPU threads
  ## detected, 1 to disable multitheading for backups, or the number of threads
  ## wanted. Default: 1
  threads: 1


  ############################
  #### Libvirt connection ####
  ############################

  ## Libvirt URI ##
  uri: "qemu:///system"

  ## Libvirt authentication, if needed ##
  username:
  passphrase:


  #######################
  #### Backup groups ####
  #######################

  ## Groups are here to share the same backup options between multiple domains.
  ## That way, it is possible, for example, to have a different policy retention
  ## for a pool of guests in testing than for the one in production.

  ## Define default options for all groups. ##
  ## Here we set the retention parameters for each VM when calling `virt-backup clean`.
  default:
    hourly: 1
    daily: 4
    weekly: 2
    monthly: 5
    yearly: 1

  ## Groups definition ##
  groups:
    ## Group name ##
    test:
      ## Backup directory ##
      target: /mnt/kvm/backups

      ## Use ZSTD compression, configured at lvl 6
      packager: zstd
      packager_opts:
        compression_lvl: 6

      ## When doing `virt-backup backup` without specifying any group, only
      ## groups with the autostart option enabled will be backup.
      autostart: True

      ## Enable the Libvirt Quiesce option when taking the external snapshots.
      ##
      ## From Libvirt documentation: libvirt will try to freeze and unfreeze the guest
      ## virtual machine’s mounted file system(s), using the guest agent. However, if the
      ## guest virtual machine does not have a guest agent, snapshot creation will fail.
      ##
      ## However, virt-backup has a fallback mechanism if the snapshot happens to fail
      ## with Quiesce enabled, and retries without it.
      quiesce: True

      ## Hosts definition ##
      hosts:
        ## Will backup everything.
        - "r:.*"

  # vim: set ts=2 sw=2:


Adapt it and save it either as:

  - ``~/.config/virt-backup/config.yml``
  - ``/etc/virt-backup/config.yml``


Backup
------

.. _quickstart_backup:

All groups set with the `autostart` option to `True` can be started by running::

    $ virt-backup backup

A specific group (``test``) can be started by running::

    $ virt-backup backup test

The group has to be defined in the configuration.

Multiple groups can be ran with::

    $ virt-backup backup group1 group2 […]


List
----

.. _quickstart_list:

To list the backups for all groups, as a summary::

    $ virt-backup list

     generic
    =========

    Total backups: 2 hosts, 22 backups
    Hosts:
        vm-foo-0: 11 backup(s)
        vm-bar-0: 11 backup(s)

     test
    ======

    Total backups: 1 hosts, 11 backups
    Hosts:
        vm-foo-1: 11 backup(s)

To have a really short summary for all groups::

    $ virt-backup list -s

     generic
    =========

    Total backups: 9 hosts, 99 backups

     test
    ======

    Total backups: 1 hosts, 11 backups

By default, only domains with at least one backup will be listed, but all domains matching with the group rules can be
printed by using the ``-a/--all`` option.

To list exactly all the backups done for one domain, here ``vm-foo-0``::

    $ virt-backup list -D vm-foo-0

     generic
    =========

    vm-foo-0: 11 backup(s)
    	2020-09-17T01:02:53+00:00: /backups/vm-foo-0/20200917-010253_8_vm-foo-0.json
    	2020-09-16T01:02:56+00:00: /backups/vm-foo-0/20200916-010256_8_vm-foo-0.json
    	2020-09-15T01:02:39+00:00: /backups/vm-foo-0/20200915-010239_8_vm-foo-0.json
    	2020-09-14T01:02:34+00:00: /backups/vm-foo-0/20200914-010234_8_vm-foo-0.json
    	2020-09-07T01:03:07+00:00: /backups/vm-foo-0/20200907-010307_8_vm-foo-0.json
    	2020-09-01T01:02:22+00:00: /backups/vm-foo-0/20200901-010222_8_vm-foo-0.json
    	2020-08-01T01:02:20+00:00: /backups/vm-foo-0/20200801-010220_8_vm-foo-0.json
    	2020-07-01T00:55:01+00:00: /backups/vm-foo-0/20200701-005501_3_vm-foo-0.json
    	2020-06-01T00:55:02+00:00: /backups/vm-foo-0/20200601-005502_3_vm-foo-0.json
    	2020-05-01T00:55:01+00:00: /backups/vm-foo-0/20200501-005501_3_vm-foo-0.json
    	2020-04-01T00:55:01+00:00: /backups/vm-foo-0/20200401-005501_3_vm-foo-0.json

Which lists when the backup was taken, and where its definition file is stored. If the domain matches multiple groups,
backups will be listed per group.



Restore
-------

.. _quickstart_restore:

To restore the last backup of a domain (``vm-foo-0``) part of a given group (``generic``), and extract the result in the given target destination (``~/disks``)::

    $ virt-backup restore generic vm-foo-0 ~/disks

Which extracts everything backuped to ``~/disks``.

To extract a specific backup, its date can be specified (``2020-09-17T01:02:53+00:00``)::

    $ virt-backup restore --date 2020-09-17T01:02:53+00:00 generic vm-foo-0 ~/disks

The format is for the moment non convenient and some work will be needed to facilitate it. For the moment, the exact
date and format as given by ``virt-backup list`` has to be used.


Clean
-----

.. _quickstart_clean:

It is possible to automatically clean old backups, by following the configured :ref:`rentention policy
<configuration_retention>`, but also broken backups (for which the backup process was not correctly interrupted, by a
crash or server shutdown for example).

To clean old and broken backups for all groups::

    $ virt-backup clean

To limit the cleaning to one group only (``test``)::

    $ virt-backup clean test


To only clean the broken backups, but not handle the old (correct) backups::

    $ virt-backup clean -b

Opposite situation, to not clean the broken backups but only handle the old (correct) backups::

    $ virt-backup clean -B

A systemd service is available in `example/virt-backup-clean.service
<https://raw.githubusercontent.com/aruhier/virt-backup/master/example/virt-backup-clean.service>`_  to trigger a
cleaning of all broken backups at start. This way, if the hypervisor crashed during a backup, the service will clean
all temporary files and pivot all disks to their original images (instead of running on a temporary external snapshot).
