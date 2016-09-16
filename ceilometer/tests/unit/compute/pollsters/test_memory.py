# Copyright (c) 2014 VMware, Inc.
# All Rights Reserved.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

import mock

from ceilometer.agent import manager
from ceilometer.agent import plugin_base
from ceilometer.compute.pollsters import memory
from ceilometer.compute.virt import inspector as virt_inspector
from ceilometer.tests.unit.compute.pollsters import base


class TestMemoryPollster(base.TestPollsterBase):

    def setUp(self):
        super(TestMemoryPollster, self).setUp()

    @mock.patch('ceilometer.pipeline.setup_pipeline', mock.MagicMock())
    def test_get_samples(self):
        next_value = iter((
            virt_inspector.MemoryUsageStats(usage=1.0),
            virt_inspector.MemoryUsageStats(usage=2.0),
            virt_inspector.InstanceNoDataException(),
            virt_inspector.InstanceShutOffException(),
        ))

        def inspect_memory_usage(instance, duration):
            value = next(next_value)
            if isinstance(value, virt_inspector.MemoryUsageStats):
                return value
            else:
                raise value

        self.inspector.inspect_memory_usage = mock.Mock(
            side_effect=inspect_memory_usage)

        mgr = manager.AgentManager()
        pollster = memory.MemoryUsagePollster()

        @mock.patch('ceilometer.compute.pollsters.memory.LOG')
        def _verify_memory_metering(expected_count, expected_memory_mb,
                                    expected_warnings, mylog):
            samples = list(pollster.get_samples(mgr, {}, [self.instance]))
            self.assertEqual(expected_count, len(samples))
            if expected_count > 0:
                self.assertEqual(set(['memory.usage']),
                                 set([s.name for s in samples]))
                self.assertEqual(expected_memory_mb, samples[0].volume)
            else:
                self.assertEqual(expected_warnings, mylog.warning.call_count)
            self.assertEqual(0, mylog.exception.call_count)

        _verify_memory_metering(1, 1.0, 0)
        _verify_memory_metering(1, 2.0, 0)
        _verify_memory_metering(0, 0, 1)
        _verify_memory_metering(0, 0, 0)

    @mock.patch('ceilometer.pipeline.setup_pipeline', mock.MagicMock())
    def test_get_samples_with_empty_stats(self):

        def inspect_memory_usage(instance, duration):
            raise virt_inspector.NoDataException()

        self.inspector.inspect_memory_usage = mock.Mock(
            side_effect=inspect_memory_usage)

        mgr = manager.AgentManager()
        pollster = memory.MemoryUsagePollster()

        def all_samples():
            return list(pollster.get_samples(mgr, {}, [self.instance]))

        self.assertRaises(plugin_base.PollsterPermanentError,
                          all_samples)


class TestResidentMemoryPollster(base.TestPollsterBase):

    def setUp(self):
        super(TestResidentMemoryPollster, self).setUp()

    @mock.patch('ceilometer.pipeline.setup_pipeline', mock.MagicMock())
    def test_get_samples(self):
        next_value = iter((
            virt_inspector.MemoryResidentStats(resident=1.0),
            virt_inspector.MemoryResidentStats(resident=2.0),
            virt_inspector.NoDataException(),
            virt_inspector.InstanceShutOffException(),
        ))

        def inspect_memory_resident(instance, duration):
            value = next(next_value)
            if isinstance(value, virt_inspector.MemoryResidentStats):
                return value
            else:
                raise value

        self.inspector.inspect_memory_resident = mock.Mock(
            side_effect=inspect_memory_resident)

        mgr = manager.AgentManager()
        pollster = memory.MemoryResidentPollster()

        @mock.patch('ceilometer.compute.pollsters.memory.LOG')
        def _verify_resident_memory_metering(expected_count,
                                             expected_resident_memory_mb,
                                             expected_warnings, mylog):
            samples = list(pollster.get_samples(mgr, {}, [self.instance]))
            self.assertEqual(expected_count, len(samples))
            if expected_count > 0:
                self.assertEqual(set(['memory.resident']),
                                 set([s.name for s in samples]))
                self.assertEqual(expected_resident_memory_mb,
                                 samples[0].volume)
            else:
                self.assertEqual(expected_warnings, mylog.warning.call_count)
            self.assertEqual(0, mylog.exception.call_count)

        _verify_resident_memory_metering(1, 1.0, 0)
        _verify_resident_memory_metering(1, 2.0, 0)
        _verify_resident_memory_metering(0, 0, 1)
        _verify_resident_memory_metering(0, 0, 0)


class TestMemoryBandwidthPollster(base.TestPollsterBase):

    def setUp(self):
        super(TestMemoryBandwidthPollster, self).setUp()

    @mock.patch('ceilometer.pipeline.setup_pipeline', mock.MagicMock())
    def test_get_samples(self):
        next_value = iter((
            virt_inspector.MemoryBandwidthStats(total=1892352, local=1802240),
            virt_inspector.MemoryBandwidthStats(total=1081344, local=90112),
        ))

        def inspect_memory_bandwidth(instance, duration):
            return next(next_value)

        self.inspector.inspect_memory_bandwidth = mock.Mock(
            side_effect=inspect_memory_bandwidth)
        mgr = manager.AgentManager()

        def _check_memory_bandwidth_total(expected_usage):
            pollster = memory.MemoryBandwidthTotalPollster()

            samples = list(pollster.get_samples(mgr, {}, [self.instance]))
            self.assertEqual(1, len(samples))
            self.assertEqual(set(['memory.bandwidth.total']),
                             set([s.name for s in samples]))
            self.assertEqual(expected_usage, samples[0].volume)

        def _check_memory_bandwidth_local(expected_usage):
            pollster = memory.MemoryBandwidthLocalPollster()

            samples = list(pollster.get_samples(mgr, {}, [self.instance]))
            self.assertEqual(1, len(samples))
            self.assertEqual(set(['memory.bandwidth.local']),
                             set([s.name for s in samples]))
            self.assertEqual(expected_usage, samples[0].volume)

        _check_memory_bandwidth_total(1892352)
        _check_memory_bandwidth_local(90112)

    @mock.patch('ceilometer.pipeline.setup_pipeline', mock.MagicMock())
    def test_get_samples_with_empty_stats(self):

        def inspect_memory_bandwidth(instance, duration):
            raise virt_inspector.NoDataException()

        self.inspector.inspect_memory_bandwidth = mock.Mock(
            side_effect=inspect_memory_bandwidth)

        mgr = manager.AgentManager()
        pollster = memory.MemoryBandwidthTotalPollster()

        def all_samples():
            return list(pollster.get_samples(mgr, {}, [self.instance]))

        self.assertRaises(plugin_base.PollsterPermanentError,
                          all_samples)
