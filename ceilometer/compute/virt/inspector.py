#
# Copyright 2012 Red Hat, Inc
#
# Author: Eoghan Glynn <eglynn@redhat.com>
#         Doug Hellmann <doug.hellmann@dreamhost.com>
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.
"""Inspector abstraction for read-only access to hypervisors."""

import collections

from oslo.config import cfg
from stevedore import driver

import ceilometer
from ceilometer.openstack.common.gettextutils import _
from ceilometer.openstack.common import log


OPTS = [
    cfg.StrOpt('hypervisor_inspector',
               default='libvirt',
               help='Inspector to use for inspecting the hypervisor layer.'),
]

cfg.CONF.register_opts(OPTS)


LOG = log.getLogger(__name__)

# Named tuple representing instances.
#
# name: the name of the instance
# uuid: the UUID associated with the instance
#
Instance = collections.namedtuple('Instance', ['name', 'UUID'])


# Named tuple representing CPU statistics.
#
# number: number of CPUs
# time: cumulative CPU time
#
CPUStats = collections.namedtuple('CPUStats', ['number', 'time'])

# Named tuple representing CPU Utilization statistics.
#
# util: CPU utilization in percentage
#
CPUUtilStats = collections.namedtuple('CPUUtilStats', ['util'])

# Named tuple representing Memory usage statistics.
#
# usage: Amount of memory used
#
MemoryUsageStats = collections.namedtuple('MemoryUsageStats', ['usage'])


# Named tuple representing vNICs.
#
# name: the name of the vNIC
# mac: the MAC address
# fref: the filter ref
# parameters: miscellaneous parameters
#
Interface = collections.namedtuple('Interface', ['name', 'mac',
                                                 'fref', 'parameters'])


# Named tuple representing vNIC statistics.
#
# rx_bytes: number of received bytes
# rx_packets: number of received packets
# tx_bytes: number of transmitted bytes
# tx_packets: number of transmitted packets
#
InterfaceStats = collections.namedtuple('InterfaceStats',
                                        ['rx_bytes', 'rx_packets',
                                         'tx_bytes', 'tx_packets'])


# Named tuple representing vNIC rate statistics.
#
# rx_bytes_rate: rate of received bytes
# tx_bytes_rate: rate of transmitted bytes
#
InterfaceRateStats = collections.namedtuple('InterfaceRateStats',
                                            ['rx_bytes_rate', 'tx_bytes_rate'])


# Named tuple representing disks.
#
# device: the device name for the disk
#
Disk = collections.namedtuple('Disk', ['device'])


# Named tuple representing disk statistics.
#
# read_bytes: number of bytes read
# read_requests: number of read operations
# write_bytes: number of bytes written
# write_requests: number of write operations
# errors: number of errors
#
DiskStats = collections.namedtuple('DiskStats',
                                   ['read_bytes', 'read_requests',
                                    'write_bytes', 'write_requests',
                                    'errors'])

# Named tuple representing disk rate statistics.
#
# read_bytes_rate: number of bytes read per second
# read_requests_rate: number of read operations per second
# write_bytes_rate: number of bytes written per second
# write_requests_rate: number of write operations per second
#
DiskRateStats = collections.namedtuple('DiskRateStats',
                                       ['read_bytes_rate',
                                        'read_requests_rate',
                                        'write_bytes_rate',
                                        'write_requests_rate'])


# Exception types
#
class InspectorException(Exception):
    def __init__(self, message=None):
        super(InspectorException, self).__init__(message)


class InstanceNotFoundException(InspectorException):
    pass


# Main virt inspector abstraction layering over the hypervisor API.
#
class Inspector(object):

    def inspect_instances(self):
        """List the instances on the current host."""
        raise ceilometer.NotImplementedError

    def inspect_cpus(self, instance_name):
        """Inspect the CPU statistics for an instance.

        :param instance_name: the name of the target instance
        :return: the number of CPUs and cumulative CPU time
        """
        raise ceilometer.NotImplementedError

    def inspect_cpu_util(self, instance, duration=None):
        """Inspect the CPU Utilization (%) for an instance.

        :param instance: the target instance
        :param duration: the last 'n' seconds, over which the value should be
               inspected
        :return: the percentage of CPU utilization
        """
        raise ceilometer.NotImplementedError

    def inspect_vnics(self, instance_name):
        """Inspect the vNIC statistics for an instance.

        :param instance_name: the name of the target instance
        :return: for each vNIC, the number of bytes & packets
                 received and transmitted
        """
        raise ceilometer.NotImplementedError

    def inspect_vnic_rates(self, instance, duration=None):
        """Inspect the vNIC rate statistics for an instance.

        :param instance: the target instance
        :param duration: the last 'n' seconds, over which the value should be
               inspected
        :return: for each vNIC, the rate of bytes & packets
                 received and transmitted
        """
        raise ceilometer.NotImplementedError

    def inspect_disks(self, instance_name):
        """Inspect the disk statistics for an instance.

        :param instance_name: the name of the target instance
        :return: for each disk, the number of bytes & operations
                 read and written, and the error count
        """
        raise ceilometer.NotImplementedError

    def inspect_memory_usage(self, instance, duration=None):
        """Inspect the memory usage statistics for an instance.

        :param instance: the target instance
        :param duration: the last 'n' seconds, over which the value should be
               inspected
        :return: the amount of memory used
        """
        raise ceilometer.NotImplementedError

    def inspect_disk_rates(self, instance, duration=None):
        """Inspect the disk statistics as rates for an instance.

        :param instance: the target instance
        :param duration: the last 'n' seconds, over which the value should be
               inspected
        :return: for each disk, the number of bytes & operations
                 read and written per second, with the error count
        """
        raise ceilometer.NotImplementedError


def get_hypervisor_inspector():
    try:
        namespace = 'ceilometer.compute.virt'
        mgr = driver.DriverManager(namespace,
                                   cfg.CONF.hypervisor_inspector,
                                   invoke_on_load=True)
        return mgr.driver
    except ImportError as e:
        LOG.error(_("Unable to load the hypervisor inspector: %s") % e)
        return Inspector()
