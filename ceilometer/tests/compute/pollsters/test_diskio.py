#
# Copyright 2012 eNovance <licensing@enovance.com>
# Copyright 2012 Red Hat, Inc
# Copyright 2014 Cisco Systems, Inc
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
import mock
from oslotest import mockpatch

from ceilometer.agent import manager
from ceilometer.compute.pollsters import disk
from ceilometer.compute.virt import inspector as virt_inspector
import ceilometer.tests.base as base


class TestBaseDiskIO(base.BaseTestCase):

    TYPE = 'cumulative'

    def setUp(self):
        super(TestBaseDiskIO, self).setUp()

        self.inspector = mock.Mock()
        self.instance = self._get_fake_instances()
        patch_virt = mockpatch.Patch(
            'ceilometer.compute.virt.inspector.get_hypervisor_inspector',
            new=mock.Mock(return_value=self.inspector))
        self.useFixture(patch_virt)

        # as we're having lazy hypervisor inspector singleton object in the
        # base compute pollster class, that leads to the fact that we
        # need to mock all this class property to avoid context sharing between
        # the tests
        patch_inspector = mockpatch.Patch(
            'ceilometer.compute.pollsters.BaseComputePollster.inspector',
            self.inspector)
        self.useFixture(patch_inspector)

    @staticmethod
    def _get_fake_instances():
        instances = []
        for i in [1, 2]:
            instance = mock.MagicMock()
            instance.name = 'instance-%s' % i
            setattr(instance, 'OS-EXT-SRV-ATTR:instance_name',
                    instance.name)
            instance.id = i
            instance.flavor = {'name': 'm1.small', 'id': 2, 'vcpus': 1,
                               'ram': 512, 'disk': 20, 'ephemeral': 0}
            instance.status = 'active'
            instances.append(instance)
        return instances

    @mock.patch('ceilometer.pipeline.setup_pipeline', mock.MagicMock())
    def _check_get_samples(self, factory, name, expected_count=2):
        pollster = factory()

        mgr = manager.AgentManager()
        cache = {}
        samples = list(pollster.get_samples(mgr, cache, self.instance))
        self.assertIsNotEmpty(samples)
        cache_key = getattr(pollster, self.CACHE_KEY)
        self.assertIn(cache_key, cache)
        for instance in self.instance:
            self.assertIn(instance.id, cache[cache_key])
        self.assertEqual(set([name]), set([s.name for s in samples]))

        match = [s for s in samples if s.name == name]
        self.assertEqual(len(match), expected_count,
                         'missing counter %s' % name)
        return match

    def _check_aggregate_samples(self, factory, name,
                                 expected_volume,
                                 expected_device=None):
        match = self._check_get_samples(factory, name)
        self.assertEqual(expected_volume, match[0].volume)
        self.assertEqual(self.TYPE, match[0].type)
        if expected_device is not None:
            self.assertEqual(set(expected_device),
                             set(match[0].resource_metadata.get('device')))
        instances = [i.id for i in self.instance]
        for m in match:
            self.assertIn(m.resource_id, instances)

    def _check_per_device_samples(self, factory, name,
                                  expected_volume,
                                  expected_device=None):
        match = self._check_get_samples(factory, name, expected_count=4)
        match_dict = {}
        for m in match:
            match_dict[m.resource_id] = m
        for instance in self.instance:
            key = "%s-%s" % (instance.id, expected_device)
            self.assertEqual(expected_volume,
                             match_dict[key].volume)
            self.assertEqual(self.TYPE, match_dict[key].type)

            self.assertEqual(key, match_dict[key].resource_id)


class TestDiskPollsters(TestBaseDiskIO):

    DISKS = [
        (virt_inspector.Disk(device='vda1'),
         virt_inspector.DiskStats(read_bytes=1L, read_requests=2L,
                                  write_bytes=3L, write_requests=4L,
                                  errors=-1L)),
        (virt_inspector.Disk(device='vda2'),
         virt_inspector.DiskStats(read_bytes=2L, read_requests=3L,
                                  write_bytes=5L, write_requests=7L,
                                  errors=-1L)),
    ]
    CACHE_KEY = "CACHE_KEY_DISK"

    def setUp(self):
        super(TestDiskPollsters, self).setUp()
        self.inspector.inspect_disks = mock.Mock(return_value=self.DISKS)

    def test_disk_read_requests(self):
        self._check_aggregate_samples(disk.ReadRequestsPollster,
                                      'disk.read.requests', 5L,
                                      expected_device=['vda1', 'vda2'])

    def test_disk_read_bytes(self):
        self._check_aggregate_samples(disk.ReadBytesPollster,
                                      'disk.read.bytes', 3L,
                                      expected_device=['vda1', 'vda2'])

    def test_disk_write_requests(self):
        self._check_aggregate_samples(disk.WriteRequestsPollster,
                                      'disk.write.requests', 11L,
                                      expected_device=['vda1', 'vda2'])

    def test_disk_write_bytes(self):
        self._check_aggregate_samples(disk.WriteBytesPollster,
                                      'disk.write.bytes', 8L,
                                      expected_device=['vda1', 'vda2'])

    def test_per_disk_read_requests(self):
        self._check_per_device_samples(disk.PerDeviceReadRequestsPollster,
                                       'disk.device.read.requests', 2L,
                                       'vda1')
        self._check_per_device_samples(disk.PerDeviceReadRequestsPollster,
                                       'disk.device.read.requests', 3L,
                                       'vda2')

    def test_per_disk_write_requests(self):
        self._check_per_device_samples(disk.PerDeviceWriteRequestsPollster,
                                       'disk.device.write.requests', 4L,
                                       'vda1')
        self._check_per_device_samples(disk.PerDeviceWriteRequestsPollster,
                                       'disk.device.write.requests', 7L,
                                       'vda2')

    def test_per_disk_read_bytes(self):
        self._check_per_device_samples(disk.PerDeviceReadBytesPollster,
                                       'disk.device.read.bytes', 1L,
                                       'vda1')
        self._check_per_device_samples(disk.PerDeviceReadBytesPollster,
                                       'disk.device.read.bytes', 2L,
                                       'vda2')

    def test_per_disk_write_bytes(self):
        self._check_per_device_samples(disk.PerDeviceWriteBytesPollster,
                                       'disk.device.write.bytes', 3L,
                                       'vda1')
        self._check_per_device_samples(disk.PerDeviceWriteBytesPollster,
                                       'disk.device.write.bytes', 5L,
                                       'vda2')


class TestDiskRatePollsters(TestBaseDiskIO):

    DISKS = [
        (virt_inspector.Disk(device='disk1'),
         virt_inspector.DiskRateStats(1024, 300, 5120, 700)),

        (virt_inspector.Disk(device='disk2'),
         virt_inspector.DiskRateStats(2048, 400, 6144, 800))
    ]
    TYPE = 'gauge'
    CACHE_KEY = "CACHE_KEY_DISK_RATE"

    def setUp(self):
        super(TestDiskRatePollsters, self).setUp()
        self.inspector.inspect_disk_rates = mock.Mock(return_value=self.DISKS)

    def test_disk_read_bytes_rate(self):
        self._check_aggregate_samples(disk.ReadBytesRatePollster,
                                      'disk.read.bytes.rate', 3072L,
                                      expected_device=['disk1', 'disk2'])

    def test_disk_read_requests_rate(self):
        self._check_aggregate_samples(disk.ReadRequestsRatePollster,
                                      'disk.read.requests.rate', 700L,
                                      expected_device=['disk1', 'disk2'])

    def test_disk_write_bytes_rate(self):
        self._check_aggregate_samples(disk.WriteBytesRatePollster,
                                      'disk.write.bytes.rate', 11264L,
                                      expected_device=['disk1', 'disk2'])

    def test_disk_write_requests_rate(self):
        self._check_aggregate_samples(disk.WriteRequestsRatePollster,
                                      'disk.write.requests.rate', 1500L,
                                      expected_device=['disk1', 'disk2'])

    def test_per_disk_read_bytes_rate(self):
        self._check_per_device_samples(disk.PerDeviceReadBytesRatePollster,
                                       'disk.device.read.bytes.rate',
                                       1024L, 'disk1')
        self._check_per_device_samples(disk.PerDeviceReadBytesRatePollster,
                                       'disk.device.read.bytes.rate',
                                       2048L, 'disk2')

    def test_per_disk_read_requests_rate(self):
        self._check_per_device_samples(disk.PerDeviceReadRequestsRatePollster,
                                       'disk.device.read.requests.rate',
                                       300L, 'disk1')
        self._check_per_device_samples(disk.PerDeviceReadRequestsRatePollster,
                                       'disk.device.read.requests.rate',
                                       400L, 'disk2')

    def test_per_disk_write_bytes_rate(self):
        self._check_per_device_samples(disk.PerDeviceWriteBytesRatePollster,
                                       'disk.device.write.bytes.rate',
                                       5120L, 'disk1')
        self._check_per_device_samples(disk.PerDeviceWriteBytesRatePollster,
                                       'disk.device.write.bytes.rate', 6144L,
                                       'disk2')

    def test_per_disk_write_requests_rate(self):
        self._check_per_device_samples(disk.PerDeviceWriteRequestsRatePollster,
                                       'disk.device.write.requests.rate', 700L,
                                       'disk1')
        self._check_per_device_samples(disk.PerDeviceWriteRequestsRatePollster,
                                       'disk.device.write.requests.rate', 800L,
                                       'disk2')


class TestDiskLatencyPollsters(TestBaseDiskIO):

    DISKS = [
        (virt_inspector.Disk(device='disk1'),
         virt_inspector.DiskLatencyStats(1000)),

        (virt_inspector.Disk(device='disk2'),
         virt_inspector.DiskLatencyStats(2000))
    ]
    TYPE = 'gauge'
    CACHE_KEY = "CACHE_KEY_DISK_LATENCY"

    def setUp(self):
        super(TestDiskLatencyPollsters, self).setUp()
        self.inspector.inspect_disk_latency = mock.Mock(
            return_value=self.DISKS)

    def test_disk_latency(self):
        self._check_aggregate_samples(disk.DiskLatencyPollster,
                                      'disk.latency', 3)

    def test_per_device_latency(self):
        self._check_per_device_samples(disk.PerDeviceDiskLatencyPollster,
                                       'disk.device.latency', 1, 'disk1')

        self._check_per_device_samples(disk.PerDeviceDiskLatencyPollster,
                                       'disk.device.latency', 2, 'disk2')


class TestDiskIOPSPollsters(TestBaseDiskIO):

    DISKS = [
        (virt_inspector.Disk(device='disk1'),
         virt_inspector.DiskIOPSStats(10)),

        (virt_inspector.Disk(device='disk2'),
         virt_inspector.DiskIOPSStats(20)),
    ]
    TYPE = 'gauge'
    CACHE_KEY = "CACHE_KEY_DISK_IOPS"

    def setUp(self):
        super(TestDiskIOPSPollsters, self).setUp()
        self.inspector.inspect_disk_iops = mock.Mock(return_value=self.DISKS)

    def test_disk_iops(self):
        self._check_aggregate_samples(disk.DiskIOPSPollster,
                                      'disk.iops', 30L)

    def test_per_device_iops(self):
        self._check_per_device_samples(disk.PerDeviceDiskIOPSPollster,
                                       'disk.device.iops', 10L, 'disk1')

        self._check_per_device_samples(disk.PerDeviceDiskIOPSPollster,
                                       'disk.device.iops', 20L, 'disk2')


class TestDiskInfoPollsters(TestBaseDiskIO):

    DISKS = [
        (virt_inspector.Disk(device='vda1'),
         virt_inspector.DiskInfo(capacity=3L, allocation=2L, physical=1L)),
        (virt_inspector.Disk(device='vda2'),
         virt_inspector.DiskInfo(capacity=4L, allocation=3L, physical=2L)),
    ]
    TYPE = 'gauge'
    CACHE_KEY = "CACHE_KEY_DISK_INFO"

    def setUp(self):
        super(TestDiskInfoPollsters, self).setUp()
        self.inspector.inspect_disk_info = mock.Mock(return_value=self.DISKS)

    def test_disk_capacity(self):
        self._check_aggregate_samples(disk.CapacityPollster,
                                      'disk.capacity', 7L,
                                      expected_device=['vda1', 'vda2'])

    def test_disk_allocation(self):
        self._check_aggregate_samples(disk.AllocationPollster,
                                      'disk.allocation', 5L,
                                      expected_device=['vda1', 'vda2'])

    def test_disk_physical(self):
        self._check_aggregate_samples(disk.PhysicalPollster,
                                      'disk.usage', 3L,
                                      expected_device=['vda1', 'vda2'])

    def test_per_disk_capacity(self):
        self._check_per_device_samples(disk.PerDeviceCapacityPollster,
                                       'disk.device.capacity', 3L,
                                       'vda1')
        self._check_per_device_samples(disk.PerDeviceCapacityPollster,
                                       'disk.device.capacity', 4L,
                                       'vda2')

    def test_per_disk_allocation(self):
        self._check_per_device_samples(disk.PerDeviceAllocationPollster,
                                       'disk.device.allocation', 2L,
                                       'vda1')
        self._check_per_device_samples(disk.PerDeviceAllocationPollster,
                                       'disk.device.allocation', 3L,
                                       'vda2')

    def test_per_disk_physical(self):
        self._check_per_device_samples(disk.PerDevicePhysicalPollster,
                                       'disk.device.usage', 1L,
                                       'vda1')
        self._check_per_device_samples(disk.PerDevicePhysicalPollster,
                                       'disk.device.usage', 2L,
                                       'vda2')
