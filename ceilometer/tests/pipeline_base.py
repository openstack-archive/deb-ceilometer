# -*- coding: utf-8 -*-
#
# Copyright 2013 Intel Corp.
#
# Authors: Yunhong Jiang <yunhong.jiang@intel.com>
#          Julien Danjou <julien@danjou.info>
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
import datetime
import traceback

import mock
from oslo_utils import timeutils
from oslotest import base
from oslotest import mockpatch
import six
from stevedore import extension

from ceilometer import pipeline
from ceilometer import publisher
from ceilometer.publisher import test as test_publisher
from ceilometer import sample
from ceilometer import transformer
from ceilometer.transformer import accumulator
from ceilometer.transformer import arithmetic
from ceilometer.transformer import conversions


@six.add_metaclass(abc.ABCMeta)
class BasePipelineTestCase(base.BaseTestCase):
    @staticmethod
    def fake_tem_init():
        """Fake a transformerManager for pipeline.

        The faked entry point setting is below:
        update: TransformerClass
        except: TransformerClassException
        drop:   TransformerClassDrop
        """
        pass

    def fake_tem_get_ext(self, name):
        class_name_ext = {
            'update': self.TransformerClass,
            'except': self.TransformerClassException,
            'drop': self.TransformerClassDrop,
            'cache': accumulator.TransformerAccumulator,
            'aggregator': conversions.AggregatorTransformer,
            'unit_conversion': conversions.ScalingTransformer,
            'rate_of_change': conversions.RateOfChangeTransformer,
            'arithmetic': arithmetic.ArithmeticTransformer,
            'delta': conversions.DeltaTransformer,
        }

        if name in class_name_ext:
            return extension.Extension(name, None,
                                       class_name_ext[name],
                                       None,
                                       )

        raise KeyError(name)

    def get_publisher(self, url, namespace=''):
        fake_drivers = {'test://': test_publisher.TestPublisher,
                        'new://': test_publisher.TestPublisher,
                        'except://': self.PublisherClassException}
        return fake_drivers[url](url)

    class PublisherClassException(publisher.PublisherBase):
        def publish_samples(self, ctxt, samples):
            raise Exception()

        def publish_events(self, ctxt, events):
            raise Exception()

    class TransformerClass(transformer.TransformerBase):
        samples = []
        grouping_keys = ['counter_name']

        def __init__(self, append_name='_update'):
            self.__class__.samples = []
            self.append_name = append_name

        def flush(self, ctxt):
            return []

        def handle_sample(self, ctxt, counter):
            self.__class__.samples.append(counter)
            newname = getattr(counter, 'name') + self.append_name
            return sample.Sample(
                name=newname,
                type=counter.type,
                volume=counter.volume,
                unit=counter.unit,
                user_id=counter.user_id,
                project_id=counter.project_id,
                resource_id=counter.resource_id,
                timestamp=counter.timestamp,
                resource_metadata=counter.resource_metadata,
            )

    class TransformerClassDrop(transformer.TransformerBase):
        samples = []
        grouping_keys = ['resource_id']

        def __init__(self):
            self.__class__.samples = []

        def handle_sample(self, ctxt, counter):
            self.__class__.samples.append(counter)

    class TransformerClassException(object):
        grouping_keys = ['resource_id']

        @staticmethod
        def handle_sample(ctxt, counter):
            raise Exception()

    def setUp(self):
        super(BasePipelineTestCase, self).setUp()

        self.test_counter = sample.Sample(
            name='a',
            type=sample.TYPE_GAUGE,
            volume=1,
            unit='B',
            user_id="test_user",
            project_id="test_proj",
            resource_id="test_resource",
            timestamp=timeutils.utcnow().isoformat(),
            resource_metadata={}
        )

        self.useFixture(mockpatch.PatchObject(
            publisher, 'get_publisher', side_effect=self.get_publisher))

        self.transformer_manager = mock.MagicMock()
        self.transformer_manager.__getitem__.side_effect = \
            self.fake_tem_get_ext

        self._setup_pipeline_cfg()

        self._reraise_exception = True
        self.useFixture(mockpatch.Patch(
            'ceilometer.pipeline.LOG.exception',
            side_effect=self._handle_reraise_exception))

    def _handle_reraise_exception(self, msg):
        if self._reraise_exception:
            raise Exception(traceback.format_exc())

    @abc.abstractmethod
    def _setup_pipeline_cfg(self):
        """Setup the appropriate form of pipeline config."""

    @abc.abstractmethod
    def _augment_pipeline_cfg(self):
        """Augment the pipeline config with an additional element."""

    @abc.abstractmethod
    def _break_pipeline_cfg(self):
        """Break the pipeline config with a malformed element."""

    @abc.abstractmethod
    def _dup_pipeline_name_cfg(self):
        """Break the pipeline config with duplicate pipeline name."""

    @abc.abstractmethod
    def _set_pipeline_cfg(self, field, value):
        """Set a field to a value in the pipeline config."""

    @abc.abstractmethod
    def _extend_pipeline_cfg(self, field, value):
        """Extend an existing field in the pipeline config with a value."""

    @abc.abstractmethod
    def _unset_pipeline_cfg(self, field):
        """Clear an existing field in the pipeline config."""

    def _exception_create_pipelinemanager(self):
        self.assertRaises(pipeline.PipelineException,
                          pipeline.PipelineManager,
                          self.pipeline_cfg,
                          self.transformer_manager)

    def test_no_counters(self):
        self._unset_pipeline_cfg('counters')
        self._exception_create_pipelinemanager()

    def test_no_transformers(self):
        self._unset_pipeline_cfg('transformers')
        pipeline.PipelineManager(self.pipeline_cfg, self.transformer_manager)

    def test_no_name(self):
        self._unset_pipeline_cfg('name')
        self._exception_create_pipelinemanager()

    def test_no_interval(self):
        self._unset_pipeline_cfg('interval')
        pipeline_manager = pipeline.PipelineManager(self.pipeline_cfg,
                                                    self.transformer_manager)

        pipe = pipeline_manager.pipelines[0]
        self.assertEqual(600, pipe.get_interval())

    def test_no_publishers(self):
        self._unset_pipeline_cfg('publishers')
        self._exception_create_pipelinemanager()

    def test_invalid_resources(self):
        invalid_resource = {'invalid': 1}
        self._set_pipeline_cfg('resources', invalid_resource)
        self._exception_create_pipelinemanager()

    def test_check_counters_include_exclude_same(self):
        counter_cfg = ['a', '!a']
        self._set_pipeline_cfg('counters', counter_cfg)
        self._exception_create_pipelinemanager()

    def test_check_counters_include_exclude(self):
        counter_cfg = ['a', '!b']
        self._set_pipeline_cfg('counters', counter_cfg)
        self._exception_create_pipelinemanager()

    def test_check_counters_wildcard_included(self):
        counter_cfg = ['a', '*']
        self._set_pipeline_cfg('counters', counter_cfg)
        self._exception_create_pipelinemanager()

    def test_check_publishers_invalid_publisher(self):
        publisher_cfg = ['test_invalid']
        self._set_pipeline_cfg('publishers', publisher_cfg)

    def test_invalid_string_interval(self):
        self._set_pipeline_cfg('interval', 'string')
        self._exception_create_pipelinemanager()

    def test_check_transformer_invalid_transformer(self):
        transformer_cfg = [
            {'name': "test_invalid",
             'parameters': {}}
        ]
        self._set_pipeline_cfg('transformers', transformer_cfg)
        self._exception_create_pipelinemanager()

    def test_get_interval(self):
        pipeline_manager = pipeline.PipelineManager(self.pipeline_cfg,
                                                    self.transformer_manager)

        pipe = pipeline_manager.pipelines[0]
        self.assertEqual(5, pipe.get_interval())

    def test_publisher_transformer_invoked(self):
        pipeline_manager = pipeline.PipelineManager(self.pipeline_cfg,
                                                    self.transformer_manager)

        with pipeline_manager.publisher(None) as p:
            p([self.test_counter])

        publisher = pipeline_manager.pipelines[0].publishers[0]
        self.assertEqual(1, len(publisher.samples))
        self.assertEqual(1, len(self.TransformerClass.samples))
        self.assertEqual('a_update', getattr(publisher.samples[0], "name"))
        self.assertEqual('a',
                         getattr(self.TransformerClass.samples[0], "name"))

    def test_multiple_included_counters(self):
        counter_cfg = ['a', 'b']
        self._set_pipeline_cfg('counters', counter_cfg)
        pipeline_manager = pipeline.PipelineManager(self.pipeline_cfg,
                                                    self.transformer_manager)

        with pipeline_manager.publisher(None) as p:
            p([self.test_counter])

        publisher = pipeline_manager.pipelines[0].publishers[0]
        self.assertEqual(1, len(publisher.samples))

        self.test_counter = sample.Sample(
            name='b',
            type=self.test_counter.type,
            volume=self.test_counter.volume,
            unit=self.test_counter.unit,
            user_id=self.test_counter.user_id,
            project_id=self.test_counter.project_id,
            resource_id=self.test_counter.resource_id,
            timestamp=self.test_counter.timestamp,
            resource_metadata=self.test_counter.resource_metadata,
        )

        with pipeline_manager.publisher(None) as p:
            p([self.test_counter])

        self.assertEqual(2, len(publisher.samples))
        self.assertEqual(2, len(self.TransformerClass.samples))
        self.assertEqual('a_update', getattr(publisher.samples[0], "name"))
        self.assertEqual('b_update', getattr(publisher.samples[1], "name"))

    @mock.patch('ceilometer.pipeline.LOG')
    def test_none_volume_counter(self, LOG):
        self._set_pipeline_cfg('counters', ['empty_volume'])
        pipeline_manager = pipeline.PipelineManager(self.pipeline_cfg,
                                                    self.transformer_manager)
        publisher = pipeline_manager.pipelines[0].publishers[0]

        test_s = sample.Sample(
            name='empty_volume',
            type=self.test_counter.type,
            volume=None,
            unit=self.test_counter.unit,
            user_id=self.test_counter.user_id,
            project_id=self.test_counter.project_id,
            resource_id=self.test_counter.resource_id,
            timestamp=self.test_counter.timestamp,
            resource_metadata=self.test_counter.resource_metadata,
        )

        with pipeline_manager.publisher(None) as p:
            p([test_s])

        LOG.warning.assert_called_once_with(
            'metering data %(counter_name)s for %(resource_id)s '
            '@ %(timestamp)s has no volume (volume: %(counter_volume)s), the '
            'sample will be dropped'
            % {'counter_name': test_s.name,
               'resource_id': test_s.resource_id,
               'timestamp': test_s.timestamp,
               'counter_volume': test_s.volume})

        self.assertEqual(0, len(publisher.samples))

    @mock.patch('ceilometer.pipeline.LOG')
    def test_fake_volume_counter(self, LOG):
        self._set_pipeline_cfg('counters', ['fake_volume'])
        pipeline_manager = pipeline.PipelineManager(self.pipeline_cfg,
                                                    self.transformer_manager)
        publisher = pipeline_manager.pipelines[0].publishers[0]

        test_s = sample.Sample(
            name='fake_volume',
            type=self.test_counter.type,
            volume='fake_value',
            unit=self.test_counter.unit,
            user_id=self.test_counter.user_id,
            project_id=self.test_counter.project_id,
            resource_id=self.test_counter.resource_id,
            timestamp=self.test_counter.timestamp,
            resource_metadata=self.test_counter.resource_metadata,
        )

        with pipeline_manager.publisher(None) as p:
            p([test_s])

        LOG.warning.assert_called_once_with(
            'metering data %(counter_name)s for %(resource_id)s '
            '@ %(timestamp)s has volume which is not a number '
            '(volume: %(counter_volume)s), the sample will be dropped'
            % {'counter_name': test_s.name,
               'resource_id': test_s.resource_id,
               'timestamp': test_s.timestamp,
               'counter_volume': test_s.volume})

        self.assertEqual(0, len(publisher.samples))

    def test_counter_dont_match(self):
        counter_cfg = ['nomatch']
        self._set_pipeline_cfg('counters', counter_cfg)
        pipeline_manager = pipeline.PipelineManager(self.pipeline_cfg,
                                                    self.transformer_manager)
        with pipeline_manager.publisher(None) as p:
            p([self.test_counter])

        publisher = pipeline_manager.pipelines[0].publishers[0]
        self.assertEqual(0, len(publisher.samples))
        self.assertEqual(0, publisher.calls)

    def test_wildcard_counter(self):
        counter_cfg = ['*']
        self._set_pipeline_cfg('counters', counter_cfg)
        pipeline_manager = pipeline.PipelineManager(self.pipeline_cfg,
                                                    self.transformer_manager)
        with pipeline_manager.publisher(None) as p:
            p([self.test_counter])

        publisher = pipeline_manager.pipelines[0].publishers[0]
        self.assertEqual(1, len(publisher.samples))
        self.assertEqual(1, len(self.TransformerClass.samples))
        self.assertEqual('a_update', getattr(publisher.samples[0], "name"))

    def test_wildcard_excluded_counters(self):
        counter_cfg = ['*', '!a']
        self._set_pipeline_cfg('counters', counter_cfg)
        pipeline_manager = pipeline.PipelineManager(self.pipeline_cfg,
                                                    self.transformer_manager)
        self.assertFalse(pipeline_manager.pipelines[0].support_meter('a'))

    def test_wildcard_excluded_counters_not_excluded(self):
        counter_cfg = ['*', '!b']
        self._set_pipeline_cfg('counters', counter_cfg)
        pipeline_manager = pipeline.PipelineManager(self.pipeline_cfg,
                                                    self.transformer_manager)
        with pipeline_manager.publisher(None) as p:
            p([self.test_counter])
        publisher = pipeline_manager.pipelines[0].publishers[0]
        self.assertEqual(1, len(publisher.samples))
        self.assertEqual(1, len(self.TransformerClass.samples))
        self.assertEqual('a_update', getattr(publisher.samples[0], "name"))

    def test_all_excluded_counters_not_excluded(self):
        counter_cfg = ['!b', '!c']
        self._set_pipeline_cfg('counters', counter_cfg)
        pipeline_manager = pipeline.PipelineManager(self.pipeline_cfg,
                                                    self.transformer_manager)
        with pipeline_manager.publisher(None) as p:
            p([self.test_counter])

        publisher = pipeline_manager.pipelines[0].publishers[0]
        self.assertEqual(1, len(publisher.samples))
        self.assertEqual(1, len(self.TransformerClass.samples))
        self.assertEqual('a_update', getattr(publisher.samples[0], "name"))
        self.assertEqual('a',
                         getattr(self.TransformerClass.samples[0], "name"))

    def test_all_excluded_counters_is_excluded(self):
        counter_cfg = ['!a', '!c']
        self._set_pipeline_cfg('counters', counter_cfg)
        pipeline_manager = pipeline.PipelineManager(self.pipeline_cfg,
                                                    self.transformer_manager)
        self.assertFalse(pipeline_manager.pipelines[0].support_meter('a'))
        self.assertTrue(pipeline_manager.pipelines[0].support_meter('b'))
        self.assertFalse(pipeline_manager.pipelines[0].support_meter('c'))

    def test_wildcard_and_excluded_wildcard_counters(self):
        counter_cfg = ['*', '!disk.*']
        self._set_pipeline_cfg('counters', counter_cfg)
        pipeline_manager = pipeline.PipelineManager(self.pipeline_cfg,
                                                    self.transformer_manager)
        self.assertFalse(pipeline_manager.pipelines[0].
                         support_meter('disk.read.bytes'))
        self.assertTrue(pipeline_manager.pipelines[0].support_meter('cpu'))

    def test_included_counter_and_wildcard_counters(self):
        counter_cfg = ['cpu', 'disk.*']
        self._set_pipeline_cfg('counters', counter_cfg)
        pipeline_manager = pipeline.PipelineManager(self.pipeline_cfg,
                                                    self.transformer_manager)
        self.assertTrue(pipeline_manager.pipelines[0].
                        support_meter('disk.read.bytes'))
        self.assertTrue(pipeline_manager.pipelines[0].support_meter('cpu'))
        self.assertFalse(pipeline_manager.pipelines[0].
                         support_meter('instance'))

    def test_excluded_counter_and_excluded_wildcard_counters(self):
        counter_cfg = ['!cpu', '!disk.*']
        self._set_pipeline_cfg('counters', counter_cfg)
        pipeline_manager = pipeline.PipelineManager(self.pipeline_cfg,
                                                    self.transformer_manager)
        self.assertFalse(pipeline_manager.pipelines[0].
                         support_meter('disk.read.bytes'))
        self.assertFalse(pipeline_manager.pipelines[0].support_meter('cpu'))
        self.assertTrue(pipeline_manager.pipelines[0].
                        support_meter('instance'))

    def test_multiple_pipeline(self):
        self._augment_pipeline_cfg()

        pipeline_manager = pipeline.PipelineManager(self.pipeline_cfg,
                                                    self.transformer_manager)
        with pipeline_manager.publisher(None) as p:
            p([self.test_counter])

        self.test_counter = sample.Sample(
            name='b',
            type=self.test_counter.type,
            volume=self.test_counter.volume,
            unit=self.test_counter.unit,
            user_id=self.test_counter.user_id,
            project_id=self.test_counter.project_id,
            resource_id=self.test_counter.resource_id,
            timestamp=self.test_counter.timestamp,
            resource_metadata=self.test_counter.resource_metadata,
        )

        with pipeline_manager.publisher(None) as p:
            p([self.test_counter])

        publisher = pipeline_manager.pipelines[0].publishers[0]
        self.assertEqual(1, len(publisher.samples))
        self.assertEqual(1, publisher.calls)
        self.assertEqual('a_update', getattr(publisher.samples[0], "name"))
        new_publisher = pipeline_manager.pipelines[1].publishers[0]
        self.assertEqual(1, len(new_publisher.samples))
        self.assertEqual(1, new_publisher.calls)
        self.assertEqual('b_new', getattr(new_publisher.samples[0], "name"))
        self.assertEqual(2, len(self.TransformerClass.samples))
        self.assertEqual('a',
                         getattr(self.TransformerClass.samples[0], "name"))
        self.assertEqual('b',
                         getattr(self.TransformerClass.samples[1], "name"))

    def test_multiple_pipeline_exception(self):
        self._reraise_exception = False
        self._break_pipeline_cfg()
        pipeline_manager = pipeline.PipelineManager(self.pipeline_cfg,
                                                    self.transformer_manager)

        with pipeline_manager.publisher(None) as p:
            p([self.test_counter])

        self.test_counter = sample.Sample(
            name='b',
            type=self.test_counter.type,
            volume=self.test_counter.volume,
            unit=self.test_counter.unit,
            user_id=self.test_counter.user_id,
            project_id=self.test_counter.project_id,
            resource_id=self.test_counter.resource_id,
            timestamp=self.test_counter.timestamp,
            resource_metadata=self.test_counter.resource_metadata,
        )

        with pipeline_manager.publisher(None) as p:
            p([self.test_counter])

        publisher = pipeline_manager.pipelines[0].publishers[0]
        self.assertEqual(1, publisher.calls)
        self.assertEqual(1, len(publisher.samples))
        self.assertEqual('a_update', getattr(publisher.samples[0], "name"))
        self.assertEqual(2, len(self.TransformerClass.samples))
        self.assertEqual('a',
                         getattr(self.TransformerClass.samples[0], "name"))
        self.assertEqual('b',
                         getattr(self.TransformerClass.samples[1], "name"))

    def test_none_transformer_pipeline(self):
        self._set_pipeline_cfg('transformers', None)
        pipeline_manager = pipeline.PipelineManager(self.pipeline_cfg,
                                                    self.transformer_manager)
        with pipeline_manager.publisher(None) as p:
            p([self.test_counter])
        publisher = pipeline_manager.pipelines[0].publishers[0]
        self.assertEqual(1, len(publisher.samples))
        self.assertEqual(1, publisher.calls)
        self.assertEqual('a', getattr(publisher.samples[0], 'name'))

    def test_empty_transformer_pipeline(self):
        self._set_pipeline_cfg('transformers', [])
        pipeline_manager = pipeline.PipelineManager(self.pipeline_cfg,
                                                    self.transformer_manager)
        with pipeline_manager.publisher(None) as p:
            p([self.test_counter])
        publisher = pipeline_manager.pipelines[0].publishers[0]
        self.assertEqual(1, len(publisher.samples))
        self.assertEqual(1, publisher.calls)
        self.assertEqual('a', getattr(publisher.samples[0], 'name'))

    def test_multiple_transformer_same_class(self):
        transformer_cfg = [
            {
                'name': 'update',
                'parameters': {}
            },
            {
                'name': 'update',
                'parameters': {}
            },
        ]
        self._set_pipeline_cfg('transformers', transformer_cfg)
        pipeline_manager = pipeline.PipelineManager(self.pipeline_cfg,
                                                    self.transformer_manager)

        with pipeline_manager.publisher(None) as p:
            p([self.test_counter])

        publisher = pipeline_manager.pipelines[0].publishers[0]
        self.assertEqual(1, publisher.calls)
        self.assertEqual(1, len(publisher.samples))
        self.assertEqual('a_update_update',
                         getattr(publisher.samples[0], 'name'))
        self.assertEqual(2, len(self.TransformerClass.samples))
        self.assertEqual('a',
                         getattr(self.TransformerClass.samples[0], 'name'))
        self.assertEqual('a_update',
                         getattr(self.TransformerClass.samples[1], 'name'))

    def test_multiple_transformer_same_class_different_parameter(self):
        transformer_cfg = [
            {
                'name': 'update',
                'parameters':
                {
                    "append_name": "_update",
                }
            },
            {
                'name': 'update',
                'parameters':
                {
                    "append_name": "_new",
                }
            },
        ]
        self._set_pipeline_cfg('transformers', transformer_cfg)
        pipeline_manager = pipeline.PipelineManager(self.pipeline_cfg,
                                                    self.transformer_manager)
        with pipeline_manager.publisher(None) as p:
            p([self.test_counter])

        self.assertEqual(2, len(self.TransformerClass.samples))
        self.assertEqual('a',
                         getattr(self.TransformerClass.samples[0], 'name'))
        self.assertEqual('a_update',
                         getattr(self.TransformerClass.samples[1], 'name'))
        publisher = pipeline_manager.pipelines[0].publishers[0]
        self.assertEqual(1,
                         len(publisher.samples))
        self.assertEqual('a_update_new',
                         getattr(publisher.samples[0], 'name'))

    def test_multiple_transformer_drop_transformer(self):
        transformer_cfg = [
            {
                'name': 'update',
                'parameters':
                {
                    "append_name": "_update",
                }
            },
            {
                'name': 'drop',
                'parameters': {}
            },
            {
                'name': 'update',
                'parameters':
                {
                    "append_name": "_new",
                }
            },
        ]
        self._set_pipeline_cfg('transformers', transformer_cfg)
        pipeline_manager = pipeline.PipelineManager(self.pipeline_cfg,
                                                    self.transformer_manager)
        with pipeline_manager.publisher(None) as p:
            p([self.test_counter])

        publisher = pipeline_manager.pipelines[0].publishers[0]
        self.assertEqual(0, len(publisher.samples))
        self.assertEqual(1, len(self.TransformerClass.samples))
        self.assertEqual('a',
                         getattr(self.TransformerClass.samples[0], 'name'))
        self.assertEqual(1,
                         len(self.TransformerClassDrop.samples))
        self.assertEqual('a_update',
                         getattr(self.TransformerClassDrop.samples[0], 'name'))

    def test_multiple_publisher(self):
        self._set_pipeline_cfg('publishers', ['test://', 'new://'])
        pipeline_manager = pipeline.PipelineManager(self.pipeline_cfg,
                                                    self.transformer_manager)

        with pipeline_manager.publisher(None) as p:
            p([self.test_counter])

        publisher = pipeline_manager.pipelines[0].publishers[0]
        new_publisher = pipeline_manager.pipelines[0].publishers[1]
        self.assertEqual(1, len(publisher.samples))
        self.assertEqual(1, len(new_publisher.samples))
        self.assertEqual('a_update',
                         getattr(new_publisher.samples[0], 'name'))
        self.assertEqual('a_update',
                         getattr(publisher.samples[0], 'name'))

    def test_multiple_publisher_isolation(self):
        self._reraise_exception = False
        self._set_pipeline_cfg('publishers', ['except://', 'new://'])
        pipeline_manager = pipeline.PipelineManager(self.pipeline_cfg,
                                                    self.transformer_manager)
        with pipeline_manager.publisher(None) as p:
            p([self.test_counter])

        new_publisher = pipeline_manager.pipelines[0].publishers[1]
        self.assertEqual(1, len(new_publisher.samples))
        self.assertEqual('a_update',
                         getattr(new_publisher.samples[0], 'name'))

    def test_multiple_counter_pipeline(self):
        self._set_pipeline_cfg('counters', ['a', 'b'])
        pipeline_manager = pipeline.PipelineManager(self.pipeline_cfg,
                                                    self.transformer_manager)
        with pipeline_manager.publisher(None) as p:
            p([self.test_counter,
               sample.Sample(
                   name='b',
                   type=self.test_counter.type,
                   volume=self.test_counter.volume,
                   unit=self.test_counter.unit,
                   user_id=self.test_counter.user_id,
                   project_id=self.test_counter.project_id,
                   resource_id=self.test_counter.resource_id,
                   timestamp=self.test_counter.timestamp,
                   resource_metadata=self.test_counter.resource_metadata,
               )])

        publisher = pipeline_manager.pipelines[0].publishers[0]
        self.assertEqual(2, len(publisher.samples))
        self.assertEqual('a_update', getattr(publisher.samples[0], 'name'))
        self.assertEqual('b_update', getattr(publisher.samples[1], 'name'))

    def test_flush_pipeline_cache(self):
        CACHE_SIZE = 10
        extra_transformer_cfg = [
            {
                'name': 'cache',
                'parameters': {
                    'size': CACHE_SIZE,
                }
            },
            {
                'name': 'update',
                'parameters':
                {
                    'append_name': '_new'
                }
            },
        ]
        self._extend_pipeline_cfg('transformers', extra_transformer_cfg)
        pipeline_manager = pipeline.PipelineManager(self.pipeline_cfg,
                                                    self.transformer_manager)
        pipe = pipeline_manager.pipelines[0]

        pipe.publish_data(None, self.test_counter)
        publisher = pipeline_manager.pipelines[0].publishers[0]
        self.assertEqual(0, len(publisher.samples))
        pipe.flush(None)
        self.assertEqual(0, len(publisher.samples))
        pipe.publish_data(None, self.test_counter)
        pipe.flush(None)
        self.assertEqual(0, len(publisher.samples))
        for i in range(CACHE_SIZE - 2):
            pipe.publish_data(None, self.test_counter)
        pipe.flush(None)
        self.assertEqual(CACHE_SIZE, len(publisher.samples))
        self.assertEqual('a_update_new', getattr(publisher.samples[0], 'name'))

    def test_flush_pipeline_cache_multiple_counter(self):
        CACHE_SIZE = 3
        extra_transformer_cfg = [
            {
                'name': 'cache',
                'parameters': {
                    'size': CACHE_SIZE
                }
            },
            {
                'name': 'update',
                'parameters':
                {
                    'append_name': '_new'
                }
            },
        ]
        self._extend_pipeline_cfg('transformers', extra_transformer_cfg)
        self._set_pipeline_cfg('counters', ['a', 'b'])
        pipeline_manager = pipeline.PipelineManager(self.pipeline_cfg,
                                                    self.transformer_manager)
        with pipeline_manager.publisher(None) as p:
            p([self.test_counter,
               sample.Sample(
                   name='b',
                   type=self.test_counter.type,
                   volume=self.test_counter.volume,
                   unit=self.test_counter.unit,
                   user_id=self.test_counter.user_id,
                   project_id=self.test_counter.project_id,
                   resource_id=self.test_counter.resource_id,
                   timestamp=self.test_counter.timestamp,
                   resource_metadata=self.test_counter.resource_metadata,
               )])

        publisher = pipeline_manager.pipelines[0].publishers[0]
        self.assertEqual(0, len(publisher.samples))

        with pipeline_manager.publisher(None) as p:
            p([self.test_counter])

        self.assertEqual(CACHE_SIZE, len(publisher.samples))
        self.assertEqual('a_update_new',
                         getattr(publisher.samples[0], 'name'))
        self.assertEqual('b_update_new',
                         getattr(publisher.samples[1], 'name'))

    def test_flush_pipeline_cache_before_publisher(self):
        extra_transformer_cfg = [{
            'name': 'cache',
            'parameters': {}
        }]
        self._extend_pipeline_cfg('transformers', extra_transformer_cfg)
        pipeline_manager = pipeline.PipelineManager(self.pipeline_cfg,
                                                    self.transformer_manager)
        pipe = pipeline_manager.pipelines[0]

        publisher = pipe.publishers[0]
        pipe.publish_data(None, self.test_counter)
        self.assertEqual(0, len(publisher.samples))
        pipe.flush(None)
        self.assertEqual(1, len(publisher.samples))
        self.assertEqual('a_update',
                         getattr(publisher.samples[0], 'name'))

    def test_global_unit_conversion(self):
        scale = 'volume / ((10**6) * 60)'
        transformer_cfg = [
            {
                'name': 'unit_conversion',
                'parameters': {
                    'source': {},
                    'target': {'name': 'cpu_mins',
                               'unit': 'min',
                               'scale': scale},
                }
            },
        ]
        self._set_pipeline_cfg('transformers', transformer_cfg)
        self._set_pipeline_cfg('counters', ['cpu'])
        counters = [
            sample.Sample(
                name='cpu',
                type=sample.TYPE_CUMULATIVE,
                volume=1200000000,
                unit='ns',
                user_id='test_user',
                project_id='test_proj',
                resource_id='test_resource',
                timestamp=timeutils.utcnow().isoformat(),
                resource_metadata={}
            ),
        ]

        pipeline_manager = pipeline.PipelineManager(self.pipeline_cfg,
                                                    self.transformer_manager)
        pipe = pipeline_manager.pipelines[0]

        pipe.publish_data(None, counters)
        publisher = pipeline_manager.pipelines[0].publishers[0]
        self.assertEqual(1, len(publisher.samples))
        pipe.flush(None)
        self.assertEqual(1, len(publisher.samples))
        cpu_mins = publisher.samples[-1]
        self.assertEqual('cpu_mins', getattr(cpu_mins, 'name'))
        self.assertEqual('min', getattr(cpu_mins, 'unit'))
        self.assertEqual(sample.TYPE_CUMULATIVE, getattr(cpu_mins, 'type'))
        self.assertEqual(20, getattr(cpu_mins, 'volume'))

    def test_unit_identified_source_unit_conversion(self):
        transformer_cfg = [
            {
                'name': 'unit_conversion',
                'parameters': {
                    'source': {'unit': '°C'},
                    'target': {'unit': '°F',
                               'scale': '(volume * 1.8) + 32'},
                }
            },
        ]
        self._set_pipeline_cfg('transformers', transformer_cfg)
        self._set_pipeline_cfg('counters', ['core_temperature',
                                            'ambient_temperature'])
        counters = [
            sample.Sample(
                name='core_temperature',
                type=sample.TYPE_GAUGE,
                volume=36.0,
                unit='°C',
                user_id='test_user',
                project_id='test_proj',
                resource_id='test_resource',
                timestamp=timeutils.utcnow().isoformat(),
                resource_metadata={}
            ),
            sample.Sample(
                name='ambient_temperature',
                type=sample.TYPE_GAUGE,
                volume=88.8,
                unit='°F',
                user_id='test_user',
                project_id='test_proj',
                resource_id='test_resource',
                timestamp=timeutils.utcnow().isoformat(),
                resource_metadata={}
            ),
        ]

        pipeline_manager = pipeline.PipelineManager(self.pipeline_cfg,
                                                    self.transformer_manager)
        pipe = pipeline_manager.pipelines[0]

        pipe.publish_data(None, counters)
        publisher = pipeline_manager.pipelines[0].publishers[0]
        self.assertEqual(2, len(publisher.samples))
        core_temp = publisher.samples[0]
        self.assertEqual('core_temperature', getattr(core_temp, 'name'))
        self.assertEqual('°F', getattr(core_temp, 'unit'))
        self.assertEqual(96.8, getattr(core_temp, 'volume'))
        amb_temp = publisher.samples[1]
        self.assertEqual('ambient_temperature', getattr(amb_temp, 'name'))
        self.assertEqual('°F', getattr(amb_temp, 'unit'))
        self.assertEqual(88.8, getattr(amb_temp, 'volume'))
        self.assertEqual(96.8, getattr(core_temp, 'volume'))

    def _do_test_rate_of_change_conversion(self, prev, curr, type, expected,
                                           offset=1, weight=None):
        s = ("(resource_metadata.user_metadata.autoscaling_weight or 1.0)"
             "* (resource_metadata.non.existent or 1.0)"
             "* (100.0 / (10**9 * (resource_metadata.cpu_number or 1)))")
        transformer_cfg = [
            {
                'name': 'rate_of_change',
                'parameters': {
                    'source': {},
                    'target': {'name': 'cpu_util',
                               'unit': '%',
                               'type': sample.TYPE_GAUGE,
                               'scale': s},
                }
            },
        ]
        self._set_pipeline_cfg('transformers', transformer_cfg)
        self._set_pipeline_cfg('counters', ['cpu'])
        now = timeutils.utcnow()
        later = now + datetime.timedelta(minutes=offset)
        um = {'autoscaling_weight': weight} if weight else {}
        counters = [
            sample.Sample(
                name='cpu',
                type=type,
                volume=prev,
                unit='ns',
                user_id='test_user',
                project_id='test_proj',
                resource_id='test_resource',
                timestamp=now.isoformat(),
                resource_metadata={'cpu_number': 4,
                                   'user_metadata': um},
            ),
            sample.Sample(
                name='cpu',
                type=type,
                volume=prev,
                unit='ns',
                user_id='test_user',
                project_id='test_proj',
                resource_id='test_resource2',
                timestamp=now.isoformat(),
                resource_metadata={'cpu_number': 2,
                                   'user_metadata': um},
            ),
            sample.Sample(
                name='cpu',
                type=type,
                volume=curr,
                unit='ns',
                user_id='test_user',
                project_id='test_proj',
                resource_id='test_resource',
                timestamp=later.isoformat(),
                resource_metadata={'cpu_number': 4,
                                   'user_metadata': um},
            ),
            sample.Sample(
                name='cpu',
                type=type,
                volume=curr,
                unit='ns',
                user_id='test_user',
                project_id='test_proj',
                resource_id='test_resource2',
                timestamp=later.isoformat(),
                resource_metadata={'cpu_number': 2,
                                   'user_metadata': um},
            ),
        ]

        pipeline_manager = pipeline.PipelineManager(self.pipeline_cfg,
                                                    self.transformer_manager)
        pipe = pipeline_manager.pipelines[0]

        pipe.publish_data(None, counters)
        publisher = pipeline_manager.pipelines[0].publishers[0]
        self.assertEqual(2, len(publisher.samples))
        pipe.flush(None)
        self.assertEqual(2, len(publisher.samples))
        cpu_util = publisher.samples[0]
        self.assertEqual('cpu_util', getattr(cpu_util, 'name'))
        self.assertEqual('test_resource', getattr(cpu_util, 'resource_id'))
        self.assertEqual('%', getattr(cpu_util, 'unit'))
        self.assertEqual(sample.TYPE_GAUGE, getattr(cpu_util, 'type'))
        self.assertEqual(expected, getattr(cpu_util, 'volume'))
        cpu_util = publisher.samples[1]
        self.assertEqual('cpu_util', getattr(cpu_util, 'name'))
        self.assertEqual('test_resource2', getattr(cpu_util, 'resource_id'))
        self.assertEqual('%', getattr(cpu_util, 'unit'))
        self.assertEqual(sample.TYPE_GAUGE, getattr(cpu_util, 'type'))
        self.assertEqual(expected * 2, getattr(cpu_util, 'volume'))

    def test_rate_of_change_conversion(self):
        self._do_test_rate_of_change_conversion(120000000000,
                                                180000000000,
                                                sample.TYPE_CUMULATIVE,
                                                25.0)

    def test_rate_of_change_conversion_weight(self):
        self._do_test_rate_of_change_conversion(120000000000,
                                                180000000000,
                                                sample.TYPE_CUMULATIVE,
                                                27.5,
                                                weight=1.1)

    def test_rate_of_change_conversion_negative_cumulative_delta(self):
        self._do_test_rate_of_change_conversion(180000000000,
                                                120000000000,
                                                sample.TYPE_CUMULATIVE,
                                                50.0)

    def test_rate_of_change_conversion_negative_gauge_delta(self):
        self._do_test_rate_of_change_conversion(180000000000,
                                                120000000000,
                                                sample.TYPE_GAUGE,
                                                -25.0)

    def test_rate_of_change_conversion_zero_delay(self):
        self._do_test_rate_of_change_conversion(120000000000,
                                                120000000000,
                                                sample.TYPE_CUMULATIVE,
                                                0.0,
                                                offset=0)

    def test_rate_of_change_no_predecessor(self):
        s = "100.0 / (10**9 * (resource_metadata.cpu_number or 1))"
        transformer_cfg = [
            {
                'name': 'rate_of_change',
                'parameters': {
                    'source': {},
                    'target': {'name': 'cpu_util',
                               'unit': '%',
                               'type': sample.TYPE_GAUGE,
                               'scale': s}
                }
            },
        ]
        self._set_pipeline_cfg('transformers', transformer_cfg)
        self._set_pipeline_cfg('counters', ['cpu'])
        now = timeutils.utcnow()
        counters = [
            sample.Sample(
                name='cpu',
                type=sample.TYPE_CUMULATIVE,
                volume=120000000000,
                unit='ns',
                user_id='test_user',
                project_id='test_proj',
                resource_id='test_resource',
                timestamp=now.isoformat(),
                resource_metadata={'cpu_number': 4}
            ),
        ]

        pipeline_manager = pipeline.PipelineManager(self.pipeline_cfg,
                                                    self.transformer_manager)
        pipe = pipeline_manager.pipelines[0]

        pipe.publish_data(None, counters)
        publisher = pipeline_manager.pipelines[0].publishers[0]
        self.assertEqual(0, len(publisher.samples))
        pipe.flush(None)
        self.assertEqual(0, len(publisher.samples))

    @mock.patch('ceilometer.transformer.conversions.LOG')
    def test_rate_of_change_out_of_order(self, the_log):
        s = "100.0 / (10**9 * (resource_metadata.cpu_number or 1))"
        transformer_cfg = [
            {
                'name': 'rate_of_change',
                'parameters': {
                    'source': {},
                    'target': {'name': 'cpu_util',
                               'unit': '%',
                               'type': sample.TYPE_GAUGE,
                               'scale': s}
                }
            },
        ]
        self._set_pipeline_cfg('transformers', transformer_cfg)
        self._set_pipeline_cfg('counters', ['cpu'])
        pipeline_manager = pipeline.PipelineManager(self.pipeline_cfg,
                                                    self.transformer_manager)
        pipe = pipeline_manager.pipelines[0]

        now = timeutils.utcnow()
        earlier = now - datetime.timedelta(seconds=10)
        later = now + datetime.timedelta(seconds=10)

        counters = [
            sample.Sample(
                name='cpu',
                type=sample.TYPE_CUMULATIVE,
                volume=125000000000,
                unit='ns',
                user_id='test_user',
                project_id='test_proj',
                resource_id='test_resource',
                timestamp=now.isoformat(),
                resource_metadata={'cpu_number': 4}
            ),
            sample.Sample(
                name='cpu',
                type=sample.TYPE_CUMULATIVE,
                volume=120000000000,
                unit='ns',
                user_id='test_user',
                project_id='test_proj',
                resource_id='test_resource',
                timestamp=earlier.isoformat(),
                resource_metadata={'cpu_number': 4}
            ),
            sample.Sample(
                name='cpu',
                type=sample.TYPE_CUMULATIVE,
                volume=130000000000,
                unit='ns',
                user_id='test_user',
                project_id='test_proj',
                resource_id='test_resource',
                timestamp=later.isoformat(),
                resource_metadata={'cpu_number': 4}
            ),
        ]

        pipe.publish_data(None, counters)
        publisher = pipe.publishers[0]
        self.assertEqual(1, len(publisher.samples))
        pipe.flush(None)
        self.assertEqual(1, len(publisher.samples))

        cpu_util_sample = publisher.samples[0]
        self.assertEqual(12.5, cpu_util_sample.volume)
        the_log.warning.assert_called_with(
            'dropping out of time order sample: %s',
            (counters[1],)
        )

    def test_resources(self):
        resources = ['test1://', 'test2://']
        self._set_pipeline_cfg('resources', resources)
        pipeline_manager = pipeline.PipelineManager(self.pipeline_cfg,
                                                    self.transformer_manager)
        self.assertEqual(resources,
                         pipeline_manager.pipelines[0].resources)

    def test_no_resources(self):
        pipeline_manager = pipeline.PipelineManager(self.pipeline_cfg,
                                                    self.transformer_manager)
        self.assertEqual(0, len(pipeline_manager.pipelines[0].resources))

    def _do_test_rate_of_change_mapping(self, pipe, meters, units):
        now = timeutils.utcnow()
        base = 1000
        offset = 7
        rate = 42
        later = now + datetime.timedelta(minutes=offset)
        counters = []
        for v, ts in [(base, now.isoformat()),
                      (base + (offset * 60 * rate), later.isoformat())]:
            for n, u, r in [(meters[0], units[0], 'resource1'),
                            (meters[1], units[1], 'resource2')]:
                s = sample.Sample(
                    name=n,
                    type=sample.TYPE_CUMULATIVE,
                    volume=v,
                    unit=u,
                    user_id='test_user',
                    project_id='test_proj',
                    resource_id=r,
                    timestamp=ts,
                    resource_metadata={},
                )
                counters.append(s)

        pipe.publish_data(None, counters)
        publisher = pipe.publishers[0]
        self.assertEqual(2, len(publisher.samples))
        pipe.flush(None)
        self.assertEqual(2, len(publisher.samples))
        bps = publisher.samples[0]
        self.assertEqual('%s.rate' % meters[0], getattr(bps, 'name'))
        self.assertEqual('resource1', getattr(bps, 'resource_id'))
        self.assertEqual('%s/s' % units[0], getattr(bps, 'unit'))
        self.assertEqual(sample.TYPE_GAUGE, getattr(bps, 'type'))
        self.assertEqual(rate, getattr(bps, 'volume'))
        rps = publisher.samples[1]
        self.assertEqual('%s.rate' % meters[1], getattr(rps, 'name'))
        self.assertEqual('resource2', getattr(rps, 'resource_id'))
        self.assertEqual('%s/s' % units[1], getattr(rps, 'unit'))
        self.assertEqual(sample.TYPE_GAUGE, getattr(rps, 'type'))
        self.assertEqual(rate, getattr(rps, 'volume'))

    def test_rate_of_change_mapping(self):
        map_from = {'name': 'disk\\.(read|write)\\.(bytes|requests)',
                    'unit': '(B|request)'}
        map_to = {'name': 'disk.\\1.\\2.rate',
                  'unit': '\\1/s'}
        transformer_cfg = [
            {
                'name': 'rate_of_change',
                'parameters': {
                    'source': {
                        'map_from': map_from
                    },
                    'target': {
                        'map_to': map_to,
                        'type': sample.TYPE_GAUGE
                    },
                },
            },
        ]
        self._set_pipeline_cfg('transformers', transformer_cfg)
        self._set_pipeline_cfg('counters', ['disk.read.bytes',
                                            'disk.write.requests'])
        pipeline_manager = pipeline.PipelineManager(self.pipeline_cfg,
                                                    self.transformer_manager)
        pipe = pipeline_manager.pipelines[0]
        meters = ('disk.read.bytes', 'disk.write.requests')
        units = ('B', 'request')
        self._do_test_rate_of_change_mapping(pipe, meters, units)

    def _do_test_aggregator(self, parameters, expected_length):
        transformer_cfg = [
            {
                'name': 'aggregator',
                'parameters': parameters,
            },
        ]
        self._set_pipeline_cfg('transformers', transformer_cfg)
        self._set_pipeline_cfg('counters', ['storage.objects.incoming.bytes'])
        counters = [
            sample.Sample(
                name='storage.objects.incoming.bytes',
                type=sample.TYPE_DELTA,
                volume=26,
                unit='B',
                user_id='test_user',
                project_id='test_proj',
                resource_id='test_resource',
                timestamp=timeutils.utcnow().isoformat(),
                resource_metadata={'version': '1.0'}
            ),
            sample.Sample(
                name='storage.objects.incoming.bytes',
                type=sample.TYPE_DELTA,
                volume=16,
                unit='B',
                user_id='test_user',
                project_id='test_proj',
                resource_id='test_resource',
                timestamp=timeutils.utcnow().isoformat(),
                resource_metadata={'version': '2.0'}
            ),
            sample.Sample(
                name='storage.objects.incoming.bytes',
                type=sample.TYPE_DELTA,
                volume=53,
                unit='B',
                user_id='test_user_bis',
                project_id='test_proj_bis',
                resource_id='test_resource',
                timestamp=timeutils.utcnow().isoformat(),
                resource_metadata={'version': '1.0'}
            ),
            sample.Sample(
                name='storage.objects.incoming.bytes',
                type=sample.TYPE_DELTA,
                volume=42,
                unit='B',
                user_id='test_user_bis',
                project_id='test_proj_bis',
                resource_id='test_resource',
                timestamp=timeutils.utcnow().isoformat(),
                resource_metadata={'version': '2.0'}
            ),
            sample.Sample(
                name='storage.objects.incoming.bytes',
                type=sample.TYPE_DELTA,
                volume=15,
                unit='B',
                user_id='test_user',
                project_id='test_proj_bis',
                resource_id='test_resource',
                timestamp=timeutils.utcnow().isoformat(),
                resource_metadata={'version': '2.0'}
            ),
            sample.Sample(
                name='storage.objects.incoming.bytes',
                type=sample.TYPE_DELTA,
                volume=2,
                unit='B',
                user_id='test_user_bis',
                project_id='test_proj',
                resource_id='test_resource',
                timestamp=timeutils.utcnow().isoformat(),
                resource_metadata={'version': '3.0'}
            ),
        ]

        pipeline_manager = pipeline.PipelineManager(self.pipeline_cfg,
                                                    self.transformer_manager)
        pipe = pipeline_manager.pipelines[0]

        pipe.publish_data(None, counters)
        pipe.flush(None)
        publisher = pipeline_manager.pipelines[0].publishers[0]
        self.assertEqual(expected_length, len(publisher.samples))
        return sorted(publisher.samples, key=lambda s: s.volume)

    def test_aggregator_meter_type(self):
        volumes = [1.0, 2.0, 3.0]
        transformer_cfg = [
            {
                'name': 'aggregator',
                'parameters': {'size': len(volumes) * len(sample.TYPES)}
            },
        ]
        self._set_pipeline_cfg('transformers', transformer_cfg)
        self._set_pipeline_cfg('counters',
                               ['testgauge', 'testcumulative', 'testdelta'])
        counters = []
        for sample_type in sample.TYPES:
            for volume in volumes:
                counters.append(sample.Sample(
                    name='test' + sample_type,
                    type=sample_type,
                    volume=volume,
                    unit='B',
                    user_id='test_user',
                    project_id='test_proj',
                    resource_id='test_resource',
                    timestamp=timeutils.utcnow().isoformat(),
                    resource_metadata={'version': '1.0'}
                ))

        pipeline_manager = pipeline.PipelineManager(self.pipeline_cfg,
                                                    self.transformer_manager)
        pipe = pipeline_manager.pipelines[0]

        pipe.publish_data(None, counters)
        pipe.flush(None)
        publisher = pipeline_manager.pipelines[0].publishers[0]
        actual = sorted(s.volume for s in publisher.samples)
        self.assertEqual([2.0, 3.0, 6.0], actual)

    def test_aggregator_metadata(self):
        for conf, expected_version in [('last', '2.0'), ('first', '1.0')]:
            samples = self._do_test_aggregator({
                'resource_metadata': conf,
                'target': {'name': 'aggregated-bytes'}
            }, expected_length=4)
            s = samples[0]
            self.assertEqual('aggregated-bytes', s.name)
            self.assertEqual(2, s.volume)
            self.assertEqual('test_user_bis', s.user_id)
            self.assertEqual('test_proj', s.project_id)
            self.assertEqual({'version': '3.0'},
                             s.resource_metadata)
            s = samples[1]
            self.assertEqual('aggregated-bytes', s.name)
            self.assertEqual(15, s.volume)
            self.assertEqual('test_user', s.user_id)
            self.assertEqual('test_proj_bis', s.project_id)
            self.assertEqual({'version': '2.0'},
                             s.resource_metadata)
            s = samples[2]
            self.assertEqual('aggregated-bytes', s.name)
            self.assertEqual(42, s.volume)
            self.assertEqual('test_user', s.user_id)
            self.assertEqual('test_proj', s.project_id)
            self.assertEqual({'version': expected_version},
                             s.resource_metadata)
            s = samples[3]
            self.assertEqual('aggregated-bytes', s.name)
            self.assertEqual(95, s.volume)
            self.assertEqual('test_user_bis', s.user_id)
            self.assertEqual('test_proj_bis', s.project_id)
            self.assertEqual({'version': expected_version},
                             s.resource_metadata)

    def test_aggregator_user_last_and_metadata_last(self):
        samples = self._do_test_aggregator({
            'resource_metadata': 'last',
            'user_id': 'last',
            'target': {'name': 'aggregated-bytes'}
        }, expected_length=2)
        s = samples[0]
        self.assertEqual('aggregated-bytes', s.name)
        self.assertEqual(44, s.volume)
        self.assertEqual('test_user_bis', s.user_id)
        self.assertEqual('test_proj', s.project_id)
        self.assertEqual({'version': '3.0'},
                         s.resource_metadata)
        s = samples[1]
        self.assertEqual('aggregated-bytes', s.name)
        self.assertEqual(110, s.volume)
        self.assertEqual('test_user', s.user_id)
        self.assertEqual('test_proj_bis', s.project_id)
        self.assertEqual({'version': '2.0'},
                         s.resource_metadata)

    def test_aggregator_user_first_and_metadata_last(self):
        samples = self._do_test_aggregator({
            'resource_metadata': 'last',
            'user_id': 'first',
            'target': {'name': 'aggregated-bytes'}
        }, expected_length=2)
        s = samples[0]
        self.assertEqual('aggregated-bytes', s.name)
        self.assertEqual(44, s.volume)
        self.assertEqual('test_user', s.user_id)
        self.assertEqual('test_proj', s.project_id)
        self.assertEqual({'version': '3.0'},
                         s.resource_metadata)
        s = samples[1]
        self.assertEqual('aggregated-bytes', s.name)
        self.assertEqual(110, s.volume)
        self.assertEqual('test_user_bis', s.user_id)
        self.assertEqual('test_proj_bis', s.project_id)
        self.assertEqual({'version': '2.0'},
                         s.resource_metadata)

    def test_aggregator_all_first(self):
        samples = self._do_test_aggregator({
            'resource_metadata': 'first',
            'user_id': 'first',
            'project_id': 'first',
            'target': {'name': 'aggregated-bytes'}
        }, expected_length=1)
        s = samples[0]
        self.assertEqual('aggregated-bytes', s.name)
        self.assertEqual(154, s.volume)
        self.assertEqual('test_user', s.user_id)
        self.assertEqual('test_proj', s.project_id)
        self.assertEqual({'version': '1.0'},
                         s.resource_metadata)

    def test_aggregator_all_last(self):
        samples = self._do_test_aggregator({
            'resource_metadata': 'last',
            'user_id': 'last',
            'project_id': 'last',
            'target': {'name': 'aggregated-bytes'}
        }, expected_length=1)
        s = samples[0]
        self.assertEqual('aggregated-bytes', s.name)
        self.assertEqual(154, s.volume)
        self.assertEqual('test_user_bis', s.user_id)
        self.assertEqual('test_proj', s.project_id)
        self.assertEqual({'version': '3.0'},
                         s.resource_metadata)

    def test_aggregator_all_mixed(self):
        samples = self._do_test_aggregator({
            'resource_metadata': 'drop',
            'user_id': 'first',
            'project_id': 'last',
            'target': {'name': 'aggregated-bytes'}
        }, expected_length=1)
        s = samples[0]
        self.assertEqual('aggregated-bytes', s.name)
        self.assertEqual(154, s.volume)
        self.assertEqual('test_user', s.user_id)
        self.assertEqual('test_proj', s.project_id)
        self.assertEqual({}, s.resource_metadata)

    def test_aggregator_metadata_default(self):
        samples = self._do_test_aggregator({
            'user_id': 'last',
            'project_id': 'last',
            'target': {'name': 'aggregated-bytes'}
        }, expected_length=1)
        s = samples[0]
        self.assertEqual('aggregated-bytes', s.name)
        self.assertEqual(154, s.volume)
        self.assertEqual('test_user_bis', s.user_id)
        self.assertEqual('test_proj', s.project_id)
        self.assertEqual({'version': '3.0'},
                         s.resource_metadata)

    @mock.patch('ceilometer.transformer.conversions.LOG')
    def test_aggregator_metadata_invalid(self, mylog):
        samples = self._do_test_aggregator({
            'resource_metadata': 'invalid',
            'user_id': 'last',
            'project_id': 'last',
            'target': {'name': 'aggregated-bytes'}
        }, expected_length=1)
        s = samples[0]
        self.assertTrue(mylog.warning.called)
        self.assertEqual('aggregated-bytes', s.name)
        self.assertEqual(154, s.volume)
        self.assertEqual('test_user_bis', s.user_id)
        self.assertEqual('test_proj', s.project_id)
        self.assertEqual({'version': '3.0'},
                         s.resource_metadata)

    def test_aggregator_sized_flush(self):
        transformer_cfg = [
            {
                'name': 'aggregator',
                'parameters': {'size': 2},
            },
        ]
        self._set_pipeline_cfg('transformers', transformer_cfg)
        self._set_pipeline_cfg('counters', ['storage.objects.incoming.bytes'])
        counters = [
            sample.Sample(
                name='storage.objects.incoming.bytes',
                type=sample.TYPE_DELTA,
                volume=26,
                unit='B',
                user_id='test_user',
                project_id='test_proj',
                resource_id='test_resource',
                timestamp=timeutils.utcnow().isoformat(),
                resource_metadata={'version': '1.0'}
            ),
            sample.Sample(
                name='storage.objects.incoming.bytes',
                type=sample.TYPE_DELTA,
                volume=16,
                unit='B',
                user_id='test_user_bis',
                project_id='test_proj_bis',
                resource_id='test_resource',
                timestamp=timeutils.utcnow().isoformat(),
                resource_metadata={'version': '2.0'}
            )
        ]

        pipeline_manager = pipeline.PipelineManager(self.pipeline_cfg,
                                                    self.transformer_manager)
        pipe = pipeline_manager.pipelines[0]

        pipe.publish_data(None, [counters[0]])
        pipe.flush(None)
        publisher = pipe.publishers[0]
        self.assertEqual(0, len(publisher.samples))

        pipe.publish_data(None, [counters[1]])
        pipe.flush(None)
        publisher = pipe.publishers[0]
        self.assertEqual(2, len(publisher.samples))

    def test_aggregator_timed_flush(self):
        timeutils.set_time_override()
        transformer_cfg = [
            {
                'name': 'aggregator',
                'parameters': {'size': 900, 'retention_time': 60},
            },
        ]
        self._set_pipeline_cfg('transformers', transformer_cfg)
        self._set_pipeline_cfg('counters', ['storage.objects.incoming.bytes'])
        counters = [
            sample.Sample(
                name='storage.objects.incoming.bytes',
                type=sample.TYPE_DELTA,
                volume=26,
                unit='B',
                user_id='test_user',
                project_id='test_proj',
                resource_id='test_resource',
                timestamp=timeutils.utcnow().isoformat(),
                resource_metadata={'version': '1.0'}
            ),
        ]

        pipeline_manager = pipeline.PipelineManager(self.pipeline_cfg,
                                                    self.transformer_manager)
        pipe = pipeline_manager.pipelines[0]

        pipe.publish_data(None, counters)
        pipe.flush(None)
        publisher = pipeline_manager.pipelines[0].publishers[0]
        self.assertEqual(0, len(publisher.samples))

        timeutils.advance_time_seconds(120)
        pipe.flush(None)
        publisher = pipeline_manager.pipelines[0].publishers[0]
        self.assertEqual(1, len(publisher.samples))

    def test_aggregator_without_authentication(self):
        transformer_cfg = [
            {
                'name': 'aggregator',
                'parameters': {'size': 2},
            },
        ]
        self._set_pipeline_cfg('transformers', transformer_cfg)
        self._set_pipeline_cfg('counters', ['storage.objects.outgoing.bytes'])
        counters = [
            sample.Sample(
                name='storage.objects.outgoing.bytes',
                type=sample.TYPE_DELTA,
                volume=26,
                unit='B',
                user_id=None,
                project_id=None,
                resource_id='test_resource',
                timestamp=timeutils.utcnow().isoformat(),
                resource_metadata={'version': '1.0'}
            ),
            sample.Sample(
                name='storage.objects.outgoing.bytes',
                type=sample.TYPE_DELTA,
                volume=16,
                unit='B',
                user_id=None,
                project_id=None,
                resource_id='test_resource',
                timestamp=timeutils.utcnow().isoformat(),
                resource_metadata={'version': '2.0'}
            )
        ]

        pipeline_manager = pipeline.PipelineManager(self.pipeline_cfg,
                                                    self.transformer_manager)
        pipe = pipeline_manager.pipelines[0]

        pipe.publish_data(None, [counters[0]])
        pipe.flush(None)
        publisher = pipe.publishers[0]
        self.assertEqual(0, len(publisher.samples))

        pipe.publish_data(None, [counters[1]])
        pipe.flush(None)
        publisher = pipe.publishers[0]

        self.assertEqual(1, len(publisher.samples))
        self.assertEqual(42, getattr(publisher.samples[0], 'volume'))
        self.assertEqual("test_resource", getattr(publisher.samples[0],
                                                  'resource_id'))

    def _do_test_arithmetic_expr_parse(self, expr, expected):
        actual = arithmetic.ArithmeticTransformer.parse_expr(expr)
        self.assertEqual(expected, actual)

    def test_arithmetic_expr_parse(self):
        expr = '$(cpu) + $(cpu.util)'
        expected = ('cpu.volume + _cpu_util_ESC.volume',
                    {
                        'cpu': 'cpu',
                        'cpu.util': '_cpu_util_ESC'
                    })
        self._do_test_arithmetic_expr_parse(expr, expected)

    def test_arithmetic_expr_parse_parameter(self):
        expr = '$(cpu) + $(cpu.util).resource_metadata'
        expected = ('cpu.volume + _cpu_util_ESC.resource_metadata',
                    {
                        'cpu': 'cpu',
                        'cpu.util': '_cpu_util_ESC'
                    })
        self._do_test_arithmetic_expr_parse(expr, expected)

    def test_arithmetic_expr_parse_reserved_keyword(self):
        expr = '$(class) + $(cpu.util)'
        expected = ('_class_ESC.volume + _cpu_util_ESC.volume',
                    {
                        'class': '_class_ESC',
                        'cpu.util': '_cpu_util_ESC'
                    })
        self._do_test_arithmetic_expr_parse(expr, expected)

    def test_arithmetic_expr_parse_already_escaped(self):
        expr = '$(class) + $(_class_ESC)'
        expected = ('_class_ESC.volume + __class_ESC_ESC.volume',
                    {
                        'class': '_class_ESC',
                        '_class_ESC': '__class_ESC_ESC'
                    })
        self._do_test_arithmetic_expr_parse(expr, expected)

    def _do_test_arithmetic(self, expression, scenario, expected):
        transformer_cfg = [
            {
                'name': 'arithmetic',
                'parameters': {
                    'target': {'name': 'new_meter',
                               'unit': '%',
                               'type': sample.TYPE_GAUGE,
                               'expr': expression},
                }
            },
        ]
        self._set_pipeline_cfg('transformers', transformer_cfg)
        self._set_pipeline_cfg('counters',
                               list(set(s['name'] for s in scenario)))
        counters = []
        test_resources = ['test_resource1', 'test_resource2']
        for resource_id in test_resources:
            for s in scenario:
                counters.append(sample.Sample(
                    name=s['name'],
                    type=sample.TYPE_CUMULATIVE,
                    volume=s['volume'],
                    unit='ns',
                    user_id='test_user',
                    project_id='test_proj',
                    resource_id=resource_id,
                    timestamp=timeutils.utcnow().isoformat(),
                    resource_metadata=s.get('metadata')
                ))

        pipeline_manager = pipeline.PipelineManager(self.pipeline_cfg,
                                                    self.transformer_manager)
        pipe = pipeline_manager.pipelines[0]
        for s in counters:
            pipe.publish_data(None, s)
            pipe.flush(None)
        publisher = pipeline_manager.pipelines[0].publishers[0]
        expected_len = len(test_resources) * len(expected)
        self.assertEqual(expected_len, len(publisher.samples))

        # bucket samples by resource first
        samples_by_resource = dict((r, []) for r in test_resources)
        for s in publisher.samples:
            samples_by_resource[s.resource_id].append(s)

        for resource_id in samples_by_resource:
            self.assertEqual(len(expected),
                             len(samples_by_resource[resource_id]))
            for i, s in enumerate(samples_by_resource[resource_id]):
                self.assertEqual('new_meter', getattr(s, 'name'))
                self.assertEqual(resource_id, getattr(s, 'resource_id'))
                self.assertEqual('%', getattr(s, 'unit'))
                self.assertEqual(sample.TYPE_GAUGE, getattr(s, 'type'))
                self.assertEqual(expected[i], getattr(s, 'volume'))

    def test_arithmetic_transformer(self):
        expression = '100.0 * $(memory.usage) / $(memory)'
        scenario = [
            dict(name='memory', volume=1024.0),
            dict(name='memory.usage', volume=512.0),
        ]
        expected = [50.0]
        self._do_test_arithmetic(expression, scenario, expected)

    def test_arithmetic_transformer_expr_empty(self):
        expression = ''
        scenario = [
            dict(name='memory', volume=1024.0),
            dict(name='memory.usage', volume=512.0),
        ]
        expected = []
        self._do_test_arithmetic(expression, scenario, expected)

    def test_arithmetic_transformer_expr_misconfigured(self):
        expression = '512.0 * 3'
        scenario = [
            dict(name='memory', volume=1024.0),
            dict(name='memory.usage', volume=512.0),
        ]
        expected = []
        self._do_test_arithmetic(expression, scenario, expected)

    def test_arithmetic_transformer_nan(self):
        expression = 'float(\'nan\') * $(memory.usage) / $(memory)'
        scenario = [
            dict(name='memory', volume=1024.0),
            dict(name='memory.usage', volume=512.0),
        ]
        expected = []
        self._do_test_arithmetic(expression, scenario, expected)

    def test_arithmetic_transformer_exception(self):
        expression = '$(memory) / 0'
        scenario = [
            dict(name='memory', volume=1024.0),
            dict(name='memory.usage', volume=512.0),
        ]
        expected = []
        self._do_test_arithmetic(expression, scenario, expected)

    def test_arithmetic_transformer_multiple_samples(self):
        expression = '100.0 * $(memory.usage) / $(memory)'
        scenario = [
            dict(name='memory', volume=2048.0),
            dict(name='memory.usage', volume=512.0),
            dict(name='memory', volume=1024.0),
        ]
        expected = [25.0]
        self._do_test_arithmetic(expression, scenario, expected)

    def test_arithmetic_transformer_missing(self):
        expression = '100.0 * $(memory.usage) / $(memory)'
        scenario = [dict(name='memory.usage', volume=512.0)]
        expected = []
        self._do_test_arithmetic(expression, scenario, expected)

    def test_arithmetic_transformer_more_than_needed(self):
        expression = '100.0 * $(memory.usage) / $(memory)'
        scenario = [
            dict(name='memory', volume=1024.0),
            dict(name='memory.usage', volume=512.0),
            dict(name='cpu_util', volume=90.0),
        ]
        expected = [50.0]
        self._do_test_arithmetic(expression, scenario, expected)

    def test_arithmetic_transformer_cache_cleared(self):
        transformer_cfg = [
            {
                'name': 'arithmetic',
                'parameters': {
                    'target': {'name': 'new_meter',
                               'expr': '$(memory.usage) + 2'}
                }
            },
        ]
        self._set_pipeline_cfg('transformers', transformer_cfg)
        self._set_pipeline_cfg('counters', ['memory.usage'])
        counter = sample.Sample(
            name='memory.usage',
            type=sample.TYPE_GAUGE,
            volume=1024.0,
            unit='MB',
            user_id='test_user',
            project_id='test_proj',
            resource_id='test_resource',
            timestamp=timeutils.utcnow().isoformat(),
            resource_metadata=None
        )

        pipeline_manager = pipeline.PipelineManager(self.pipeline_cfg,
                                                    self.transformer_manager)
        pipe = pipeline_manager.pipelines[0]

        pipe.publish_data(None, [counter])
        publisher = pipeline_manager.pipelines[0].publishers[0]
        self.assertEqual(0, len(publisher.samples))
        pipe.flush(None)
        self.assertEqual(1, len(publisher.samples))
        self.assertEqual(1026.0, publisher.samples[0].volume)

        pipe.flush(None)
        self.assertEqual(1, len(publisher.samples))

        counter.volume = 2048.0
        pipe.publish_data(None, [counter])
        pipe.flush(None)
        self.assertEqual(2, len(publisher.samples))
        self.assertEqual(2050.0, publisher.samples[1].volume)

    def test_aggregator_timed_flush_no_matching_samples(self):
        timeutils.set_time_override()
        transformer_cfg = [
            {
                'name': 'aggregator',
                'parameters': {'size': 900, 'retention_time': 60},
            },
        ]
        self._set_pipeline_cfg('transformers', transformer_cfg)
        self._set_pipeline_cfg('counters', ['unrelated-sample'])
        pipeline_manager = pipeline.PipelineManager(self.pipeline_cfg,
                                                    self.transformer_manager)
        timeutils.advance_time_seconds(200)
        pipe = pipeline_manager.pipelines[0]
        pipe.flush(None)
        publisher = pipeline_manager.pipelines[0].publishers[0]
        self.assertEqual(0, len(publisher.samples))

    def _do_test_delta(self, data, expected, growth_only=False):
        transformer_cfg = [
            {
                'name': 'delta',
                'parameters': {
                    'target': {'name': 'new_meter'},
                    'growth_only': growth_only,
                }
            },
        ]
        self._set_pipeline_cfg('transformers', transformer_cfg)
        self._set_pipeline_cfg('counters', ['cpu'])

        pipeline_manager = pipeline.PipelineManager(self.pipeline_cfg,
                                                    self.transformer_manager)
        pipe = pipeline_manager.pipelines[0]

        pipe.publish_data(None, data)
        pipe.flush(None)
        publisher = pipeline_manager.pipelines[0].publishers[0]
        self.assertEqual(expected, len(publisher.samples))
        return publisher.samples

    def test_delta_transformer(self):
        samples = [
            sample.Sample(
                name='cpu',
                type=sample.TYPE_CUMULATIVE,
                volume=26,
                unit='ns',
                user_id='test_user',
                project_id='test_proj',
                resource_id='test_resource',
                timestamp=timeutils.utcnow().isoformat(),
                resource_metadata={'version': '1.0'}
            ),
            sample.Sample(
                name='cpu',
                type=sample.TYPE_CUMULATIVE,
                volume=16,
                unit='ns',
                user_id='test_user',
                project_id='test_proj',
                resource_id='test_resource',
                timestamp=timeutils.utcnow().isoformat(),
                resource_metadata={'version': '2.0'}
            ),
            sample.Sample(
                name='cpu',
                type=sample.TYPE_CUMULATIVE,
                volume=53,
                unit='ns',
                user_id='test_user_bis',
                project_id='test_proj_bis',
                resource_id='test_resource',
                timestamp=timeutils.utcnow().isoformat(),
                resource_metadata={'version': '1.0'}
            ),
        ]
        deltas = self._do_test_delta(samples, 2)
        self.assertEqual('new_meter', deltas[0].name)
        self.assertEqual('delta', deltas[0].type)
        self.assertEqual('ns', deltas[0].unit)
        self.assertEqual({'version': '2.0'}, deltas[0].resource_metadata)
        self.assertEqual(-10, deltas[0].volume)
        self.assertEqual('new_meter', deltas[1].name)
        self.assertEqual('delta', deltas[1].type)
        self.assertEqual('ns', deltas[1].unit)
        self.assertEqual({'version': '1.0'}, deltas[1].resource_metadata)
        self.assertEqual(37, deltas[1].volume)

    def test_delta_transformer_out_of_order(self):
        samples = [
            sample.Sample(
                name='cpu',
                type=sample.TYPE_CUMULATIVE,
                volume=26,
                unit='ns',
                user_id='test_user',
                project_id='test_proj',
                resource_id='test_resource',
                timestamp=timeutils.utcnow().isoformat(),
                resource_metadata={'version': '1.0'}
            ),
            sample.Sample(
                name='cpu',
                type=sample.TYPE_CUMULATIVE,
                volume=16,
                unit='ns',
                user_id='test_user',
                project_id='test_proj',
                resource_id='test_resource',
                timestamp=((timeutils.utcnow() - datetime.timedelta(minutes=5))
                           .isoformat()),
                resource_metadata={'version': '2.0'}
            ),
            sample.Sample(
                name='cpu',
                type=sample.TYPE_CUMULATIVE,
                volume=53,
                unit='ns',
                user_id='test_user_bis',
                project_id='test_proj_bis',
                resource_id='test_resource',
                timestamp=timeutils.utcnow().isoformat(),
                resource_metadata={'version': '1.0'}
            ),
        ]
        deltas = self._do_test_delta(samples, 1)
        self.assertEqual('new_meter', deltas[0].name)
        self.assertEqual('delta', deltas[0].type)
        self.assertEqual('ns', deltas[0].unit)
        self.assertEqual({'version': '1.0'}, deltas[0].resource_metadata)
        self.assertEqual(27, deltas[0].volume)

    def test_delta_transformer_growth_only(self):
        samples = [
            sample.Sample(
                name='cpu',
                type=sample.TYPE_CUMULATIVE,
                volume=26,
                unit='ns',
                user_id='test_user',
                project_id='test_proj',
                resource_id='test_resource',
                timestamp=timeutils.utcnow().isoformat(),
                resource_metadata={'version': '1.0'}
            ),
            sample.Sample(
                name='cpu',
                type=sample.TYPE_CUMULATIVE,
                volume=16,
                unit='ns',
                user_id='test_user',
                project_id='test_proj',
                resource_id='test_resource',
                timestamp=timeutils.utcnow().isoformat(),
                resource_metadata={'version': '2.0'}
            ),
            sample.Sample(
                name='cpu',
                type=sample.TYPE_CUMULATIVE,
                volume=53,
                unit='ns',
                user_id='test_user_bis',
                project_id='test_proj_bis',
                resource_id='test_resource',
                timestamp=timeutils.utcnow().isoformat(),
                resource_metadata={'version': '1.0'}
            ),
        ]
        deltas = self._do_test_delta(samples, 1, True)
        self.assertEqual('new_meter', deltas[0].name)
        self.assertEqual('delta', deltas[0].type)
        self.assertEqual('ns', deltas[0].unit)
        self.assertEqual({'version': '1.0'}, deltas[0].resource_metadata)
        self.assertEqual(37, deltas[0].volume)

    def test_unique_pipeline_names(self):
        self._dup_pipeline_name_cfg()
        self._exception_create_pipelinemanager()

    def test_get_pipeline_grouping_key(self):
        transformer_cfg = [
            {
                'name': 'update',
                'parameters': {}
            },
            {
                'name': 'unit_conversion',
                'parameters': {
                    'source': {},
                    'target': {'name': 'cpu_mins',
                               'unit': 'min',
                               'scale': 'volume'},
                }
            },
            {
                'name': 'update',
                'parameters': {}
            },
        ]
        self._set_pipeline_cfg('transformers', transformer_cfg)
        pipeline_manager = pipeline.PipelineManager(self.pipeline_cfg,
                                                    self.transformer_manager)
        self.assertEqual(set(['resource_id', 'counter_name']),
                         set(pipeline.get_pipeline_grouping_key(
                             pipeline_manager.pipelines[0])))

    def test_get_pipeline_duplicate_grouping_key(self):
        transformer_cfg = [
            {
                'name': 'update',
                'parameters': {}
            },
            {
                'name': 'update',
                'parameters': {}
            },
        ]
        self._set_pipeline_cfg('transformers', transformer_cfg)
        pipeline_manager = pipeline.PipelineManager(self.pipeline_cfg,
                                                    self.transformer_manager)
        self.assertEqual(['counter_name'],
                         pipeline.get_pipeline_grouping_key(
                             pipeline_manager.pipelines[0]))
