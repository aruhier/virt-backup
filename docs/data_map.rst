.. _data_map:

=========
Data maps
=========

This page lists the custom data defined and used by virt-backup, and their schema.

.. contents:: Table of Contents
   :depth: 3


Compatibility layers
--------------------

In order to ensure that virt-backup can read old backups, old configurations and pending
datas, it uses compatibility layers.

Compatibility layers are defined in ``virt_backup.compatibility_layers``, and each data
has its own package.

Compatibility layers can use a range of version if the data allows it. A configuration
doesn't define any version for example, so its compatibility layers will be executed
iteratively. However, Definitions and Pending Info contained a version, therefore only
the compatibility layers between its version and the last one will be ran.

Depending the data, warnings can be shown to the user to apply the migrations
themselves. Configuration for example will indicate the needed steps to migrate the
configuration file. Things will still run if it is not migrated, but the support of old
configurations can be dropped in the future.

To ensure that old data can be migrated to a last wanted state, some tests run all the
compatibility layers (``tests/test_compat_layers_*``).

.. _data_map_configuration:


Configuration
-------------

The configuration file is a yaml file used by virt-backup in ``virt_backup.config.Config``::

  # Be more verbose.
  # Default: False
  debug: bool

  # How many threads (simultaneous backups) to run. Use 0 to use all CPU threads
  # detected, 1 to disable multitheading for backups, or the number of threads wanted.
  # Default: 1
  threads: int


  ############################
  #### Libvirt connection ####
  ############################

  # Libvirt URI.
  uri: str

  # Libvirt authentication, if needed.
  username: str
  passphrase: str


  #######################
  #### Backup groups ####
  #######################

  # Groups are here to share the same backup options between multiple domains.
  # That way, it is possible, for example, to have a different policy retention
  # for a pool of guests in testing than for the one in production.

  # Define default options for all groups.
  default:
    target: str
    packager: str
    packager_opts: dict{packager_option: value}
    quiesce: bool
    hourly: int
    daily: int
    weekly: int
    monthly: int
    yearly: int

  # Groups definition.
  groups:
    # Group name
    str:
      # Backup directory.
      target: str

      # Packager to use for each backup:
      packager: str

      # Options for the choosen packager:
      packager_opts: dict{packager_option: value}

      # When doing `virt-backup backup` without specifying any group, only groups with
      # the autostart option enabled will be backup.
      # Default: False
      autostart: bool

      # Retention policy: the first backup of the day is considered as the
      # "daily" backup, first of the week "weekly", etc. The following options
      # detail how many backups of each type has to be kept. Set to "*" or None for an
      # infinite retention.
      # Default:
      #  hourly: 5
      #  daily: 5
      #  weekly: 5
      #  monthly: 5
      #  yearly: 5
      hourly: int
      daily: int
      weekly: int
      monthly: int
      yearly: int

      # Enable the Libvirt Quiesce option when taking the external snapshots.
      #
      # From Libvirt documentation: libvirt will try to freeze and unfreeze the guest
      # virtual machine’s mounted file system(s), using the guest agent. However, if the
      # guest virtual machine does not have a guest agent, snapshot creation will fail.
      #
      # However, virt-backup has a fallback mechanism if the snapshot happens to fail
      # with Quiesce enabled, and retries without it.
      quiesce: bool

      # Hosts definition.
      hosts:
        # Can either be a dictionary or a str.
        - host: str
          disks: []str
          quiesce: bool
        # If a str, can be the domain name, or a regex.
        - str


Backup definition
-----------------

A backup definition is a JSON file defining a backup. It is stored next to the backup
package to quickly get all the needed information about it, without the need of
unpacking anything::

  {
      name: str,
      domain_id: int,
      domain_name: str,
      // Dump of the libvirt definition of the targeted domain.
      domain_xml: str,
      disks: { disk_name <str>: backup_disk_name <str> },
      version: str,
      date: int,
      packager: {
          type: str,
          opts: {},
      },
  }

Example::

    {
        "name": "20191001-003401_3_test-domain",
        "domain_id": 3,
        "domain_name": "test-domain",
        "domain_xml": "<domain type='kvm' id='3'></domain>",
        "disks": {
            "vda": "20191001-003401_3_test-domain_vda.qcow2",
        },
        "version": "0.4.0",
        "date": 1569890041,
        "packager": {
            "type": "tar",
            "opts": {
                "compression": "gz",
                "compression_lvl": 6,
            },
        },
    }


Pending data
------------

Pending data is a temporary backup definition, following the same structure but with a bit more information in order to
clean everything if something failed::

    {
        name: str,
        domain_id: int,
        domain_name: str,
        // Dump of the libvirt definition of the targeted domain.
        domain_xml: str,
        disks: {
            disk_name <str>: {
                src: str,
                snapshot: str,
                target: str,
            }
        },
        version: str,
        date: int,
        packager: {
            type: str,
            opts: {},
        },
    }

Example::

    {
        "name": "20191001-003401_3_test-domain",
        "domain_id": 3,
        "domain_name": "test-domain",
        "domain_xml": "<domain type='kvm' id='3'></domain>",
        "disks": {
            "vda": {
                "src": "/tmp/test/vda.qcow2",
                "snapshot": "/tmp/test/vda.qcow2.snap",
                "target": "20191001-003401_3_test-domain_vda.qcow2",
            },
        },
        "version": "0.4.0",
        "date": 1569890041,
        "packager": {
            "type": "tar",
            "opts": {
                "compression": "gz",
                "compression_lvl": 6,
            },
        },
    }

The structure is the closest as possible from the backup definition.
