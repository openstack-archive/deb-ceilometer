#
# Copyright 2012 New Dream Network, LLC (DreamHost)
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
"""Tests for ceilometer/publisher/messaging.py
"""
import datetime
import uuid

import eventlet
import mock
from oslo_config import fixture as fixture_config
from oslo_context import context
import oslo_messaging
from oslo_utils import netutils
import testscenarios.testcase

from ceilometer.event.storage import models as event
from ceilometer import messaging
from ceilometer.publisher import messaging as msg_publisher
from ceilometer import sample
from ceilometer.tests import base as tests_base


class BasePublisherTestCase(tests_base.BaseTestCase):
    test_event_data = [
        event.Event(message_id=uuid.uuid4(),
                    event_type='event_%d' % i,
                    generated=datetime.datetime.utcnow(),
                    traits=[], raw={})
        for i in range(0, 5)
    ]

    test_sample_data = [
        sample.Sample(
            name='test',
            type=sample.TYPE_CUMULATIVE,
            unit='',
            volume=1,
            user_id='test',
            project_id='test',
            resource_id='test_run_tasks',
            timestamp=datetime.datetime.utcnow().isoformat(),
            resource_metadata={'name': 'TestPublish'},
        ),
        sample.Sample(
            name='test',
            type=sample.TYPE_CUMULATIVE,
            unit='',
            volume=1,
            user_id='test',
            project_id='test',
            resource_id='test_run_tasks',
            timestamp=datetime.datetime.utcnow().isoformat(),
            resource_metadata={'name': 'TestPublish'},
        ),
        sample.Sample(
            name='test2',
            type=sample.TYPE_CUMULATIVE,
            unit='',
            volume=1,
            user_id='test',
            project_id='test',
            resource_id='test_run_tasks',
            timestamp=datetime.datetime.utcnow().isoformat(),
            resource_metadata={'name': 'TestPublish'},
        ),
        sample.Sample(
            name='test2',
            type=sample.TYPE_CUMULATIVE,
            unit='',
            volume=1,
            user_id='test',
            project_id='test',
            resource_id='test_run_tasks',
            timestamp=datetime.datetime.utcnow().isoformat(),
            resource_metadata={'name': 'TestPublish'},
        ),
        sample.Sample(
            name='test3',
            type=sample.TYPE_CUMULATIVE,
            unit='',
            volume=1,
            user_id='test',
            project_id='test',
            resource_id='test_run_tasks',
            timestamp=datetime.datetime.utcnow().isoformat(),
            resource_metadata={'name': 'TestPublish'},
        ),
    ]

    def setUp(self):
        super(BasePublisherTestCase, self).setUp()
        self.CONF = self.useFixture(fixture_config.Config()).conf
        self.setup_messaging(self.CONF)


class RpcOnlyPublisherTest(BasePublisherTestCase):
    def test_published_no_mock(self):
        publisher = msg_publisher.RPCPublisher(
            netutils.urlsplit('rpc://'))

        endpoint = mock.MagicMock(['record_metering_data'])
        collector = messaging.get_rpc_server(
            self.transport, self.CONF.publisher_rpc.metering_topic, endpoint)
        endpoint.record_metering_data.side_effect = (lambda *args, **kwds:
                                                     collector.stop())

        collector.start()
        eventlet.sleep()
        publisher.publish_samples(context.RequestContext(),
                                  self.test_sample_data)
        collector.wait()

        class Matcher(object):
            @staticmethod
            def __eq__(data):
                for i, sample_item in enumerate(data):
                    if (sample_item['counter_name'] !=
                            self.test_sample_data[i].name):
                        return False
                return True

        endpoint.record_metering_data.assert_called_once_with(
            mock.ANY, data=Matcher())

    def test_publish_target(self):
        publisher = msg_publisher.RPCPublisher(
            netutils.urlsplit('rpc://?target=custom_procedure_call'))
        cast_context = mock.MagicMock()
        with mock.patch.object(publisher.rpc_client, 'prepare') as prepare:
            prepare.return_value = cast_context
            publisher.publish_samples(mock.MagicMock(),
                                      self.test_sample_data)

        prepare.assert_called_once_with(
            topic=self.CONF.publisher_rpc.metering_topic)
        cast_context.cast.assert_called_once_with(
            mock.ANY, 'custom_procedure_call', data=mock.ANY)

    def test_published_with_per_meter_topic(self):
        publisher = msg_publisher.RPCPublisher(
            netutils.urlsplit('rpc://?per_meter_topic=1'))
        with mock.patch.object(publisher.rpc_client, 'prepare') as prepare:
            publisher.publish_samples(mock.MagicMock(),
                                      self.test_sample_data)

            class MeterGroupMatcher(object):
                def __eq__(self, meters):
                    return len(set(meter['counter_name']
                                   for meter in meters)) == 1

            topic = self.CONF.publisher_rpc.metering_topic
            expected = [mock.call(topic=topic),
                        mock.call().cast(mock.ANY, 'record_metering_data',
                                         data=mock.ANY),
                        mock.call(topic=topic + '.test'),
                        mock.call().cast(mock.ANY, 'record_metering_data',
                                         data=MeterGroupMatcher()),
                        mock.call(topic=topic + '.test2'),
                        mock.call().cast(mock.ANY, 'record_metering_data',
                                         data=MeterGroupMatcher()),
                        mock.call(topic=topic + '.test3'),
                        mock.call().cast(mock.ANY, 'record_metering_data',
                                         data=MeterGroupMatcher())]
            self.assertEqual(expected, prepare.mock_calls)


class NotifierOnlyPublisherTest(BasePublisherTestCase):

    @mock.patch('oslo_messaging.Notifier')
    def test_publish_topic_override(self, notifier):
        msg_publisher.SampleNotifierPublisher(
            netutils.urlsplit('notifier://?topic=custom_topic'))
        notifier.assert_called_with(mock.ANY, topic='custom_topic',
                                    driver=mock.ANY, retry=mock.ANY,
                                    publisher_id=mock.ANY)

        msg_publisher.EventNotifierPublisher(
            netutils.urlsplit('notifier://?topic=custom_event_topic'))
        notifier.assert_called_with(mock.ANY, topic='custom_event_topic',
                                    driver=mock.ANY, retry=mock.ANY,
                                    publisher_id=mock.ANY)


class TestPublisher(testscenarios.testcase.WithScenarios,
                    BasePublisherTestCase):
    scenarios = [
        ('notifier',
         dict(protocol="notifier",
              publisher_cls=msg_publisher.SampleNotifierPublisher,
              test_data=BasePublisherTestCase.test_sample_data,
              pub_func='publish_samples', attr='source')),
        ('event_notifier',
         dict(protocol="notifier",
              publisher_cls=msg_publisher.EventNotifierPublisher,
              test_data=BasePublisherTestCase.test_event_data,
              pub_func='publish_events', attr='event_type')),
        ('rpc', dict(protocol="rpc",
                     publisher_cls=msg_publisher.RPCPublisher,
                     test_data=BasePublisherTestCase.test_sample_data,
                     pub_func='publish_samples', attr='source')),
    ]

    def setUp(self):
        super(TestPublisher, self).setUp()
        self.topic = (self.CONF.publisher_notifier.event_topic
                      if self.pub_func == 'publish_events' else
                      self.CONF.publisher_rpc.metering_topic)


class TestPublisherPolicy(TestPublisher):
    def test_published_concurrency(self):
        """Test concurrent access to the local queue of the rpc publisher."""

        publisher = self.publisher_cls(
            netutils.urlsplit('%s://' % self.protocol))

        with mock.patch.object(publisher, '_send') as fake_send:
            def fake_send_wait(ctxt, topic, meters):
                fake_send.side_effect = mock.Mock()
                # Sleep to simulate concurrency and allow other threads to work
                eventlet.sleep(0)

            fake_send.side_effect = fake_send_wait

            job1 = eventlet.spawn(getattr(publisher, self.pub_func),
                                  mock.MagicMock(), self.test_data)
            job2 = eventlet.spawn(getattr(publisher, self.pub_func),
                                  mock.MagicMock(), self.test_data)

            job1.wait()
            job2.wait()

        self.assertEqual('default', publisher.policy)
        self.assertEqual(2, len(fake_send.mock_calls))
        self.assertEqual(0, len(publisher.local_queue))

    @mock.patch('ceilometer.publisher.messaging.LOG')
    def test_published_with_no_policy(self, mylog):
        publisher = self.publisher_cls(
            netutils.urlsplit('%s://' % self.protocol))
        side_effect = oslo_messaging.MessageDeliveryFailure()
        with mock.patch.object(publisher, '_send') as fake_send:
            fake_send.side_effect = side_effect
            self.assertRaises(
                oslo_messaging.MessageDeliveryFailure,
                getattr(publisher, self.pub_func),
                mock.MagicMock(), self.test_data)
            self.assertTrue(mylog.info.called)
            self.assertEqual('default', publisher.policy)
            self.assertEqual(0, len(publisher.local_queue))
            fake_send.assert_called_once_with(
                mock.ANY, self.topic, mock.ANY)

    @mock.patch('ceilometer.publisher.messaging.LOG')
    def test_published_with_policy_block(self, mylog):
        publisher = self.publisher_cls(
            netutils.urlsplit('%s://?policy=default' % self.protocol))
        side_effect = oslo_messaging.MessageDeliveryFailure()
        with mock.patch.object(publisher, '_send') as fake_send:
            fake_send.side_effect = side_effect
            self.assertRaises(
                oslo_messaging.MessageDeliveryFailure,
                getattr(publisher, self.pub_func),
                mock.MagicMock(), self.test_data)
            self.assertTrue(mylog.info.called)
            self.assertEqual(0, len(publisher.local_queue))
            fake_send.assert_called_once_with(
                mock.ANY, self.topic, mock.ANY)

    @mock.patch('ceilometer.publisher.messaging.LOG')
    def test_published_with_policy_incorrect(self, mylog):
        publisher = self.publisher_cls(
            netutils.urlsplit('%s://?policy=notexist' % self.protocol))
        side_effect = oslo_messaging.MessageDeliveryFailure()
        with mock.patch.object(publisher, '_send') as fake_send:
            fake_send.side_effect = side_effect
            self.assertRaises(
                oslo_messaging.MessageDeliveryFailure,
                getattr(publisher, self.pub_func),
                mock.MagicMock(), self.test_data)
            self.assertTrue(mylog.warn.called)
            self.assertEqual('default', publisher.policy)
            self.assertEqual(0, len(publisher.local_queue))
            fake_send.assert_called_once_with(
                mock.ANY, self.topic, mock.ANY)


@mock.patch('ceilometer.publisher.messaging.LOG', mock.Mock())
class TestPublisherPolicyReactions(TestPublisher):

    def test_published_with_policy_drop_and_rpc_down(self):
        publisher = self.publisher_cls(
            netutils.urlsplit('%s://?policy=drop' % self.protocol))
        side_effect = oslo_messaging.MessageDeliveryFailure()
        with mock.patch.object(publisher, '_send') as fake_send:
            fake_send.side_effect = side_effect
            getattr(publisher, self.pub_func)(mock.MagicMock(),
                                              self.test_data)
            self.assertEqual(0, len(publisher.local_queue))
            fake_send.assert_called_once_with(
                mock.ANY, self.topic, mock.ANY)

    def test_published_with_policy_queue_and_rpc_down(self):
        publisher = self.publisher_cls(
            netutils.urlsplit('%s://?policy=queue' % self.protocol))
        side_effect = oslo_messaging.MessageDeliveryFailure()
        with mock.patch.object(publisher, '_send') as fake_send:
            fake_send.side_effect = side_effect

            getattr(publisher, self.pub_func)(mock.MagicMock(),
                                              self.test_data)
            self.assertEqual(1, len(publisher.local_queue))
            fake_send.assert_called_once_with(
                mock.ANY, self.topic, mock.ANY)

    def test_published_with_policy_queue_and_rpc_down_up(self):
        self.rpc_unreachable = True
        publisher = self.publisher_cls(
            netutils.urlsplit('%s://?policy=queue' % self.protocol))

        side_effect = oslo_messaging.MessageDeliveryFailure()
        with mock.patch.object(publisher, '_send') as fake_send:
            fake_send.side_effect = side_effect
            getattr(publisher, self.pub_func)(mock.MagicMock(),
                                              self.test_data)

            self.assertEqual(1, len(publisher.local_queue))

            fake_send.side_effect = mock.MagicMock()
            getattr(publisher, self.pub_func)(mock.MagicMock(),
                                              self.test_data)

            self.assertEqual(0, len(publisher.local_queue))

            topic = self.topic
            expected = [mock.call(mock.ANY, topic, mock.ANY),
                        mock.call(mock.ANY, topic, mock.ANY),
                        mock.call(mock.ANY, topic, mock.ANY)]
            self.assertEqual(expected, fake_send.mock_calls)

    def test_published_with_policy_sized_queue_and_rpc_down(self):
        publisher = self.publisher_cls(netutils.urlsplit(
            '%s://?policy=queue&max_queue_length=3' % self.protocol))

        side_effect = oslo_messaging.MessageDeliveryFailure()
        with mock.patch.object(publisher, '_send') as fake_send:
            fake_send.side_effect = side_effect
            for i in range(0, 5):
                for s in self.test_data:
                    setattr(s, self.attr, 'test-%d' % i)
                getattr(publisher, self.pub_func)(mock.MagicMock(),
                                                  self.test_data)

        self.assertEqual(3, len(publisher.local_queue))
        self.assertEqual(
            'test-2',
            publisher.local_queue[0][2][0][self.attr]
        )
        self.assertEqual(
            'test-3',
            publisher.local_queue[1][2][0][self.attr]
        )
        self.assertEqual(
            'test-4',
            publisher.local_queue[2][2][0][self.attr]
        )

    def test_published_with_policy_default_sized_queue_and_rpc_down(self):
        publisher = self.publisher_cls(
            netutils.urlsplit('%s://?policy=queue' % self.protocol))

        side_effect = oslo_messaging.MessageDeliveryFailure()
        with mock.patch.object(publisher, '_send') as fake_send:
            fake_send.side_effect = side_effect
            for i in range(0, 2000):
                for s in self.test_data:
                    setattr(s, self.attr, 'test-%d' % i)
                getattr(publisher, self.pub_func)(mock.MagicMock(),
                                                  self.test_data)

        self.assertEqual(1024, len(publisher.local_queue))
        self.assertEqual(
            'test-976',
            publisher.local_queue[0][2][0][self.attr]
        )
        self.assertEqual(
            'test-1999',
            publisher.local_queue[1023][2][0][self.attr]
        )
