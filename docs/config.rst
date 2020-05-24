.. _config:

=============
Configuration
=============

This page describes how to configure virt-backup and goes in detail for each section.

.. contents:: Table of Contents
   :depth: 3

.. _configuration_full_example:

Full example
------------

The configuration is a yaml file virtually split into 3 main sections: the global
options, libvirt connection and backup groups. Here is a full example::

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

      ## Packager to use for each backup:
      ##   directory: images will be copied as they are, in a directory per domain
      ##   tar: images will be packaged in a tar file
      ##   zstd: images will be compressed with zstd. Requires python "zstandard" package to be installed.
      packager: tar

      ## Options for the choosen packager:
      ## tar:
      ##   # Compression algorithm to use. Default to None.
      ##   compression: None | "xz" | "gz" | "bz2"
      ##   # Compression level to use for each backup.
      ##   # Generally this should be an integer between 1~9 (depends on the
      ##   # compression algorithm), where 1 will be the fastest while having
      ##   # the lowest compression ratio, and 9 gives the best compression ratio
      ##   # but takes the longest time to compress.
      ##   compression_lvl: [1-9]
      ##
      ## zstd:
      ##   # Compression level to use for each backup.
      ##   # 1 will be the fastest while having the lowest compression ratio,
      ##   # and 22 gives the best compression ratio but takes the longest time
      ##   # to compress.
      ##   compression_lvl: [1-22]
      packager_opts:
        compression: xz
        compression_lvl: 6

      ## When doing `virt-backup backup` without specifying any group, only
      ## groups with the autostart option enabled will be backup.
      autostart: True

      ## Retention policy: the first backup of the day is considered as the
      ## "daily" backup, first of the week "weekly", etc. The following options
      ## detail how many backups of each type has to be kept. Set to "*" or None for an
      ## infinite retention.
      ## Default to 5 for everything, meaning that calling "virt-backup clean" will let 5
      ## backups for each period not specified in the config.
      hourly: 5
      daily: 5
      weekly: 5
      monthly: 5
      yearly: 1

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
        ## This policy will match the domain "domainname" in libvirt, and will
        ## backup the disks "vba" and "vdb" only.
        - host: domainname
          disks:
            - vda
            - vdb
          ## Quiesce option can also be overriden per host definition.
          quiesce: False
        ## Will backup all disks of "domainname2" ##
        - domainname2
        ## Regex that will match for all domains starting with "prod". The regex
        ## syntax is the same as the python one
        - "r:^prod.*"
        ## Exclude the domain domainname3 (useful with regex, for example)
        - "!domainname3"
        ## Exclude all domains starting with "test"
        - "!r:^test.*"

  # vim: set ts=2 sw=2:


It can be saved as (the order defines the priority of the import):

  - ``~/.config/virt-backup/config.yml``
  - ``/etc/virt-backup/config.yml``


Global options
--------------

They define the global behavior of virt-backup:

  - ``debug``: if ``True``, virt-backup is more verbose. Enable this option (or use the
    global `-d` command line option) for bug reports. (Optional, default: ``False``)
  - ``threads``: how many simultaneous backups to run. Set it to the number of threads
    wanted, or 1 to disable multithreading, or 0 to use all CPU threads detected.
    (Optional, default: ``1``)


Libvirt connection
------------------

They define the options to connect to libvirt:

  - ``uri``: libvirt URI: https://libvirt.org/uri.html
  - ``username``: connection username. (Optional)
  - ``password``: connection password. (Optional)

virt-backup can technically connect to a distant Libvirt, but in order to actually
backup the domain disks, it has to have access to the files. Therefore, it should run on
the same hypervisor than Libvirt.


Backup groups
-------------

Groups domains allow to share the same backup options between multiple domains.
This way, it is possible to define for example a different retention set or compression
for a pool of domains in production than one in testing.

  - ``default``: dictionary containing all the default options for the groups. If a
    group redefines an option, it overrides it.
  - ``groups``: dictionary defining the groups. Groups are defined per names, and are
    themselves dictionary defining their options.

Group options
~~~~~~~~~~~~~

  - ``target``: backup directory.
  - ``packager``: which packager to use. Read the :ref:`Packagers section <configuration_packagers>` for more info.
  - ``packager_opts``
  - ``autostart``: if ``True``, this group will be automatically backup when doing
    ``virt-backup backup`` without the need of specifying it. Otherwise, if set to
    ``False``, it needs to be specifically called (``virt-backup backup foo bar``).
  - ``hourly``, ``daily``, ``weekly``, ``monthly``, ``yearly``: retention policy. Read
    the :ref:`Retention section <configuration_retention>` for more info.
  - ``quiesce``: Enable the Libvirt Quiesce option when taking the external snapshots.

    From Libvirt documentation: libvirt will try to freeze and unfreeze the guest virtual
    machine’s mounted file system(s), using the guest agent. However, if the guest virtual
    machine does not have a guest agent, snapshot creation will fail.

    However, virt-backup has a fallback mechanism if the snapshot happens to fail with
    Quiesce enabled, and retries without it.
  - ``hosts``: domains to include in this group. Read the :ref:`Hosts section <configuration_hosts>` for more info.


.. _configuration_packagers:

Packagers
^^^^^^^^^

Packagers define the storage mechanism. The existing packagers are:

  - ``directory``: images will be copied as they are, in a directory per domain
  - ``tar``: images will be packed into a tar file
  - ``zstd``: images will be compressed with zstd. Requires python ``zstandard`` library
    to be installed.

Then, depending on the packager, some options can be set.

Tar options:
  - ``compression``: set the compression algorithm for the tar archive. (Valid options:
    ``None`` | ``xz`` | ``gz`` | ``bz2``, default: ``None``)
  - ``compression_lvl``: set the compression level for the given algorithm. Generally
    this should be an integer between 1 and 9 (depends on the compression algorithm), where
    1 will be the fastest while having the lowest compression ratio, and 9 gives the
    best compression ratio but takes the longest time to compress.

    For more info, read https://docs.python.org/3/library/tarfile.html.

ZSTD options:
  - ``compression_lvl``: set the compression level, between 1 and 22. 1 will be the fastest while having
    the lowest compression ratio, and 22 gives the best compression ratio but takes the
    longest time to compress.


.. _configuration_hosts:

Hosts
^^^^^

The ``hosts`` option contain a list of domains to match for this group. Each item of this list can also limit the
backup to specific disks, and override different options.

To only do host matching::

  hosts:
    # Will backup all disks of "domainname2"
    - domainname2
    # Regex that will match for all domains starting with "prod". The regex syntax is the same as the python one
    - "r:^prod.*"
    # Exclude the domain domainname3 (useful with regex, for example)
    - "!domainname3"
    # Exclude all domains starting with "test"
    - "!r:^test.*"

To do a more detailed definition, and limit the host to only a list of disks::

  hosts:
    - host: domainname
      disks:
        - vda
        - vdb
      ## Quiesce option can also be overriden per host definition.
      quiesce: False
    # It can still also be a regex.
    - host: "r:^prod.*"
      disks:
        - vda

As shown in the example, exclusion is possible by adding ``!``. The order of definition does not matter, and exclusion
will always take precedence over the inclusion.


.. _configuration_retention:

Retention
^^^^^^^^^

The available retention options define how many backups to keep per period when cleaning this group. The available time
periods are:

  - ``hourly``
  - ``daily``
  - ``weekly``
  - ``monthly``
  - ``yearly``

The default value is ``5`` for everything.

The first backup of the hour is called an ``hourly`` backup, first of the day is ``daily``, etc.
Setting ``daily`` to ``2`` would mean to keep the first backups of the day of the last 2 days. ``weekly`` to ``2``
would mean to keep the first backup of the week of the last 2 weeks.

`The last 2 days/weeks/etc.` is here a simplification in the explanation. Please read the :ref:`backups cleaning
documentation <clean>` to get a full explanation of the cleaning process.

