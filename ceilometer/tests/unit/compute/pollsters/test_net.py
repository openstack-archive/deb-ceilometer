#
# Copyright 2012 eNovance <licensing@enovance.com>
# Copyright 2012 Red Hat, Inc
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

from ceilometer.agent import manager
from ceilometer.compute.pollsters import net
from ceilometer.compute.virt import inspector as virt_inspector
from ceilometer import sample
from ceilometer.tests.unit.compute.pollsters import base


class FauxInstance(object):

    def __init__(self, **kwargs):
        for name, value in kwargs.items():
            setattr(self, name, value)

    def __getitem__(self, key):
        return getattr(self, key)

    def get(self, key, default):
        return getattr(self, key, default)


class TestNetPollster(base.TestPollsterBase):

    def setUp(self):
        super(TestNetPollster, self).setUp()
        self.vnic0 = virt_inspector.Interface(
            name='vnet0',
            fref='fa163e71ec6e',
            mac='fa:16:3e:71:ec:6d',
            parameters=dict(ip='10.0.0.2',
                            projmask='255.255.255.0',
                            projnet='proj1',
                            dhcp_server='10.0.0.1'))
        stats0 = virt_inspector.InterfaceStats(rx_bytes=1, rx_packets=2,
                                               tx_bytes=3, tx_packets=4)
        self.vnic1 = virt_inspector.Interface(
            name='vnet1',
            fref='fa163e71ec6f',
            mac='fa:16:3e:71:ec:6e',
            parameters=dict(ip='192.168.0.3',
                            projmask='255.255.255.0',
                            projnet='proj2',
                            dhcp_server='10.0.0.2'))
        stats1 = virt_inspector.InterfaceStats(rx_bytes=5, rx_packets=6,
                                               tx_bytes=7, tx_packets=8)
        self.vnic2 = virt_inspector.Interface(
            name='vnet2',
            fref=None,
            mac='fa:18:4e:72:fc:7e',
            parameters=dict(ip='192.168.0.4',
                            projmask='255.255.255.0',
                            projnet='proj3',
                            dhcp_server='10.0.0.3'))
        stats2 = virt_inspector.InterfaceStats(rx_bytes=9, rx_packets=10,
                                               tx_bytes=11, tx_packets=12)

        vnics = [
            (self.vnic0, stats0),
            (self.vnic1, stats1),
            (self.vnic2, stats2),
        ]
        self.inspector.inspect_vnics = mock.Mock(return_value=vnics)

        self.INSTANCE_PROPERTIES = {'name': 'display name',
                                    'OS-EXT-SRV-ATTR:instance_name':
                                    'instance-000001',
                                    'OS-EXT-AZ:availability_zone': 'foo-zone',
                                    'reservation_id': 'reservation id',
                                    'id': 'instance id',
                                    'user_id': 'user id',
                                    'tenant_id': 'tenant id',
                                    'architecture': 'x86_64',
                                    'kernel_id': 'kernel id',
                                    'os_type': 'linux',
                                    'ramdisk_id': 'ramdisk id',
                                    'status': 'active',
                                    'ephemeral_gb': 0,
                                    'root_gb': 20,
                                    'disk_gb': 20,
                                    'image': {'id': 1,
                                              'links': [{"rel": "bookmark",
                                                         'href': 2}]},
                                    'hostId': '1234-5678',
                                    'flavor': {'id': 1,
                                               'disk': 20,
                                               'ram': 512,
                                               'vcpus': 2,
                                               'ephemeral': 0},
                                    'metadata': {'metering.autoscale.group':
                                                 'X' * 512,
                                                 'metering.ephemeral_gb': 42}}

        self.faux_instance = FauxInstance(**self.INSTANCE_PROPERTIES)

    @mock.patch('ceilometer.pipeline.setup_pipeline', mock.MagicMock())
    def _check_get_samples(self, factory, expected):
        mgr = manager.AgentManager()
        pollster = factory()
        samples = list(pollster.get_samples(mgr, {}, [self.instance]))
        self.assertEqual(3, len(samples))  # one for each nic
        self.assertEqual(set([samples[0].name]),
                         set([s.name for s in samples]))

        def _verify_vnic_metering(ip, expected_volume, expected_rid):
            match = [s for s in samples
                     if s.resource_metadata['parameters']['ip'] == ip
                     ]
            self.assertEqual(len(match), 1, 'missing ip %s' % ip)
            self.assertEqual(expected_volume, match[0].volume)
            self.assertEqual('cumulative', match[0].type)
            self.assertEqual(expected_rid, match[0].resource_id)

        for ip, volume, rid in expected:
            _verify_vnic_metering(ip, volume, rid)

    def test_incoming_bytes(self):
        instance_name_id = "%s-%s" % (self.instance.name, self.instance.id)
        self._check_get_samples(
            net.IncomingBytesPollster,
            [('10.0.0.2', 1, self.vnic0.fref),
             ('192.168.0.3', 5, self.vnic1.fref),
             ('192.168.0.4', 9,
              "%s-%s" % (instance_name_id, self.vnic2.name)),
             ],
        )

    def test_outgoing_bytes(self):
        instance_name_id = "%s-%s" % (self.instance.name, self.instance.id)
        self._check_get_samples(
            net.OutgoingBytesPollster,
            [('10.0.0.2', 3, self.vnic0.fref),
             ('192.168.0.3', 7, self.vnic1.fref),
             ('192.168.0.4', 11,
              "%s-%s" % (instance_name_id, self.vnic2.name)),
             ],
        )

    def test_incoming_packets(self):
        instance_name_id = "%s-%s" % (self.instance.name, self.instance.id)
        self._check_get_samples(
            net.IncomingPacketsPollster,
            [('10.0.0.2', 2, self.vnic0.fref),
             ('192.168.0.3', 6, self.vnic1.fref),
             ('192.168.0.4', 10,
              "%s-%s" % (instance_name_id, self.vnic2.name)),
             ],
        )

    def test_outgoing_packets(self):
        instance_name_id = "%s-%s" % (self.instance.name, self.instance.id)
        self._check_get_samples(
            net.OutgoingPacketsPollster,
            [('10.0.0.2', 4, self.vnic0.fref),
             ('192.168.0.3', 8, self.vnic1.fref),
             ('192.168.0.4', 12,
              "%s-%s" % (instance_name_id, self.vnic2.name)),
             ],
        )

    @mock.patch('ceilometer.pipeline.setup_pipeline', mock.MagicMock())
    def test_metadata(self):
        factory = net.OutgoingBytesPollster
        pollster = factory()
        sm = pollster.make_vnic_sample(self.faux_instance,
                                       name='network.outgoing.bytes',
                                       type=sample.TYPE_CUMULATIVE,
                                       unit='B',
                                       volume=100,
                                       vnic_data=self.vnic0)

        user_metadata = sm.resource_metadata['user_metadata']
        expected = self.INSTANCE_PROPERTIES[
            'metadata']['metering.autoscale.group'][:256]
        self.assertEqual(expected, user_metadata['autoscale_group'])
        self.assertEqual(2, len(user_metadata))


class TestNetPollsterCache(base.TestPollsterBase):

    @mock.patch('ceilometer.pipeline.setup_pipeline', mock.MagicMock())
    def _check_get_samples_cache(self, factory):
        vnic0 = virt_inspector.Interface(
            name='vnet0',
            fref='fa163e71ec6e',
            mac='fa:16:3e:71:ec:6d',
            parameters=dict(ip='10.0.0.2',
                            projmask='255.255.255.0',
                            projnet='proj1',
                            dhcp_server='10.0.0.1'))
        stats0 = virt_inspector.InterfaceStats(rx_bytes=1, rx_packets=2,
                                               tx_bytes=3, tx_packets=4)
        vnics = [(vnic0, stats0)]

        mgr = manager.AgentManager()
        pollster = factory()
        cache = {
            pollster.CACHE_KEY_VNIC: {
                self.instance.id: vnics,
            },
        }
        samples = list(pollster.get_samples(mgr, cache, [self.instance]))
        self.assertEqual(1, len(samples))

    def test_incoming_bytes(self):
        self._check_get_samples_cache(net.IncomingBytesPollster)

    def test_outgoing_bytes(self):
        self._check_get_samples_cache(net.OutgoingBytesPollster)

    def test_incoming_packets(self):
        self._check_get_samples_cache(net.IncomingPacketsPollster)

    def test_outgoing_packets(self):
        self._check_get_samples_cache(net.OutgoingPacketsPollster)


class TestNetRatesPollster(base.TestPollsterBase):

    def setUp(self):
        super(TestNetRatesPollster, self).setUp()
        self.vnic0 = virt_inspector.Interface(
            name='vnet0',
            fref='fa163e71ec6e',
            mac='fa:16:3e:71:ec:6d',
            parameters=dict(ip='10.0.0.2',
                            projmask='255.255.255.0',
                            projnet='proj1',
                            dhcp_server='10.0.0.1'))
        stats0 = virt_inspector.InterfaceRateStats(rx_bytes_rate=1,
                                                   tx_bytes_rate=2)
        self.vnic1 = virt_inspector.Interface(
            name='vnet1',
            fref='fa163e71ec6f',
            mac='fa:16:3e:71:ec:6e',
            parameters=dict(ip='192.168.0.3',
                            projmask='255.255.255.0',
                            projnet='proj2',
                            dhcp_server='10.0.0.2'))
        stats1 = virt_inspector.InterfaceRateStats(rx_bytes_rate=3,
                                                   tx_bytes_rate=4)
        self.vnic2 = virt_inspector.Interface(
            name='vnet2',
            fref=None,
            mac='fa:18:4e:72:fc:7e',
            parameters=dict(ip='192.168.0.4',
                            projmask='255.255.255.0',
                            projnet='proj3',
                            dhcp_server='10.0.0.3'))
        stats2 = virt_inspector.InterfaceRateStats(rx_bytes_rate=5,
                                                   tx_bytes_rate=6)

        vnics = [
            (self.vnic0, stats0),
            (self.vnic1, stats1),
            (self.vnic2, stats2),
        ]
        self.inspector.inspect_vnic_rates = mock.Mock(return_value=vnics)

    @mock.patch('ceilometer.pipeline.setup_pipeline', mock.MagicMock())
    def _check_get_samples(self, factory, expected):
        mgr = manager.AgentManager()
        pollster = factory()
        samples = list(pollster.get_samples(mgr, {}, [self.instance]))
        self.assertEqual(3, len(samples))  # one for each nic
        self.assertEqual(set([samples[0].name]),
                         set([s.name for s in samples]))

        def _verify_vnic_metering(ip, expected_volume, expected_rid):
            match = [s for s in samples
                     if s.resource_metadata['parameters']['ip'] == ip
                     ]
            self.assertEqual(1, len(match), 'missing ip %s' % ip)
            self.assertEqual(expected_volume, match[0].volume)
            self.assertEqual('gauge', match[0].type)
            self.assertEqual(expected_rid, match[0].resource_id)

        for ip, volume, rid in expected:
            _verify_vnic_metering(ip, volume, rid)

    def test_incoming_bytes_rate(self):
        instance_name_id = "%s-%s" % (self.instance.name, self.instance.id)
        self._check_get_samples(
            net.IncomingBytesRatePollster,
            [('10.0.0.2', 1, self.vnic0.fref),
             ('192.168.0.3', 3, self.vnic1.fref),
             ('192.168.0.4', 5,
              "%s-%s" % (instance_name_id, self.vnic2.name)),
             ],
        )

    def test_outgoing_bytes_rate(self):
        instance_name_id = "%s-%s" % (self.instance.name, self.instance.id)
        self._check_get_samples(
            net.OutgoingBytesRatePollster,
            [('10.0.0.2', 2, self.vnic0.fref),
             ('192.168.0.3', 4, self.vnic1.fref),
             ('192.168.0.4', 6,
              "%s-%s" % (instance_name_id, self.vnic2.name)),
             ],
        )
