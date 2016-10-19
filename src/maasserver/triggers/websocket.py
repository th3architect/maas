# Copyright 2015-2016 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""
Websocket Triggers

Each trigger will call a procedure to send the notification. Each procedure
should be named with the table name "maasserver_node" and the action for the
trigger "node_create" followed by "notify".

E.g. "maasserver_node_node_create_notify".
"""

__all__ = [
    "register_websocket_triggers"
    ]

from textwrap import dedent

from maasserver.enum import NODE_TYPE
from maasserver.triggers import (
    register_procedure,
    register_trigger,
)
from maasserver.utils.orm import transactional

# Note that the corresponding test module (test_triggers) only tests that the
# triggers and procedures are registered.  The behavior of these procedures
# is tested (end-to-end testing) in test_listener.  We test it there because
# the asynchronous nature of the PG events makes it easier to test in
# test_listener where all the Twisted infrastructure is already in place.


# Procedure that is called when a tag is added or removed from a node/device.
# Sends a notify message for machine_update or device_update depending on if
# the node type is node.
NODE_TAG_NOTIFY = dedent("""\
    CREATE OR REPLACE FUNCTION %s() RETURNS trigger AS $$
    DECLARE
      node RECORD;
      pnode RECORD;
    BEGIN
      SELECT system_id, node_type, parent_id INTO node
      FROM maasserver_node
      WHERE id = %s;

      IF node.node_type = %d THEN
        PERFORM pg_notify('machine_update',CAST(node.system_id AS text));
      ELSIF node.node_type IN (%d, %d, %d) THEN
        PERFORM pg_notify('controller_update',CAST(node.system_id AS text));
      ELSIF node.parent_id IS NOT NULL THEN
        SELECT system_id INTO pnode
        FROM maasserver_node
        WHERE id = node.parent_id;
        PERFORM pg_notify('machine_update',CAST(pnode.system_id AS text));
      ELSE
        PERFORM pg_notify('device_update',CAST(node.system_id AS text));
      END IF;
      RETURN NEW;
    END;
    $$ LANGUAGE plpgsql;
    """)


# Procedure that is called when a tag is updated. This will send the correct
# machine_update or device_update notify message for all nodes with this tag.
TAG_NODES_NOTIFY = dedent("""\
    CREATE OR REPLACE FUNCTION tag_update_machine_device_notify()
    RETURNS trigger AS $$
    DECLARE
      node RECORD;
      pnode RECORD;
    BEGIN
      FOR node IN (
        SELECT
          maasserver_node.system_id,
          maasserver_node.node_type,
          maasserver_node.parent_id
        FROM maasserver_node_tags, maasserver_node
        WHERE maasserver_node_tags.tag_id = NEW.id
        AND maasserver_node_tags.node_id = maasserver_node.id)
      LOOP
        IF node.node_type = %d THEN
          PERFORM pg_notify('machine_update',CAST(node.system_id AS text));
        ELSIF node.node_type IN (%d, %d, %d) THEN
          PERFORM pg_notify('controller_update',CAST(node.system_id AS text));
        ELSIF node.parent_id IS NOT NULL THEN
          SELECT system_id INTO pnode
          FROM maasserver_node
          WHERE id = node.parent_id;
          PERFORM pg_notify('machine_update',CAST(pnode.system_id AS text));
        ELSE
          PERFORM pg_notify('device_update',CAST(node.system_id AS text));
        END IF;
      END LOOP;
      RETURN NEW;
    END;
    $$ LANGUAGE plpgsql;
    """)


# Procedure that is called when a event is created.
# Sends a notify message for machine_update or device_update depending on if
# the link node type is a node.
EVENT_NODE_NOTIFY = dedent("""\
    CREATE OR REPLACE FUNCTION event_create_machine_device_notify()
    RETURNS trigger AS $$
    DECLARE
      node RECORD;
      pnode RECORD;
    BEGIN
      SELECT system_id, node_type, parent_id INTO node
      FROM maasserver_node
      WHERE id = NEW.node_id;

      IF node.node_type = %d THEN
        PERFORM pg_notify('machine_update',CAST(node.system_id AS text));
      ELSIF node.node_type IN (%d, %d, %d) THEN
        PERFORM pg_notify('controller_update',CAST(node.system_id AS text));
      ELSIF node.parent_id IS NOT NULL THEN
        SELECT system_id INTO pnode
        FROM maasserver_node
        WHERE id = node.parent_id;
        PERFORM pg_notify('machine_update',CAST(pnode.system_id AS text));
      ELSE
        PERFORM pg_notify('device_update',CAST(node.system_id AS text));
      END IF;
      RETURN NEW;
    END;
    $$ LANGUAGE plpgsql;
    """)


# Procedure that is called when a static ip address is linked or unlinked to
# an Interface. Sends a notify message for domain_update
INTERFACE_IP_ADDRESS_DOMAIN_NOTIFY = dedent("""\
    CREATE OR REPLACE FUNCTION %s() RETURNS trigger AS $$
    DECLARE
      domain RECORD;
    BEGIN
      SELECT maasserver_domain.id INTO domain
      FROM maasserver_node, maasserver_interface, maasserver_domain
      WHERE maasserver_node.id = maasserver_interface.node_id
      AND maasserver_domain.id = maasserver_node.domain_id
      AND maasserver_interface.id = %s;

      IF domain.id IS NOT NULL THEN
        PERFORM pg_notify('domain_update',CAST(domain.id AS text));
      END IF;
      RETURN NEW;
    END;
    $$ LANGUAGE plpgsql;
    """)


# Procedure that is called when a static ip address is linked or unlinked to
# an Interface. Sends a notify message for machine_update or device_update
# depending on if the node type is node.
INTERFACE_IP_ADDRESS_NODE_NOTIFY = dedent("""\
    CREATE OR REPLACE FUNCTION %s() RETURNS trigger AS $$
    DECLARE
      node RECORD;
      pnode RECORD;
    BEGIN
      SELECT system_id, node_type, parent_id INTO node
      FROM maasserver_node, maasserver_interface
      WHERE maasserver_node.id = maasserver_interface.node_id
      AND maasserver_interface.id = %s;

      IF node.node_type = %d THEN
        PERFORM pg_notify('machine_update',CAST(node.system_id AS text));
      ELSIF node.node_type IN (%d, %d, %d) THEN
        PERFORM pg_notify('controller_update',CAST(node.system_id AS text));
      ELSIF node.parent_id IS NOT NULL THEN
        SELECT system_id INTO pnode
        FROM maasserver_node
        WHERE id = node.parent_id;
        PERFORM pg_notify('machine_update',CAST(pnode.system_id AS text));
      ELSE
        PERFORM pg_notify('device_update',CAST(node.system_id AS text));
      END IF;
      RETURN NEW;
    END;
    $$ LANGUAGE plpgsql;
    """)


# Procedure that is called when a Interface address updated. Will send
# machine_update or device_update when the Interface is moved from another node
# to a new node. Sends a notify message for machine_update or device_update
# depending on if the node type is node, both for the old node and the new
# node.
INTERFACE_UPDATE_NODE_NOTIFY = dedent("""\
    CREATE OR REPLACE FUNCTION nd_interface_update_notify()
    RETURNS trigger AS $$
    DECLARE
      node RECORD;
      pnode RECORD;
    BEGIN
      IF OLD.node_id != NEW.node_id THEN
        SELECT system_id, node_type, parent_id INTO node
        FROM maasserver_node
        WHERE id = OLD.node_id;

        IF node.node_type = %d THEN
          PERFORM pg_notify('machine_update',CAST(node.system_id AS text));
        ELSIF node.node_type IN (%d, %d, %d) THEN
          PERFORM pg_notify('controller_update',CAST(node.system_id AS text));
        ELSIF node.parent_id IS NOT NULL THEN
          SELECT system_id INTO pnode
          FROM maasserver_node
          WHERE id = node.parent_id;
          PERFORM pg_notify('machine_update',CAST(pnode.system_id AS text));
        ELSE
          PERFORM pg_notify('device_update',CAST(node.system_id AS text));
        END IF;
      END IF;

      SELECT system_id, node_type, parent_id INTO node
      FROM maasserver_node
      WHERE id = NEW.node_id;

      IF node.node_type = %d THEN
        PERFORM pg_notify('machine_update',CAST(node.system_id AS text));
      ELSIF node.node_type IN (%d, %d, %d) THEN
        PERFORM pg_notify('controller_update',CAST(node.system_id AS text));
      ELSIF node.parent_id IS NOT NULL THEN
        SELECT system_id INTO pnode
        FROM maasserver_node
        WHERE id = node.parent_id;
        PERFORM pg_notify('machine_update',CAST(pnode.system_id AS text));
      ELSE
        PERFORM pg_notify('device_update',CAST(node.system_id AS text));
      END IF;
      RETURN NEW;
    END;
    $$ LANGUAGE plpgsql;
    """)


# Procedure that is called when a physical or virtual block device is updated.
# Sends a notify message for machine_update or device_update depending on if
# the node type is node.
PHYSICAL_OR_VIRTUAL_BLOCK_DEVICE_NODE_NOTIFY = dedent("""\
    CREATE OR REPLACE FUNCTION %s() RETURNS trigger AS $$
    DECLARE
      node RECORD;
    BEGIN
      SELECT system_id, node_type INTO node
      FROM maasserver_node, maasserver_blockdevice
      WHERE maasserver_node.id = maasserver_blockdevice.node_id
      AND maasserver_blockdevice.id = %s;

      IF node.node_type = %d THEN
        PERFORM pg_notify('machine_update',CAST(node.system_id AS text));
      END IF;
      RETURN NEW;
    END;
    $$ LANGUAGE plpgsql;
    """)


# Procedure that is called when the partition table on a block device is
# updated.
PARTITIONTABLE_NODE_NOTIFY = dedent("""\
    CREATE OR REPLACE FUNCTION %s() RETURNS TRIGGER AS $$
    DECLARE
      node RECORD;
    BEGIN
      SELECT system_id, node_type INTO node
      FROM maasserver_node, maasserver_blockdevice
        WHERE maasserver_node.id = maasserver_blockdevice.node_id
        AND maasserver_blockdevice.id = %s;

      IF node.node_type = %d THEN
        PERFORM pg_notify('machine_update',CAST(node.system_id AS text));
      END IF;
      RETURN NEW;
    END;
    $$ LANGUAGE plpgsql;
    """)


# Procedure that is called when the partition on a partition table is updated.
PARTITION_NODE_NOTIFY = dedent("""\
    CREATE OR REPLACE FUNCTION %s() RETURNS trigger as $$
    DECLARE
      node RECORD;
    BEGIN
      SELECT system_id, node_type INTO node
      FROM maasserver_node,
           maasserver_blockdevice,
           maasserver_partitiontable
      WHERE maasserver_node.id = maasserver_blockdevice.node_id
      AND maasserver_blockdevice.id = maasserver_partitiontable.block_device_id
      AND maasserver_partitiontable.id = %s;

      IF node.node_type = %d THEN
        PERFORM pg_notify('machine_update',CAST(node.system_id AS text));
      END IF;
      RETURN NEW;
    END;
    $$ LANGUAGE plpgsql;
    """)


# Procedure that is called when the filesystem on a partition is updated.
FILESYSTEM_NODE_NOTIFY = dedent("""\
    CREATE OR REPLACE FUNCTION {0}() RETURNS trigger as $$
    DECLARE
      node RECORD;
    BEGIN
      IF {1} IS NOT NULL
      THEN
        SELECT system_id, node_type INTO node
          FROM maasserver_node,
               maasserver_blockdevice
         WHERE maasserver_node.id = maasserver_blockdevice.node_id
           AND maasserver_blockdevice.id = {1};
      ELSIF {2} IS NOT NULL
      THEN
        SELECT system_id, node_type INTO node
          FROM maasserver_node,
               maasserver_blockdevice,
               maasserver_partition,
               maasserver_partitiontable
         WHERE maasserver_node.id = maasserver_blockdevice.node_id
           AND maasserver_blockdevice.id =
               maasserver_partitiontable.block_device_id
           AND maasserver_partitiontable.id =
               maasserver_partition.partition_table_id
           AND maasserver_partition.id = {2};
      ELSIF {3} IS NOT NULL
      THEN
        SELECT system_id, node_type INTO node
          FROM maasserver_node
         WHERE maasserver_node.id = {3};
      END IF;

      IF node.node_type = {4:d} THEN
          PERFORM pg_notify('machine_update', CAST(node.system_id AS text));
      END IF;

      RETURN NEW;
    END;
    $$ LANGUAGE plpgsql;
    """)


# Procedure that is called when the filesystemgroup is updated.
FILESYSTEMGROUP_NODE_NOTIFY = dedent("""\
    CREATE OR REPLACE FUNCTION %s() RETURNS trigger as $$
    DECLARE
      node RECORD;
    BEGIN
      SELECT system_id, node_type INTO node
      FROM maasserver_node,
           maasserver_blockdevice,
           maasserver_partition,
           maasserver_partitiontable,
           maasserver_filesystem
      WHERE maasserver_node.id = maasserver_blockdevice.node_id
      AND maasserver_blockdevice.id = maasserver_partitiontable.block_device_id
      AND maasserver_partitiontable.id =
          maasserver_partition.partition_table_id
      AND maasserver_partition.id = maasserver_filesystem.partition_id
      AND (maasserver_filesystem.filesystem_group_id = %s
          OR maasserver_filesystem.cache_set_id = %s);

      IF node.node_type = %d THEN
          PERFORM pg_notify('machine_update',CAST(node.system_id AS text));
      END IF;
      RETURN NEW;
    END;
    $$ LANGUAGE plpgsql;
    """)


# Procedure that is called when the cacheset is updated.
CACHESET_NODE_NOTIFY = dedent("""\
    CREATE OR REPLACE FUNCTION %s() RETURNS trigger as $$
    DECLARE
      node RECORD;
    BEGIN
      SELECT system_id, node_type INTO node
      FROM maasserver_node,
           maasserver_blockdevice,
           maasserver_partition,
           maasserver_partitiontable,
           maasserver_filesystem
      WHERE maasserver_node.id = maasserver_blockdevice.node_id
      AND maasserver_blockdevice.id = maasserver_partitiontable.block_device_id
      AND maasserver_partitiontable.id =
          maasserver_partition.partition_table_id
      AND maasserver_partition.id = maasserver_filesystem.partition_id
      AND maasserver_filesystem.cache_set_id = %s;

      IF node.node_type = %d THEN
          PERFORM pg_notify('machine_update',CAST(node.system_id AS text));
      END IF;
      RETURN NEW;
    END;
    $$ LANGUAGE plpgsql;
    """)

# Procedure that is called when the subnet is updated.
SUBNET_NODE_NOTIFY = dedent("""\
    CREATE OR REPLACE FUNCTION %s() RETURNS trigger AS $$
    DECLARE
        node RECORD;
        pnode RECORD;
    BEGIN
      FOR node IN (
        SELECT DISTINCT ON (maasserver_node.id)
          system_id, node_type, parent_id
        FROM
          maasserver_node,
          maasserver_subnet,
          maasserver_interface,
          maasserver_interface_ip_addresses AS ip_link,
          maasserver_staticipaddress
        WHERE maasserver_subnet.id = %s
        AND maasserver_staticipaddress.subnet_id = maasserver_subnet.id
        AND ip_link.staticipaddress_id = maasserver_staticipaddress.id
        AND ip_link.interface_id = maasserver_interface.id
        AND maasserver_node.id = maasserver_interface.node_id)
      LOOP
        IF node.node_type = %d THEN
          PERFORM pg_notify('machine_update',CAST(node.system_id AS text));
        ELSIF node.node_type IN (%d, %d, %d) THEN
          PERFORM pg_notify('controller_update',CAST(node.system_id AS text));
        ELSIF node.parent_id IS NOT NULL THEN
          SELECT system_id INTO pnode
          FROM maasserver_node
          WHERE id = node.parent_id;
          PERFORM pg_notify('machine_update',CAST(pnode.system_id AS text));
        ELSE
          PERFORM pg_notify('device_update',CAST(node.system_id AS text));
        END IF;
      END LOOP;
      RETURN NEW;
    END;
    $$ LANGUAGE plpgsql;
    """)


# Procedure that is called when fabric is updated.
FABRIC_NODE_NOTIFY = dedent("""\
    CREATE OR REPLACE FUNCTION %s() RETURNS trigger AS $$
    DECLARE
        node RECORD;
        pnode RECORD;
    BEGIN
      FOR node IN (
        SELECT DISTINCT ON (maasserver_node.id)
          system_id, node_type, parent_id
        FROM
          maasserver_node,
          maasserver_fabric,
          maasserver_interface,
          maasserver_vlan
        WHERE maasserver_fabric.id = %s
        AND maasserver_vlan.fabric_id = maasserver_fabric.id
        AND maasserver_node.id = maasserver_interface.node_id
        AND maasserver_vlan.id = maasserver_interface.vlan_id)
      LOOP
        IF node.node_type = %d THEN
          PERFORM pg_notify('machine_update',CAST(node.system_id AS text));
        ELSIF node.node_type IN (%d, %d, %d) THEN
          PERFORM pg_notify('controller_update',CAST(node.system_id AS text));
        ELSIF node.parent_id IS NOT NULL THEN
          SELECT system_id INTO pnode
          FROM maasserver_node
          WHERE id = node.parent_id;
          PERFORM pg_notify('machine_update',CAST(pnode.system_id AS text));
        ELSE
          PERFORM pg_notify('device_update',CAST(node.system_id AS text));
        END IF;
      END LOOP;
      RETURN NEW;
    END;
    $$ LANGUAGE plpgsql;
    """)


# Procedure that is called when space is updated.
SPACE_NODE_NOTIFY = dedent("""\
    CREATE OR REPLACE FUNCTION %s() RETURNS trigger AS $$
    DECLARE
        node RECORD;
        pnode RECORD;
    BEGIN
      FOR node IN (
        SELECT DISTINCT ON (maasserver_node.id)
          system_id, node_type, parent_id
        FROM
          maasserver_node,
          maasserver_space,
          maasserver_subnet,
          maasserver_interface,
          maasserver_interface_ip_addresses AS ip_link,
          maasserver_staticipaddress
        WHERE maasserver_space.id = %s
        AND maasserver_subnet.space_id = maasserver_space.id
        AND maasserver_staticipaddress.subnet_id = maasserver_subnet.id
        AND ip_link.staticipaddress_id = maasserver_staticipaddress.id
        AND ip_link.interface_id = maasserver_interface.id
        AND maasserver_node.id = maasserver_interface.node_id)
      LOOP
        IF node.node_type = %d THEN
          PERFORM pg_notify('machine_update',CAST(node.system_id AS text));
        ELSIF node.node_type IN (%d, %d, %d) THEN
          PERFORM pg_notify('controller_update',CAST(node.system_id AS text));
        ELSIF node.parent_id IS NOT NULL THEN
          SELECT system_id INTO pnode
          FROM maasserver_node
          WHERE id = node.parent_id;
          PERFORM pg_notify('machine_update',CAST(pnode.system_id AS text));
        ELSE
          PERFORM pg_notify('device_update',CAST(node.system_id AS text));
        END IF;
      END LOOP;
      RETURN NEW;
    END;
    $$ LANGUAGE plpgsql;
    """)


# Procedure that is called when vlan is updated.
VLAN_NODE_NOTIFY = dedent("""\
    CREATE OR REPLACE FUNCTION %s() RETURNS trigger AS $$
    DECLARE
        node RECORD;
        pnode RECORD;
    BEGIN
      FOR node IN (
        SELECT DISTINCT ON (maasserver_node.id)
          system_id, node_type, parent_id
        FROM maasserver_node, maasserver_interface, maasserver_vlan
        WHERE maasserver_vlan.id = %s
        AND maasserver_node.id = maasserver_interface.node_id
        AND maasserver_vlan.id = maasserver_interface.vlan_id)
      LOOP
        IF node.node_type = %d THEN
          PERFORM pg_notify('machine_update',CAST(node.system_id AS text));
        ELSIF node.node_type IN (%d, %d, %d) THEN
          PERFORM pg_notify('controller_update',CAST(node.system_id AS text));
        ELSIF node.parent_id IS NOT NULL THEN
          SELECT system_id INTO pnode
          FROM maasserver_node
          WHERE id = node.parent_id;
          PERFORM pg_notify('machine_update',CAST(pnode.system_id AS text));
        ELSE
          PERFORM pg_notify('device_update',CAST(node.system_id AS text));
        END IF;
      END LOOP;
      RETURN NEW;
    END;
    $$ LANGUAGE plpgsql;
    """)


# Procedure that is called when an IP address is updated to update the related
# node.
STATIC_IP_ADDRESS_NODE_NOTIFY = dedent("""\
    CREATE OR REPLACE FUNCTION %s() RETURNS trigger AS $$
    DECLARE
        node RECORD;
        pnode RECORD;
    BEGIN
      FOR node IN (
        SELECT DISTINCT ON (maasserver_node.id)
          system_id, node_type, parent_id
        FROM
          maasserver_node,
          maasserver_interface,
          maasserver_interface_ip_addresses AS ip_link
        WHERE ip_link.staticipaddress_id = %s
        AND ip_link.interface_id = maasserver_interface.id
        AND maasserver_node.id = maasserver_interface.node_id)
      LOOP
        IF node.node_type = %d THEN
          PERFORM pg_notify('machine_update',CAST(node.system_id AS text));
        ELSIF node.node_type IN (%d, %d, %d) THEN
          PERFORM pg_notify('controller_update',CAST(node.system_id AS text));
        ELSIF node.parent_id IS NOT NULL THEN
          SELECT system_id INTO pnode
          FROM maasserver_node
          WHERE id = node.parent_id;
          PERFORM pg_notify('machine_update',CAST(pnode.system_id AS text));
        ELSE
          PERFORM pg_notify('device_update',CAST(node.system_id AS text));
        END IF;
      END LOOP;
      RETURN NEW;
    END;
    $$ LANGUAGE plpgsql;
    """)

# Procedure that is called when an IP address is updated to update its related
# subnet.
STATIC_IP_ADDRESS_SUBNET_NOTIFY = dedent("""\
    CREATE OR REPLACE FUNCTION %s() RETURNS trigger AS $$
    BEGIN
      IF OLD.subnet_id != NEW.subnet_id THEN
        IF OLD.subnet_id IS NOT NULL THEN
          PERFORM pg_notify('subnet_update',CAST(OLD.subnet_id AS text));
        END IF;
      END IF;
      IF NEW.subnet_id IS NOT NULL THEN
        PERFORM pg_notify('subnet_update',CAST(NEW.subnet_id AS text));
      END IF;
      RETURN NEW;
    END;
    $$ LANGUAGE plpgsql;
    """)

# Procedure that is called when an IP address is updated, to update its related
# domain.
STATIC_IP_ADDRESS_DOMAIN_UPDATE_NOTIFY = dedent("""\
    CREATE OR REPLACE FUNCTION %s() RETURNS trigger AS $$
    DECLARE
      dom RECORD;
    BEGIN
      IF ((OLD.ip IS NULL and NEW.ip IS NOT NULL) OR
            (OLD.ip IS NOT NULL and NEW.ip IS NULL) OR
            OLD.ip != NEW.ip) THEN
        FOR dom IN (
          SELECT DISTINCT ON (domain.id)
            domain.id
          FROM maasserver_staticipaddress AS staticipaddress
          LEFT JOIN (
            maasserver_interface_ip_addresses AS iia
            JOIN maasserver_interface AS interface ON
              iia.interface_id = interface.id
            JOIN maasserver_node AS node ON
              node.id = interface.node_id) ON
            iia.staticipaddress_id = staticipaddress.id
          LEFT JOIN (
            maasserver_dnsresource_ip_addresses AS dia
            JOIN maasserver_dnsresource AS dnsresource ON
              dia.dnsresource_id = dnsresource.id) ON
            dia.staticipaddress_id = staticipaddress.id
          JOIN maasserver_domain AS domain ON
            domain.id = node.domain_id OR domain.id = dnsresource.domain_id
          WHERE staticipaddress.id = OLD.id OR staticipaddress.id = NEW.id)
        LOOP
          PERFORM pg_notify('domain_update',CAST(dom.id AS text));
        END LOOP;
      END IF;
      RETURN NEW;
    END;
    $$ LANGUAGE plpgsql;
    """)

# Procedure that is called when an IP address is inserted or deleted, to update
# its related domain.
STATIC_IP_ADDRESS_DOMAIN_NOTIFY = dedent("""\
    CREATE OR REPLACE FUNCTION %s() RETURNS trigger AS $$
    DECLARE
      dom RECORD;
    BEGIN
      FOR dom IN (
        SELECT DISTINCT ON (domain.id)
          domain.id
        FROM maasserver_staticipaddress AS staticipaddress
        LEFT JOIN (
          maasserver_interface_ip_addresses AS iia
          JOIN maasserver_interface AS interface ON
            iia.interface_id = interface.id
          JOIN maasserver_node AS node ON
            node.id = interface.node_id) ON
          iia.staticipaddress_id = staticipaddress.id
        LEFT JOIN (
          maasserver_dnsresource_ip_addresses AS dia
          JOIN maasserver_dnsresource AS dnsresource ON
            dia.dnsresource_id = dnsresource.id) ON
          dia.staticipaddress_id = staticipaddress.id
        JOIN maasserver_domain AS domain ON
          domain.id = node.domain_id OR domain.id = dnsresource.domain_id
        WHERE staticipaddress.id = %s)
      LOOP
        PERFORM pg_notify('domain_update',CAST(dom.id AS text));
      END LOOP;
      RETURN NEW;
    END;
    $$ LANGUAGE plpgsql;
    """)

# Procedure that is called when an IP range is created to update its related
# subnet.
IP_RANGE_SUBNET_INSERT_NOTIFY = dedent("""\
    CREATE OR REPLACE FUNCTION %s() RETURNS trigger AS $$
    BEGIN
      IF NEW.subnet_id IS NOT NULL THEN
        PERFORM pg_notify('subnet_update',CAST(NEW.subnet_id AS text));
      END IF;
      RETURN NEW;
    END;
    $$ LANGUAGE plpgsql;
    """)

# Procedure that is called when an IP range is updated to update its related
# subnet.
IP_RANGE_SUBNET_UPDATE_NOTIFY = dedent("""\
    CREATE OR REPLACE FUNCTION %s() RETURNS trigger AS $$
    BEGIN
      IF OLD.subnet_id != NEW.subnet_id THEN
        IF OLD.subnet_id IS NOT NULL THEN
          PERFORM pg_notify('subnet_update',CAST(OLD.subnet_id AS text));
        END IF;
      END IF;
      IF NEW.subnet_id IS NOT NULL THEN
        PERFORM pg_notify('subnet_update',CAST(NEW.subnet_id AS text));
      END IF;
      RETURN NEW;
    END;
    $$ LANGUAGE plpgsql;
    """)

# Procedure that is called when an IP range is deleted to update its related
# subnet.
IP_RANGE_SUBNET_DELETE_NOTIFY = dedent("""\
    CREATE OR REPLACE FUNCTION %s() RETURNS trigger AS $$
    BEGIN
      IF OLD.subnet_id IS NOT NULL THEN
        PERFORM pg_notify('subnet_update',CAST(OLD.subnet_id AS text));
      END IF;
      RETURN OLD;
    END;
    $$ LANGUAGE plpgsql;
    """)

# Procedure that is called when a DNSData entry is changed.
DNSDATA_DOMAIN_NOTIFY = dedent("""\
    CREATE OR REPLACE FUNCTION %s() RETURNS trigger AS $$
    DECLARE
        dom RECORD;
    BEGIN
      SELECT DISTINCT ON (domain_id) domain_id INTO dom
      FROM maasserver_dnsresource AS dnsresource
      WHERE dnsresource.id = %s;
      PERFORM pg_notify('domain_update',CAST(dom.domain_id AS text));
      RETURN NEW;
    END;
    $$ LANGUAGE plpgsql;
    """)

# Procedure that is called when a DNSData entry is inserted/removed.
DNSRESOURCE_DOMAIN_NOTIFY = dedent("""\
    CREATE OR REPLACE FUNCTION %s() RETURNS trigger AS $$
    DECLARE
        domain RECORD;
    BEGIN
      PERFORM pg_notify('domain_update',CAST(%s.domain_id AS text));
      RETURN NEW;
    END;
    $$ LANGUAGE plpgsql;
    """)

# Procedure that is called when a DNSData entry is updated.
DNSRESOURCE_DOMAIN_UPDATE_NOTIFY = dedent("""\
    CREATE OR REPLACE FUNCTION %s() RETURNS trigger AS $$
    DECLARE
        domain RECORD;
    BEGIN
      PERFORM pg_notify('domain_update',CAST(OLD.domain_id AS text));
      IF OLD.domain_id != NEW.domain_id THEN
        PERFORM pg_notify('domain_update',CAST(NEW.domain_id AS text));
      END IF;
      RETURN NEW;
    END;
    $$ LANGUAGE plpgsql;
    """)


# Procedure that is called when a static ip address is linked or unlinked to
# an Interface. Sends a notify message for domain_update
DNSRESOURCE_IP_ADDRESS_DOMAIN_NOTIFY = dedent("""\
    CREATE OR REPLACE FUNCTION %s() RETURNS trigger AS $$
    DECLARE
      domain RECORD;
    BEGIN
      SELECT maasserver_domain.id INTO domain
      FROM maasserver_dnsresource, maasserver_domain
      WHERE maasserver_domain.id = maasserver_dnsresource.domain_id
      AND maasserver_dnsresource.id = %s;

      IF domain.id IS NOT NULL THEN
        PERFORM pg_notify('domain_update',CAST(domain.id AS text));
      END IF;
      RETURN NEW;
    END;
    $$ LANGUAGE plpgsql;
    """)


def render_notification_procedure(proc_name, event_name, cast):
    return dedent("""\
        CREATE OR REPLACE FUNCTION %s() RETURNS trigger AS $$
        DECLARE
        BEGIN
          PERFORM pg_notify('%s',CAST(%s AS text));
          RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        """ % (proc_name, event_name, cast))


def render_device_notification_procedure(proc_name, event_name, obj):
    return dedent("""\
        CREATE OR REPLACE FUNCTION {proc_name}() RETURNS trigger AS $$
        DECLARE
          pnode RECORD;
        BEGIN
          IF {obj}.parent_id IS NOT NULL THEN
            SELECT system_id INTO pnode
            FROM maasserver_node
            WHERE id = {obj}.parent_id;
            PERFORM pg_notify('machine_update',CAST(pnode.system_id AS text));
          ELSE
            PERFORM pg_notify('{event_name}',CAST({obj}.system_id AS text));
          END IF;
          RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        """.format(proc_name=proc_name, event_name=event_name, obj=obj))


def render_node_related_notification_procedure(proc_name, node_id_relation):
    return dedent("""\
        CREATE OR REPLACE FUNCTION %s() RETURNS trigger AS $$
        DECLARE
          node RECORD;
          pnode RECORD;
        BEGIN
          SELECT system_id, node_type, parent_id INTO node
          FROM maasserver_node
          WHERE id = %s;

          IF node.node_type = %d THEN
            PERFORM pg_notify('machine_update',CAST(node.system_id AS text));
          ELSIF node.node_type IN (%d, %d, %d) THEN
            PERFORM pg_notify('controller_update',CAST(
              node.system_id AS text));
          ELSIF node.parent_id IS NOT NULL THEN
            SELECT system_id INTO pnode
            FROM maasserver_node
            WHERE id = node.parent_id;
            PERFORM pg_notify('machine_update',CAST(pnode.system_id AS text));
          ELSE
            PERFORM pg_notify('device_update',CAST(node.system_id AS text));
          END IF;
          RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        """ % (proc_name, node_id_relation, NODE_TYPE.MACHINE,
               NODE_TYPE.RACK_CONTROLLER, NODE_TYPE.REGION_CONTROLLER,
               NODE_TYPE.REGION_AND_RACK_CONTROLLER))


def node_type_change():
    return dedent("""\
        CREATE OR REPLACE FUNCTION node_type_change_notify()
        RETURNS trigger AS $$
        BEGIN
          IF (OLD.node_type != NEW.node_type AND NOT (
              (
                OLD.node_type = {rack_controller} OR
                OLD.node_type = {region_controller} OR
                OLD.node_type = {region_and_rack_controller}
              ) AND (
                NEW.node_type = {rack_controller} OR
                NEW.node_type = {region_controller} OR
                NEW.node_type = {region_and_rack_controller}
              ))) THEN
            CASE OLD.node_type
              WHEN {machine} THEN
                PERFORM pg_notify('machine_delete',CAST(
                  OLD.system_id AS TEXT));
              WHEN {device} THEN
                PERFORM pg_notify('device_delete',CAST(
                  OLD.system_id AS TEXT));
              WHEN {rack_controller} THEN
                PERFORM pg_notify('controller_delete',CAST(
                  OLD.system_id AS TEXT));
              WHEN {region_controller} THEN
                PERFORM pg_notify('controller_delete',CAST(
                  OLD.system_id AS TEXT));
              WHEN {region_and_rack_controller} THEN
                PERFORM pg_notify('controller_delete',CAST(
                  OLD.system_id AS TEXT));
            END CASE;
            CASE NEW.node_type
              WHEN {machine} THEN
                PERFORM pg_notify('machine_create',CAST(
                  NEW.system_id AS TEXT));
              WHEN {device} THEN
                PERFORM pg_notify('device_create',CAST(
                  NEW.system_id AS TEXT));
              WHEN {rack_controller} THEN
                PERFORM pg_notify('controller_create',CAST(
                  NEW.system_id AS TEXT));
              WHEN {region_controller} THEN
                PERFORM pg_notify('controller_create',CAST(
                  NEW.system_id AS TEXT));
              WHEN {region_and_rack_controller} THEN
                PERFORM pg_notify('controller_create',CAST(
                  NEW.system_id AS TEXT));
            END CASE;
          END IF;
          RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
    """.format(
        machine=NODE_TYPE.MACHINE, device=NODE_TYPE.DEVICE,
        rack_controller=NODE_TYPE.RACK_CONTROLLER,
        region_controller=NODE_TYPE.REGION_CONTROLLER,
        region_and_rack_controller=NODE_TYPE.REGION_AND_RACK_CONTROLLER))


@transactional
def register_websocket_triggers():
    """Register all websocket triggers into the database."""

    for (proc_name_prefix, event_name_prefix, node_type) in (
        ('machine', 'machine', NODE_TYPE.MACHINE),
        ('rack_controller', 'controller', NODE_TYPE.RACK_CONTROLLER),
        ('region_controller', 'controller', NODE_TYPE.REGION_CONTROLLER),
        ('region_and_rack_controller', 'controller',
         NODE_TYPE.REGION_AND_RACK_CONTROLLER)):

        # Non-Device Node types
        register_procedure(
            render_notification_procedure(
                '%s_create_notify' % proc_name_prefix,
                '%s_create' % event_name_prefix,
                'NEW.system_id'))
        register_procedure(
            render_notification_procedure(
                '%s_update_notify' % proc_name_prefix,
                '%s_update' % event_name_prefix,
                'NEW.system_id'))
        register_procedure(
            render_notification_procedure(
                '%s_delete_notify' % proc_name_prefix,
                '%s_delete' % event_name_prefix,
                'OLD.system_id'))
        register_trigger(
            "maasserver_node",
            "%s_create_notify" % proc_name_prefix,
            "insert",
            {'NEW.node_type': node_type})
        register_trigger(
            "maasserver_node",
            "%s_update_notify" % proc_name_prefix,
            "update",
            {'NEW.node_type': node_type})
        register_trigger(
            "maasserver_node",
            "%s_delete_notify" % proc_name_prefix,
            "delete",
            {'OLD.node_type': node_type})

    # Config table
    register_procedure(
        render_notification_procedure(
            'config_create_notify', 'config_create', 'NEW.id'))
    register_procedure(
        render_notification_procedure(
            'config_update_notify', 'config_update', 'NEW.id'))
    register_procedure(
        render_notification_procedure(
            'config_delete_notify', 'config_delete', 'OLD.id'))
    register_trigger(
        "maasserver_config", "config_create_notify", "insert")
    register_trigger(
        "maasserver_config", "config_update_notify", "update")
    register_trigger(
        "maasserver_config", "config_delete_notify", "delete")

    # Device Node types
    register_procedure(
        render_device_notification_procedure(
            'device_create_notify', 'device_create', 'NEW'))
    register_procedure(
        render_device_notification_procedure(
            'device_update_notify', 'device_update', 'NEW'))
    register_procedure(
        render_device_notification_procedure(
            'device_delete_notify', 'device_delete', 'OLD'))
    register_trigger(
        "maasserver_node", "device_create_notify", "insert",
        {'NEW.node_type': NODE_TYPE.DEVICE})
    register_trigger(
        "maasserver_node", "device_update_notify", "update",
        {'NEW.node_type': NODE_TYPE.DEVICE})
    register_trigger(
        "maasserver_node", "device_delete_notify", "delete",
        {'OLD.node_type': NODE_TYPE.DEVICE})

    # VLAN table
    register_procedure(
        render_notification_procedure(
            'vlan_create_notify', 'vlan_create', 'NEW.id'))
    register_procedure(
        render_notification_procedure(
            'vlan_update_notify', 'vlan_update', 'NEW.id'))
    register_procedure(
        render_notification_procedure(
            'vlan_delete_notify', 'vlan_delete', 'OLD.id'))
    register_trigger(
        "maasserver_vlan", "vlan_create_notify", "insert")
    register_trigger(
        "maasserver_vlan", "vlan_update_notify", "update")
    register_trigger(
        "maasserver_vlan", "vlan_delete_notify", "delete")

    # IPRange table
    register_procedure(
        render_notification_procedure(
            'iprange_create_notify', 'iprange_create', 'NEW.id'))
    register_procedure(
        render_notification_procedure(
            'iprange_update_notify', 'iprange_update', 'NEW.id'))
    register_procedure(
        render_notification_procedure(
            'iprange_delete_notify', 'iprange_delete', 'OLD.id'))
    register_trigger(
        "maasserver_iprange", "iprange_create_notify", "insert")
    register_trigger(
        "maasserver_iprange", "iprange_update_notify", "update")
    register_trigger(
        "maasserver_iprange", "iprange_delete_notify", "delete")

    # StaticRoute table
    register_procedure(
        render_notification_procedure(
            'staticroute_create_notify', 'staticroute_create', 'NEW.id'))
    register_procedure(
        render_notification_procedure(
            'staticroute_update_notify', 'staticroute_update', 'NEW.id'))
    register_procedure(
        render_notification_procedure(
            'staticroute_delete_notify', 'staticroute_delete', 'OLD.id'))
    register_trigger(
        "maasserver_staticroute", "staticroute_create_notify", "insert")
    register_trigger(
        "maasserver_staticroute", "staticroute_update_notify", "update")
    register_trigger(
        "maasserver_staticroute", "staticroute_delete_notify", "delete")

    # Fabric table
    register_procedure(
        render_notification_procedure(
            'fabric_create_notify', 'fabric_create', 'NEW.id'))
    register_procedure(
        render_notification_procedure(
            'fabric_update_notify', 'fabric_update', 'NEW.id'))
    register_procedure(
        render_notification_procedure(
            'fabric_delete_notify', 'fabric_delete', 'OLD.id'))
    register_trigger(
        "maasserver_fabric", "fabric_create_notify", "insert")
    register_trigger(
        "maasserver_fabric", "fabric_update_notify", "update")
    register_trigger(
        "maasserver_fabric", "fabric_delete_notify", "delete")

    # Space table
    register_procedure(
        render_notification_procedure(
            'space_create_notify', 'space_create', 'NEW.id'))
    register_procedure(
        render_notification_procedure(
            'space_update_notify', 'space_update', 'NEW.id'))
    register_procedure(
        render_notification_procedure(
            'space_delete_notify', 'space_delete', 'OLD.id'))
    register_trigger(
        "maasserver_space", "space_create_notify", "insert")
    register_trigger(
        "maasserver_space", "space_update_notify", "update")
    register_trigger(
        "maasserver_space", "space_delete_notify", "delete")

    # Subnet table
    register_procedure(
        render_notification_procedure(
            'subnet_create_notify', 'subnet_create', 'NEW.id'))
    register_procedure(
        render_notification_procedure(
            'subnet_update_notify', 'subnet_update', 'NEW.id'))
    register_procedure(
        render_notification_procedure(
            'subnet_delete_notify', 'subnet_delete', 'OLD.id'))
    register_trigger(
        "maasserver_subnet", "subnet_create_notify", "insert")
    register_trigger(
        "maasserver_subnet", "subnet_update_notify", "update")
    register_trigger(
        "maasserver_subnet", "subnet_delete_notify", "delete")

    # Subnet node notifications
    register_procedure(
        SUBNET_NODE_NOTIFY % (
            'subnet_machine_update_notify', 'NEW.id', NODE_TYPE.MACHINE,
            NODE_TYPE.RACK_CONTROLLER, NODE_TYPE.REGION_CONTROLLER,
            NODE_TYPE.REGION_AND_RACK_CONTROLLER))
    register_trigger(
        "maasserver_subnet",
        "subnet_machine_update_notify", "update")

    # Fabric node notifications
    register_procedure(
        FABRIC_NODE_NOTIFY % (
            'fabric_machine_update_notify', 'NEW.id', NODE_TYPE.MACHINE,
            NODE_TYPE.RACK_CONTROLLER, NODE_TYPE.REGION_CONTROLLER,
            NODE_TYPE.REGION_AND_RACK_CONTROLLER))
    register_trigger(
        "maasserver_fabric",
        "fabric_machine_update_notify", "update")

    # Space node notifications
    register_procedure(
        SPACE_NODE_NOTIFY % (
            'space_machine_update_notify', 'NEW.id', NODE_TYPE.MACHINE,
            NODE_TYPE.RACK_CONTROLLER, NODE_TYPE.REGION_CONTROLLER,
            NODE_TYPE.REGION_AND_RACK_CONTROLLER))
    register_trigger(
        "maasserver_space",
        "space_machine_update_notify", "update")

    # VLAN node notifications
    register_procedure(
        VLAN_NODE_NOTIFY % (
            'vlan_machine_update_notify', 'NEW.id', NODE_TYPE.MACHINE,
            NODE_TYPE.RACK_CONTROLLER, NODE_TYPE.REGION_CONTROLLER,
            NODE_TYPE.REGION_AND_RACK_CONTROLLER))
    register_trigger(
        "maasserver_vlan",
        "vlan_machine_update_notify", "update")

    # IP address node notifications
    register_procedure(
        STATIC_IP_ADDRESS_NODE_NOTIFY % (
            'ipaddress_machine_update_notify', 'NEW.id', NODE_TYPE.MACHINE,
            NODE_TYPE.RACK_CONTROLLER, NODE_TYPE.REGION_CONTROLLER,
            NODE_TYPE.REGION_AND_RACK_CONTROLLER))
    register_trigger(
        "maasserver_staticipaddress",
        "ipaddress_machine_update_notify", "update")

    # IP address subnet notifications
    register_procedure(
        STATIC_IP_ADDRESS_SUBNET_NOTIFY % 'ipaddress_subnet_update_notify')
    register_trigger(
        "maasserver_staticipaddress",
        "ipaddress_subnet_update_notify", "update")

    # IP address domain notifications
    register_procedure(
        STATIC_IP_ADDRESS_DOMAIN_NOTIFY % (
            'ipaddress_domain_insert_notify', 'NEW.id'))
    register_procedure(
        STATIC_IP_ADDRESS_DOMAIN_UPDATE_NOTIFY %
        'ipaddress_domain_update_notify')
    register_procedure(
        STATIC_IP_ADDRESS_DOMAIN_NOTIFY % (
            'ipaddress_domain_delete_notify', 'OLD.id'))
    register_trigger(
        "maasserver_staticipaddress",
        "ipaddress_domain_insert_notify", "insert")
    register_trigger(
        "maasserver_staticipaddress",
        "ipaddress_domain_update_notify", "update")
    register_trigger(
        "maasserver_staticipaddress",
        "ipaddress_domain_delete_notify", "delete")

    # IP range subnet notifications
    register_procedure(
        IP_RANGE_SUBNET_INSERT_NOTIFY % 'iprange_subnet_insert_notify')
    register_procedure(
        IP_RANGE_SUBNET_UPDATE_NOTIFY % 'iprange_subnet_update_notify')
    register_procedure(
        IP_RANGE_SUBNET_DELETE_NOTIFY % 'iprange_subnet_delete_notify')
    register_trigger(
        "maasserver_iprange",
        "iprange_subnet_insert_notify", "insert")
    register_trigger(
        "maasserver_iprange",
        "iprange_subnet_update_notify", "update")
    register_trigger(
        "maasserver_iprange",
        "iprange_subnet_delete_notify", "delete")

    # DNSData table
    register_procedure(
        DNSDATA_DOMAIN_NOTIFY % (
            'dnsdata_domain_insert_notify', 'NEW.dnsresource_id'))
    register_procedure(
        DNSDATA_DOMAIN_NOTIFY % (
            'dnsdata_domain_update_notify',
            'OLD.dnsresource_id OR dnsresource.id = NEW.dnsresource_id'))
    register_procedure(
        DNSDATA_DOMAIN_NOTIFY % (
            'dnsdata_domain_delete_notify', 'OLD.dnsresource_id'))
    register_trigger(
        "maasserver_dnsdata",
        "dnsdata_domain_insert_notify", "insert")
    register_trigger(
        "maasserver_dnsdata",
        "dnsdata_domain_update_notify", "update")
    register_trigger(
        "maasserver_dnsdata",
        "dnsdata_domain_delete_notify", "delete")

    # DNSResource table
    register_procedure(
        DNSRESOURCE_DOMAIN_NOTIFY % (
            'dnsresource_domain_insert_notify', 'NEW'))
    register_procedure(
        DNSRESOURCE_DOMAIN_UPDATE_NOTIFY % 'dnsresource_domain_update_notify')
    register_procedure(
        DNSRESOURCE_DOMAIN_NOTIFY % (
            'dnsresource_domain_delete_notify', 'OLD'))
    register_trigger(
        "maasserver_dnsresource",
        "dnsresource_domain_insert_notify", "insert")
    register_trigger(
        "maasserver_dnsresource",
        "dnsresource_domain_update_notify", "update")
    register_trigger(
        "maasserver_dnsresource",
        "dnsresource_domain_delete_notify", "delete")

    # Domain table
    register_procedure(
        render_notification_procedure(
            'domain_create_notify', 'domain_create', 'NEW.id'))
    register_procedure(
        render_notification_procedure(
            'domain_update_notify', 'domain_update', 'NEW.id'))
    register_procedure(
        render_notification_procedure(
            'domain_delete_notify', 'domain_delete', 'OLD.id'))
    register_trigger(
        "maasserver_domain", "domain_create_notify", "insert")
    register_trigger(
        "maasserver_domain", "domain_update_notify", "update")
    register_trigger(
        "maasserver_domain", "domain_delete_notify", "delete")

    # MAC static ip address table, update to linked domain via dnsresource
    register_procedure(
        DNSRESOURCE_IP_ADDRESS_DOMAIN_NOTIFY % (
            'rrset_sipaddress_link_notify', 'NEW.dnsresource_id'))
    register_procedure(
        DNSRESOURCE_IP_ADDRESS_DOMAIN_NOTIFY % (
            'rrset_sipaddress_unlink_notify', 'OLD.dnsresource_id'))
    register_trigger(
        "maasserver_dnsresource_ip_addresses",
        "rrset_sipaddress_link_notify", "insert")
    register_trigger(
        "maasserver_dnsresource_ip_addresses",
        "rrset_sipaddress_unlink_notify", "delete")

    # Zone table
    register_procedure(
        render_notification_procedure(
            'zone_create_notify', 'zone_create', 'NEW.id'))
    register_procedure(
        render_notification_procedure(
            'zone_update_notify', 'zone_update', 'NEW.id'))
    register_procedure(
        render_notification_procedure(
            'zone_delete_notify', 'zone_delete', 'OLD.id'))
    register_trigger(
        "maasserver_zone", "zone_create_notify", "insert")
    register_trigger(
        "maasserver_zone", "zone_update_notify", "update")
    register_trigger(
        "maasserver_zone", "zone_delete_notify", "delete")

    # Service table
    register_procedure(
        render_notification_procedure(
            'service_create_notify', 'service_create', 'NEW.id'))
    register_procedure(
        render_notification_procedure(
            'service_update_notify', 'service_update', 'NEW.id'))
    register_procedure(
        render_notification_procedure(
            'service_delete_notify', 'service_delete', 'OLD.id'))
    register_trigger(
        "maasserver_service", "service_create_notify", "insert")
    register_trigger(
        "maasserver_service", "service_update_notify", "update")
    register_trigger(
        "maasserver_service", "service_delete_notify", "delete")

    # Tag table
    register_procedure(
        render_notification_procedure(
            'tag_create_notify', 'tag_create', 'NEW.id'))
    register_procedure(
        render_notification_procedure(
            'tag_update_notify', 'tag_update', 'NEW.id'))
    register_procedure(
        render_notification_procedure(
            'tag_delete_notify', 'tag_delete', 'OLD.id'))
    register_trigger(
        "maasserver_tag", "tag_create_notify", "insert")
    register_trigger(
        "maasserver_tag", "tag_update_notify", "update")
    register_trigger(
        "maasserver_tag", "tag_delete_notify", "delete")

    # Node tag link table
    register_procedure(
        NODE_TAG_NOTIFY % (
            'machine_device_tag_link_notify', 'NEW.node_id',
            NODE_TYPE.MACHINE, NODE_TYPE.RACK_CONTROLLER,
            NODE_TYPE.REGION_CONTROLLER, NODE_TYPE.REGION_AND_RACK_CONTROLLER))
    register_procedure(
        NODE_TAG_NOTIFY % (
            'machine_device_tag_unlink_notify', 'OLD.node_id',
            NODE_TYPE.MACHINE, NODE_TYPE.RACK_CONTROLLER,
            NODE_TYPE.REGION_CONTROLLER, NODE_TYPE.REGION_AND_RACK_CONTROLLER))
    register_trigger(
        "maasserver_node_tags", "machine_device_tag_link_notify", "insert")
    register_trigger(
        "maasserver_node_tags", "machine_device_tag_unlink_notify", "delete")

    # Tag table, update to linked nodes.
    register_procedure(TAG_NODES_NOTIFY % (NODE_TYPE.MACHINE,
                       NODE_TYPE.RACK_CONTROLLER, NODE_TYPE.REGION_CONTROLLER,
                       NODE_TYPE.REGION_AND_RACK_CONTROLLER))
    register_trigger(
        "maasserver_tag", "tag_update_machine_device_notify", "update")

    # User table
    register_procedure(
        render_notification_procedure(
            'user_create_notify', 'user_create', 'NEW.id'))
    register_procedure(
        render_notification_procedure(
            'user_update_notify', 'user_update', 'NEW.id'))
    register_procedure(
        render_notification_procedure(
            'user_delete_notify', 'user_delete', 'OLD.id'))
    register_trigger(
        "auth_user", "user_create_notify", "insert")
    register_trigger(
        "auth_user", "user_update_notify", "update")
    register_trigger(
        "auth_user", "user_delete_notify", "delete")

    # Events table
    register_procedure(
        render_notification_procedure(
            'event_create_notify', 'event_create', 'NEW.id'))
    register_trigger(
        "maasserver_event", "event_create_notify", "insert")

    # Events table, update to linked node.
    register_procedure(EVENT_NODE_NOTIFY % (
        NODE_TYPE.MACHINE, NODE_TYPE.RACK_CONTROLLER,
        NODE_TYPE.REGION_CONTROLLER, NODE_TYPE.REGION_AND_RACK_CONTROLLER))
    register_trigger(
        "maasserver_event", "event_create_machine_device_notify", "insert")

    # MAC static ip address table, update to linked node.
    register_procedure(
        INTERFACE_IP_ADDRESS_NODE_NOTIFY % (
            'nd_sipaddress_link_notify', 'NEW.interface_id',
            NODE_TYPE.MACHINE, NODE_TYPE.RACK_CONTROLLER,
            NODE_TYPE.REGION_CONTROLLER, NODE_TYPE.REGION_AND_RACK_CONTROLLER))
    register_procedure(
        INTERFACE_IP_ADDRESS_NODE_NOTIFY % (
            'nd_sipaddress_unlink_notify', 'OLD.interface_id',
            NODE_TYPE.MACHINE, NODE_TYPE.RACK_CONTROLLER,
            NODE_TYPE.REGION_CONTROLLER, NODE_TYPE.REGION_AND_RACK_CONTROLLER))
    register_trigger(
        "maasserver_interface_ip_addresses",
        "nd_sipaddress_link_notify", "insert")
    register_trigger(
        "maasserver_interface_ip_addresses",
        "nd_sipaddress_unlink_notify", "delete")

    # MAC static ip address table, update to linked domain via node.
    register_procedure(
        INTERFACE_IP_ADDRESS_DOMAIN_NOTIFY % (
            'nd_sipaddress_dns_link_notify', 'NEW.interface_id'))
    register_procedure(
        INTERFACE_IP_ADDRESS_DOMAIN_NOTIFY % (
            'nd_sipaddress_dns_unlink_notify', 'OLD.interface_id'))
    register_trigger(
        "maasserver_interface_ip_addresses",
        "nd_sipaddress_dns_link_notify", "insert")
    register_trigger(
        "maasserver_interface_ip_addresses",
        "nd_sipaddress_dns_unlink_notify", "delete")

    # Node result table, update to linked node.
    register_procedure(
        render_node_related_notification_procedure(
            'nd_noderesult_link_notify', 'NEW.node_id'))
    register_procedure(
        render_node_related_notification_procedure(
            'nd_noderesult_unlink_notify', 'OLD.node_id'))
    register_trigger(
        "metadataserver_noderesult",
        "nd_noderesult_link_notify", "insert")
    register_trigger(
        "metadataserver_noderesult",
        "nd_noderesult_unlink_notify", "delete")

    # Interface address table, update to linked node.
    register_procedure(
        render_node_related_notification_procedure(
            'nd_interface_link_notify', 'NEW.node_id'))
    register_procedure(
        render_node_related_notification_procedure(
            'nd_interface_unlink_notify', 'OLD.node_id'))
    register_procedure(INTERFACE_UPDATE_NODE_NOTIFY % (
        NODE_TYPE.MACHINE,
        NODE_TYPE.RACK_CONTROLLER,
        NODE_TYPE.REGION_CONTROLLER,
        NODE_TYPE.REGION_AND_RACK_CONTROLLER,
        NODE_TYPE.MACHINE,
        NODE_TYPE.RACK_CONTROLLER,
        NODE_TYPE.REGION_CONTROLLER,
        NODE_TYPE.REGION_AND_RACK_CONTROLLER))
    register_trigger(
        "maasserver_interface",
        "nd_interface_link_notify", "insert")
    register_trigger(
        "maasserver_interface",
        "nd_interface_unlink_notify", "delete")
    register_trigger(
        "maasserver_interface",
        "nd_interface_update_notify", "update")

    # Block device table, update to linked node.
    register_procedure(
        render_node_related_notification_procedure(
            'nd_blockdevice_link_notify', 'NEW.node_id'))
    register_procedure(
        render_node_related_notification_procedure(
            'nd_blockdevice_update_notify', 'NEW.node_id'))
    register_procedure(
        render_node_related_notification_procedure(
            'nd_blockdevice_unlink_notify', 'OLD.node_id'))
    register_procedure(
        PHYSICAL_OR_VIRTUAL_BLOCK_DEVICE_NODE_NOTIFY % (
            'nd_physblockdevice_update_notify', 'NEW.blockdevice_ptr_id',
            NODE_TYPE.MACHINE))
    register_procedure(
        PHYSICAL_OR_VIRTUAL_BLOCK_DEVICE_NODE_NOTIFY % (
            'nd_virtblockdevice_update_notify', 'NEW.blockdevice_ptr_id',
            NODE_TYPE.MACHINE))
    register_trigger(
        "maasserver_blockdevice",
        "nd_blockdevice_link_notify", "insert")
    register_trigger(
        "maasserver_blockdevice",
        "nd_blockdevice_update_notify", "update")
    register_trigger(
        "maasserver_blockdevice",
        "nd_blockdevice_unlink_notify", "delete")
    register_trigger(
        "maasserver_physicalblockdevice",
        "nd_physblockdevice_update_notify", "update")
    register_trigger(
        "maasserver_virtualblockdevice",
        "nd_virtblockdevice_update_notify", "update")

    # Partition table, update to linked user.
    register_procedure(
        PARTITIONTABLE_NODE_NOTIFY % (
            'nd_partitiontable_link_notify', 'NEW.block_device_id',
            NODE_TYPE.MACHINE))
    register_procedure(
        PARTITIONTABLE_NODE_NOTIFY % (
            'nd_partitiontable_update_notify',
            'NEW.block_device_id',
            NODE_TYPE.MACHINE))
    register_procedure(
        PARTITIONTABLE_NODE_NOTIFY % (
            'nd_partitiontable_unlink_notify', 'OLD.block_device_id',
            NODE_TYPE.MACHINE))
    register_trigger(
        "maasserver_partitiontable",
        "nd_partitiontable_link_notify", "insert")
    register_trigger(
        "maasserver_partitiontable",
        "nd_partitiontable_update_notify", "update")
    register_trigger(
        "maasserver_partitiontable",
        "nd_partitiontable_unlink_notify", "delete")

    # Partition, update to linked user.
    register_procedure(
        PARTITION_NODE_NOTIFY % (
            'nd_partition_link_notify', 'NEW.partition_table_id',
            NODE_TYPE.MACHINE))
    register_procedure(
        PARTITION_NODE_NOTIFY % (
            'nd_partition_update_notify', 'NEW.partition_table_id',
            NODE_TYPE.MACHINE))
    register_procedure(
        PARTITION_NODE_NOTIFY % (
            'nd_partition_unlink_notify', 'OLD.partition_table_id',
            NODE_TYPE.MACHINE))
    register_trigger(
        "maasserver_partition",
        "nd_partition_link_notify", "insert")
    register_trigger(
        "maasserver_partition",
        "nd_partition_update_notify", "update")
    register_trigger(
        "maasserver_partition",
        "nd_partition_unlink_notify", "delete")

    # Filesystem, update to linked user.
    register_procedure(
        FILESYSTEM_NODE_NOTIFY.format(
            'nd_filesystem_link_notify', 'NEW.block_device_id',
            'NEW.partition_id', 'NEW.node_id', NODE_TYPE.MACHINE))
    register_procedure(
        FILESYSTEM_NODE_NOTIFY.format(
            'nd_filesystem_update_notify', 'NEW.block_device_id',
            'NEW.partition_id', 'NEW.node_id', NODE_TYPE.MACHINE))
    register_procedure(
        FILESYSTEM_NODE_NOTIFY.format(
            'nd_filesystem_unlink_notify', 'OLD.block_device_id',
            'OLD.partition_id', 'OLD.node_id', NODE_TYPE.MACHINE))
    register_trigger(
        "maasserver_filesystem",
        "nd_filesystem_link_notify", "insert")
    register_trigger(
        "maasserver_filesystem",
        "nd_filesystem_update_notify", "update")
    register_trigger(
        "maasserver_filesystem",
        "nd_filesystem_unlink_notify", "delete")

    # Filesystemgroup, update to linked user.
    register_procedure(
        FILESYSTEMGROUP_NODE_NOTIFY % (
            'nd_filesystemgroup_link_notify', 'NEW.id', 'NEW.cache_set_id',
            NODE_TYPE.MACHINE))
    register_procedure(
        FILESYSTEMGROUP_NODE_NOTIFY % (
            'nd_filesystemgroup_update_notify', 'NEW.id', 'NEW.cache_set_id',
            NODE_TYPE.MACHINE))
    register_procedure(
        FILESYSTEMGROUP_NODE_NOTIFY % (
            'nd_filesystemgroup_unlink_notify', 'OLD.id', 'OLD.cache_set_id',
            NODE_TYPE.MACHINE))
    register_trigger(
        "maasserver_filesystemgroup",
        "nd_filesystemgroup_link_notify", "insert")
    register_trigger(
        "maasserver_filesystemgroup",
        "nd_filesystemgroup_update_notify", "update")
    register_trigger(
        "maasserver_filesystemgroup",
        "nd_filesystemgroup_unlink_notify", "delete")

    # Cacheset, update to linked user.
    register_procedure(
        CACHESET_NODE_NOTIFY % (
            'nd_cacheset_link_notify', 'NEW.id', NODE_TYPE.MACHINE))
    register_procedure(
        CACHESET_NODE_NOTIFY % (
            'nd_cacheset_update_notify', 'NEW.id', NODE_TYPE.MACHINE))
    register_procedure(
        CACHESET_NODE_NOTIFY % (
            'nd_cacheset_unlink_notify', 'OLD.id', NODE_TYPE.MACHINE))
    register_trigger(
        "maasserver_cacheset",
        "nd_cacheset_link_notify", "insert")
    register_trigger(
        "maasserver_cacheset",
        "nd_cacheset_update_notify", "update")
    register_trigger(
        "maasserver_cacheset",
        "nd_cacheset_unlink_notify", "delete")

    # SSH key table, update to linked user.
    register_procedure(
        render_notification_procedure(
            'user_sshkey_link_notify', 'user_update', 'NEW.user_id'))
    register_procedure(
        render_notification_procedure(
            'user_sshkey_unlink_notify', 'user_update', 'OLD.user_id'))
    register_trigger(
        "maasserver_sshkey", "user_sshkey_link_notify", "insert")
    register_trigger(
        "maasserver_sshkey", "user_sshkey_unlink_notify", "delete")

    # SSH key table.
    register_procedure(
        render_notification_procedure(
            'sshkey_create_notify', 'sshkey_create', 'NEW.id'))
    register_procedure(
        render_notification_procedure(
            'sshkey_update_notify', 'sshkey_update', 'NEW.id'))
    register_procedure(
        render_notification_procedure(
            'sshkey_delete_notify', 'sshkey_delete', 'OLD.id'))
    register_trigger(
        "maasserver_sshkey", "sshkey_create_notify", "insert")
    register_trigger(
        "maasserver_sshkey", "sshkey_update_notify", "update")
    register_trigger(
        "maasserver_sshkey", "sshkey_delete_notify", "delete")

    # SSL key table, update to linked user.
    register_procedure(
        render_notification_procedure(
            'user_sslkey_link_notify', 'user_update', 'NEW.user_id'))
    register_procedure(
        render_notification_procedure(
            'user_sslkey_unlink_notify', 'user_update', 'OLD.user_id'))
    register_trigger(
        "maasserver_sslkey", "user_sslkey_link_notify", "insert")
    register_trigger(
        "maasserver_sslkey", "user_sslkey_unlink_notify", "delete")

    # DHCPSnippet table
    register_procedure(
        render_notification_procedure(
            'dhcpsnippet_create_notify', 'dhcpsnippet_create', 'NEW.id'))
    register_procedure(
        render_notification_procedure(
            'dhcpsnippet_update_notify', 'dhcpsnippet_update', 'NEW.id'))
    register_procedure(
        render_notification_procedure(
            'dhcpsnippet_delete_notify', 'dhcpsnippet_delete', 'OLD.id'))
    register_trigger(
        "maasserver_dhcpsnippet", "dhcpsnippet_create_notify", "insert")
    register_trigger(
        "maasserver_dhcpsnippet", "dhcpsnippet_update_notify", "update")
    register_trigger(
        "maasserver_dhcpsnippet", "dhcpsnippet_delete_notify", "delete")

    # PackageRepository table
    register_procedure(
        render_notification_procedure(
            'packagerepository_create_notify', 'packagerepository_create',
            'NEW.id'))
    register_procedure(
        render_notification_procedure(
            'packagerepository_update_notify', 'packagerepository_update',
            'NEW.id'))
    register_procedure(
        render_notification_procedure(
            'packagerepository_delete_notify', 'packagerepository_delete',
            'OLD.id'))
    register_trigger(
        "maasserver_packagerepository", "packagerepository_create_notify",
        "insert")
    register_trigger(
        "maasserver_packagerepository", "packagerepository_update_notify",
        "update")
    register_trigger(
        "maasserver_packagerepository", "packagerepository_delete_notify",
        "delete")

    register_procedure(node_type_change())
    register_trigger(
        "maasserver_node", "node_type_change_notify", "update")