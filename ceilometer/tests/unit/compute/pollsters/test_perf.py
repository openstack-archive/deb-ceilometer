# Copyright 2016 Intel
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
from ceilometer.compute.pollsters import perf
from ceilometer.compute.virt import inspector as virt_inspector
from ceilometer.tests.unit.compute.pollsters import base


class TestPerfEventsPollster(base.TestPollsterBase):

    def setUp(self):
        super(TestPerfEventsPollster, self).setUp()

    @mock.patch('ceilometer.pipeline.setup_pipeline', mock.MagicMock())
    def test_get_samples(self):
        fake_value = virt_inspector.PerfEventsStats(cpu_cycles=7259361,
                                                    instructions=8815623,
                                                    cache_references=74184,
                                                    cache_misses=16737)

        def inspect_perf_events(instance, duration):
            return fake_value

        self.inspector.inspect_perf_events = mock.Mock(
            side_effect=inspect_perf_events)
        mgr = manager.AgentManager()

        def _check_perf_events_cpu_cycles(expected_usage):
            pollster = perf.PerfEventsCPUCyclesPollster()

            samples = list(pollster.get_samples(mgr, {}, [self.instance]))
            self.assertEqual(1, len(samples))
            self.assertEqual(set(['perf.cpu.cycles']),
                             set([s.name for s in samples]))
            self.assertEqual(expected_usage, samples[0].volume)

        def _check_perf_events_instructions(expected_usage):
            pollster = perf.PerfEventsInstructionsPollster()

            samples = list(pollster.get_samples(mgr, {}, [self.instance]))
            self.assertEqual(1, len(samples))
            self.assertEqual(set(['perf.instructions']),
                             set([s.name for s in samples]))
            self.assertEqual(expected_usage, samples[0].volume)

        def _check_perf_events_cache_references(expected_usage):
            pollster = perf.PerfEventsCacheReferencesPollster()

            samples = list(pollster.get_samples(mgr, {}, [self.instance]))
            self.assertEqual(1, len(samples))
            self.assertEqual(set(['perf.cache.references']),
                             set([s.name for s in samples]))
            self.assertEqual(expected_usage, samples[0].volume)

        def _check_perf_events_cache_misses(expected_usage):
            pollster = perf.PerfEventsCacheMissesPollster()

            samples = list(pollster.get_samples(mgr, {}, [self.instance]))
            self.assertEqual(1, len(samples))
            self.assertEqual(set(['perf.cache.misses']),
                             set([s.name for s in samples]))
            self.assertEqual(expected_usage, samples[0].volume)

        _check_perf_events_cpu_cycles(7259361)
        _check_perf_events_instructions(8815623)
        _check_perf_events_cache_references(74184)
        _check_perf_events_cache_misses(16737)

    @mock.patch('ceilometer.pipeline.setup_pipeline', mock.MagicMock())
    def test_get_samples_with_empty_stats(self):

        def inspect_perf_events(instance, duration):
            raise virt_inspector.NoDataException()

        self.inspector.inspect_perf_events = mock.Mock(
            side_effect=inspect_perf_events)

        mgr = manager.AgentManager()
        pollster = perf.PerfEventsCPUCyclesPollster()

        def all_samples():
            return list(pollster.get_samples(mgr, {}, [self.instance]))

        self.assertRaises(plugin_base.PollsterPermanentError,
                          all_samples)
