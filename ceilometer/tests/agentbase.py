# -*- encoding: utf-8 -*-
#
# Copyright © 2012 New Dream Network, LLC (DreamHost)
# Copyright © 2013 Intel corp.
# Copyright © 2013 eNovance
# Copyright © 2014 Red Hat, Inc
#
# Authors: Yunhong Jiang <yunhong.jiang@intel.com>
#          Julien Danjou <julien@danjou.info>
#          Eoghan Glynn <eglynn@redhat.com>
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

import abc
import copy
import datetime

import mock
import six
from stevedore import extension

from ceilometer.openstack.common.fixture import config
from ceilometer.openstack.common.fixture import mockpatch
from ceilometer import pipeline
from ceilometer import plugin
from ceilometer import publisher
from ceilometer.publisher import test as test_publisher
from ceilometer import sample
from ceilometer.tests import base
from ceilometer import transformer


class TestSample(sample.Sample):
    def __init__(self, name, type, unit, volume, user_id, project_id,
                 resource_id, timestamp, resource_metadata, source=None):
        super(TestSample, self).__init__(name, type, unit, volume, user_id,
                                         project_id, resource_id, timestamp,
                                         resource_metadata, source)

    def __eq__(self, other):
        if isinstance(other, self.__class__):
            return self.__dict__ == other.__dict__
        return False

    def __ne__(self, other):
        return not self.__eq__(other)


default_test_data = TestSample(
    name='test',
    type=sample.TYPE_CUMULATIVE,
    unit='',
    volume=1,
    user_id='test',
    project_id='test',
    resource_id='test_run_tasks',
    timestamp=datetime.datetime.utcnow().isoformat(),
    resource_metadata={'name': 'Pollster'},
)


class TestPollster(plugin.PollsterBase):
    test_data = default_test_data

    def get_samples(self, manager, cache, resources=[]):
        self.samples.append((manager, resources))
        self.resources.extend(resources)
        c = copy.copy(self.test_data)
        c.resource_metadata['resources'] = resources
        return [c]


class TestPollsterException(TestPollster):
    def get_samples(self, manager, cache, resources=[]):
        self.samples.append((manager, resources))
        self.resources.extend(resources)
        raise Exception()


class TestDiscovery(plugin.DiscoveryBase):
    def discover(self, param=None):
        self.params.append(param)
        return self.resources


class TestDiscoveryException(plugin.DiscoveryBase):
    def discover(self, param=None):
        self.params.append(param)
        raise Exception()


@six.add_metaclass(abc.ABCMeta)
class BaseAgentManagerTestCase(base.BaseTestCase):

    class Pollster(TestPollster):
        samples = []
        resources = []
        test_data = default_test_data

    class PollsterAnother(TestPollster):
        samples = []
        resources = []
        test_data = TestSample(
            name='testanother',
            type=default_test_data.type,
            unit=default_test_data.unit,
            volume=default_test_data.volume,
            user_id=default_test_data.user_id,
            project_id=default_test_data.project_id,
            resource_id=default_test_data.resource_id,
            timestamp=default_test_data.timestamp,
            resource_metadata=default_test_data.resource_metadata)

    class PollsterException(TestPollsterException):
        samples = []
        resources = []
        test_data = TestSample(
            name='testexception',
            type=default_test_data.type,
            unit=default_test_data.unit,
            volume=default_test_data.volume,
            user_id=default_test_data.user_id,
            project_id=default_test_data.project_id,
            resource_id=default_test_data.resource_id,
            timestamp=default_test_data.timestamp,
            resource_metadata=default_test_data.resource_metadata)

    class PollsterExceptionAnother(TestPollsterException):
        samples = []
        resources = []
        test_data = TestSample(
            name='testexceptionanother',
            type=default_test_data.type,
            unit=default_test_data.unit,
            volume=default_test_data.volume,
            user_id=default_test_data.user_id,
            project_id=default_test_data.project_id,
            resource_id=default_test_data.resource_id,
            timestamp=default_test_data.timestamp,
            resource_metadata=default_test_data.resource_metadata)

    class Discovery(TestDiscovery):
        params = []
        resources = []

    class DiscoveryAnother(TestDiscovery):
        params = []
        resources = []

    class DiscoveryException(TestDiscoveryException):
        params = []

    def setup_pipeline(self):
        self.transformer_manager = transformer.TransformerExtensionManager(
            'ceilometer.transformer',
        )
        self.mgr.pipeline_manager = pipeline.PipelineManager(
            self.pipeline_cfg,
            self.transformer_manager)

    def create_pollster_manager(self):
        return extension.ExtensionManager.make_test_instance(
            [
                extension.Extension(
                    'test',
                    None,
                    None,
                    self.Pollster(), ),
                extension.Extension(
                    'testanother',
                    None,
                    None,
                    self.PollsterAnother(), ),
                extension.Extension(
                    'testexception',
                    None,
                    None,
                    self.PollsterException(), ),
                extension.Extension(
                    'testexceptionanother',
                    None,
                    None,
                    self.PollsterExceptionAnother(), ),
            ],
        )

    def create_discovery_manager(self):
        return extension.ExtensionManager.make_test_instance(
            [
                extension.Extension(
                    'testdiscovery',
                    None,
                    None,
                    self.Discovery(), ),
                extension.Extension(
                    'testdiscoveryanother',
                    None,
                    None,
                    self.DiscoveryAnother(), ),
                extension.Extension(
                    'testdiscoveryexception',
                    None,
                    None,
                    self.DiscoveryException(), ),
            ],
        )

    @abc.abstractmethod
    def create_manager(self):
        """Return subclass specific manager."""

    @mock.patch('ceilometer.pipeline.setup_pipeline', mock.MagicMock())
    def setUp(self):
        super(BaseAgentManagerTestCase, self).setUp()
        self.mgr = self.create_manager()
        self.mgr.pollster_manager = self.create_pollster_manager()
        self.pipeline_cfg = [{
            'name': "test_pipeline",
            'interval': 60,
            'counters': ['test'],
            'resources': ['test://'] if self.source_resources else [],
            'transformers': [],
            'publishers': ["test"],
        }, ]
        self.setup_pipeline()
        self.CONF = self.useFixture(config.Config()).conf
        self.CONF.set_override(
            'pipeline_cfg_file',
            self.path_get('etc/ceilometer/pipeline.yaml')
        )
        self.useFixture(mockpatch.PatchObject(
            publisher, 'get_publisher', side_effect=self.get_publisher))

    def get_publisher(self, url, namespace=''):
        fake_drivers = {'test://': test_publisher.TestPublisher,
                        'new://': test_publisher.TestPublisher,
                        'rpc://': test_publisher.TestPublisher}
        return fake_drivers[url](url)

    def tearDown(self):
        self.Pollster.samples = []
        self.PollsterAnother.samples = []
        self.PollsterException.samples = []
        self.PollsterExceptionAnother.samples = []
        self.Pollster.resources = []
        self.PollsterAnother.resources = []
        self.PollsterException.resources = []
        self.PollsterExceptionAnother.resources = []
        self.Discovery.params = []
        self.DiscoveryAnother.params = []
        self.DiscoveryException.params = []
        self.Discovery.resources = []
        self.DiscoveryAnother.resources = []
        super(BaseAgentManagerTestCase, self).tearDown()

    def test_setup_polling_tasks(self):
        polling_tasks = self.mgr.setup_polling_tasks()
        self.assertEqual(len(polling_tasks), 1)
        self.assertTrue(60 in polling_tasks.keys())
        per_task_resources = polling_tasks[60].resources
        self.assertEqual(len(per_task_resources), 1)
        self.assertEqual(set(per_task_resources['test'].resources),
                         set(self.pipeline_cfg[0]['resources']))
        self.mgr.interval_task(polling_tasks.values()[0])
        pub = self.mgr.pipeline_manager.pipelines[0].publishers[0]
        del pub.samples[0].resource_metadata['resources']
        self.assertEqual(pub.samples[0], self.Pollster.test_data)

    def test_setup_polling_tasks_multiple_interval(self):
        self.pipeline_cfg.append({
            'name': "test_pipeline",
            'interval': 10,
            'counters': ['test'],
            'resources': ['test://'] if self.source_resources else [],
            'transformers': [],
            'publishers': ["test"],
        })
        self.setup_pipeline()
        polling_tasks = self.mgr.setup_polling_tasks()
        self.assertEqual(len(polling_tasks), 2)
        self.assertTrue(60 in polling_tasks.keys())
        self.assertTrue(10 in polling_tasks.keys())

    def test_setup_polling_tasks_mismatch_counter(self):
        self.pipeline_cfg.append(
            {
                'name': "test_pipeline_1",
                'interval': 10,
                'counters': ['test_invalid'],
                'resources': ['invalid://'],
                'transformers': [],
                'publishers': ["test"],
            })
        polling_tasks = self.mgr.setup_polling_tasks()
        self.assertEqual(len(polling_tasks), 1)
        self.assertTrue(60 in polling_tasks.keys())

    def test_setup_polling_task_same_interval(self):
        self.pipeline_cfg.append({
            'name': "test_pipeline",
            'interval': 60,
            'counters': ['testanother'],
            'resources': ['testanother://'] if self.source_resources else [],
            'transformers': [],
            'publishers': ["test"],
        })
        self.setup_pipeline()
        polling_tasks = self.mgr.setup_polling_tasks()
        self.assertEqual(len(polling_tasks), 1)
        pollsters = polling_tasks.get(60).pollsters
        self.assertEqual(len(pollsters), 2)
        per_task_resources = polling_tasks[60].resources
        self.assertEqual(len(per_task_resources), 2)
        self.assertEqual(set(per_task_resources['test'].resources),
                         set(self.pipeline_cfg[0]['resources']))
        self.assertEqual(set(per_task_resources['testanother'].resources),
                         set(self.pipeline_cfg[1]['resources']))

    def test_interval_exception_isolation(self):
        self.pipeline_cfg = [
            {
                'name': "test_pipeline_1",
                'interval': 10,
                'counters': ['testexceptionanother'],
                'resources': ['test://'] if self.source_resources else [],
                'transformers': [],
                'publishers': ["test"],
            },
            {
                'name': "test_pipeline_2",
                'interval': 10,
                'counters': ['testexception'],
                'resources': ['test://'] if self.source_resources else [],
                'transformers': [],
                'publishers': ["test"],
            },
        ]
        self.mgr.pipeline_manager = pipeline.PipelineManager(
            self.pipeline_cfg,
            self.transformer_manager)

        polling_tasks = self.mgr.setup_polling_tasks()
        self.assertEqual(len(polling_tasks.keys()), 1)
        polling_tasks.get(10)
        self.mgr.interval_task(polling_tasks.get(10))
        pub = self.mgr.pipeline_manager.pipelines[0].publishers[0]
        self.assertEqual(len(pub.samples), 0)

    def test_agent_manager_start(self):
        mgr = self.create_manager()
        mgr.pollster_manager = self.mgr.pollster_manager
        mgr.create_polling_task = mock.MagicMock()
        mgr.tg = mock.MagicMock()
        mgr.start()
        self.assertTrue(mgr.tg.add_timer.called)

    def test_manager_exception_persistency(self):
        self.pipeline_cfg.append({
            'name': "test_pipeline",
            'interval': 60,
            'counters': ['testanother'],
            'transformers': [],
            'publishers': ["test"],
        })
        self.setup_pipeline()

    def _verify_discovery_params(self, expected):
        self.assertEqual(self.Discovery.params, expected)
        self.assertEqual(self.DiscoveryAnother.params, expected)
        self.assertEqual(self.DiscoveryException.params, expected)

    def _do_test_per_agent_discovery(self,
                                     discovered_resources,
                                     static_resources):
        self.mgr.discovery_manager = self.create_discovery_manager()
        if discovered_resources:
            self.mgr.default_discovery = [d.name
                                          for d in self.mgr.discovery_manager]
        self.Discovery.resources = discovered_resources
        self.DiscoveryAnother.resources = [d[::-1]
                                           for d in discovered_resources]
        self.pipeline_cfg[0]['resources'] = static_resources
        self.setup_pipeline()
        polling_tasks = self.mgr.setup_polling_tasks()
        self.mgr.interval_task(polling_tasks.get(60))
        self._verify_discovery_params([None] if discovered_resources else [])
        discovery = self.Discovery.resources + self.DiscoveryAnother.resources
        # compare resource lists modulo ordering
        self.assertEqual(set(self.Pollster.resources),
                         set(static_resources or discovery))

    def test_per_agent_discovery_discovered_only(self):
        self._do_test_per_agent_discovery(['discovered_1', 'discovered_2'],
                                          [])

    def test_per_agent_discovery_static_only(self):
        self._do_test_per_agent_discovery([],
                                          ['static_1', 'static_2'])

    def test_per_agent_discovery_discovered_overridden_by_static(self):
        self._do_test_per_agent_discovery(['discovered_1', 'discovered_2'],
                                          ['static_1', 'static_2'])

    def test_per_agent_discovery_overridden_by_per_pipeline_discovery(self):
        discovered_resources = ['discovered_1', 'discovered_2']
        self.mgr.discovery_manager = self.create_discovery_manager()
        self.Discovery.resources = discovered_resources
        self.DiscoveryAnother.resources = [d[::-1]
                                           for d in discovered_resources]
        self.pipeline_cfg[0]['discovery'] = ['testdiscoveryanother',
                                             'testdiscoverynonexistent',
                                             'testdiscoveryexception']
        self.pipeline_cfg[0]['resources'] = []
        self.setup_pipeline()
        polling_tasks = self.mgr.setup_polling_tasks()
        self.mgr.interval_task(polling_tasks.get(60))
        self.assertEqual(set(self.Pollster.resources),
                         set(self.DiscoveryAnother.resources))

    def _do_test_per_pipeline_discovery(self,
                                        discovered_resources,
                                        static_resources):
        self.mgr.discovery_manager = self.create_discovery_manager()
        self.Discovery.resources = discovered_resources
        self.DiscoveryAnother.resources = [d[::-1]
                                           for d in discovered_resources]
        self.pipeline_cfg[0]['discovery'] = ['testdiscovery',
                                             'testdiscoveryanother',
                                             'testdiscoverynonexistent',
                                             'testdiscoveryexception']
        self.pipeline_cfg[0]['resources'] = static_resources
        self.setup_pipeline()
        polling_tasks = self.mgr.setup_polling_tasks()
        self.mgr.interval_task(polling_tasks.get(60))
        discovery = self.Discovery.resources + self.DiscoveryAnother.resources
        # compare resource lists modulo ordering
        self.assertEqual(set(self.Pollster.resources),
                         set(static_resources + discovery))

    def test_per_pipeline_discovery_discovered_only(self):
        self._do_test_per_pipeline_discovery(['discovered_1', 'discovered_2'],
                                             [])

    def test_per_pipeline_discovery_static_only(self):
        self._do_test_per_pipeline_discovery([],
                                             ['static_1', 'static_2'])

    def test_per_pipeline_discovery_discovered_augmented_by_static(self):
        self._do_test_per_pipeline_discovery(['discovered_1', 'discovered_2'],
                                             ['static_1', 'static_2'])

    def test_multiple_pipelines_different_static_resources(self):
        # assert that the amalgation of all static resources for a set
        # of pipelines with a common interval is passed to individual
        # pollsters matching those pipelines
        self.pipeline_cfg[0]['resources'] = ['test://']
        self.pipeline_cfg.append({
            'name': "another_pipeline",
            'interval': 60,
            'counters': ['test'],
            'resources': ['another://'],
            'transformers': [],
            'publishers': ["new"],
        })
        self.mgr.discovery_manager = self.create_discovery_manager()
        self.Discovery.resources = []
        self.setup_pipeline()
        polling_tasks = self.mgr.setup_polling_tasks()
        self.assertEqual(len(polling_tasks), 1)
        self.assertTrue(60 in polling_tasks.keys())
        self.mgr.interval_task(polling_tasks.get(60))
        self._verify_discovery_params([])
        self.assertEqual(len(self.Pollster.samples), 1)
        amalgamated_resources = set(['test://', 'another://'])
        self.assertEqual(set(self.Pollster.samples[0][1]),
                         amalgamated_resources)
        for pipeline in self.mgr.pipeline_manager.pipelines:
            self.assertEqual(len(pipeline.publishers[0].samples), 1)
            published = pipeline.publishers[0].samples[0]
            self.assertEqual(set(published.resource_metadata['resources']),
                             amalgamated_resources)
