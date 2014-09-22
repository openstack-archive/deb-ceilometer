#
# Copyright 2013 eNovance <licensing@enovance.com>
#
# Author: Julien Danjou <julien@danjou.info>
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
from oslo.config import fixture as fixture_config
from oslotest import base

from ceilometer import plugin


TEST_NOTIFICATION = {
    u'_context_auth_token': u'3d8b13de1b7d499587dfc69b77dc09c2',
    u'_context_is_admin': True,
    u'_context_project_id': u'7c150a59fe714e6f9263774af9688f0e',
    u'_context_quota_class': None,
    u'_context_read_deleted': u'no',
    u'_context_remote_address': u'10.0.2.15',
    u'_context_request_id': u'req-d68b36e0-9233-467f-9afb-d81435d64d66',
    u'_context_roles': [u'admin'],
    u'_context_timestamp': u'2012-05-08T20:23:41.425105',
    u'_context_user_id': u'1e3ce043029547f1a61c1996d1a531a2',
    u'event_type': u'compute.instance.create.end',
    u'message_id': u'dae6f69c-00e0-41c0-b371-41ec3b7f4451',
    u'payload': {u'created_at': u'2012-05-08 20:23:41',
                 u'deleted_at': u'',
                 u'disk_gb': 0,
                 u'display_name': u'testme',
                 u'fixed_ips': [{u'address': u'10.0.0.2',
                                 u'floating_ips': [],
                                 u'meta': {},
                                 u'type': u'fixed',
                                 u'version': 4}],
                 u'image_ref_url': u'http://10.0.2.15:9292/images/UUID',
                 u'instance_id': u'9f9d01b9-4a58-4271-9e27-398b21ab20d1',
                 u'instance_type': u'm1.tiny',
                 u'instance_type_id': 2,
                 u'launched_at': u'2012-05-08 20:23:47.985999',
                 u'memory_mb': 512,
                 u'state': u'active',
                 u'state_description': u'',
                 u'tenant_id': u'7c150a59fe714e6f9263774af9688f0e',
                 u'user_id': u'1e3ce043029547f1a61c1996d1a531a2',
                 u'reservation_id': u'1e3ce043029547f1a61c1996d1a531a3',
                 u'vcpus': 1,
                 u'root_gb': 0,
                 u'ephemeral_gb': 0,
                 u'host': u'compute-host-name',
                 u'availability_zone': u'1e3ce043029547f1a61c1996d1a531a4',
                 u'os_type': u'linux?',
                 u'architecture': u'x86',
                 u'image_ref': u'UUID',
                 u'kernel_id': u'1e3ce043029547f1a61c1996d1a531a5',
                 u'ramdisk_id': u'1e3ce043029547f1a61c1996d1a531a6',
                 },
    u'priority': u'INFO',
    u'publisher_id': u'compute.vagrant-precise',
    u'timestamp': u'2012-05-08 20:23:48.028195',
}


class NotificationBaseTestCase(base.BaseTestCase):
    def setUp(self):
        super(NotificationBaseTestCase, self).setUp()
        self.CONF = self.useFixture(fixture_config.Config()).conf

    def test_handle_event_type(self):
        self.assertFalse(plugin.NotificationBase._handle_event_type(
            'compute.instance.start', ['compute']))
        self.assertFalse(plugin.NotificationBase._handle_event_type(
            'compute.instance.start', ['compute.*.foobar']))
        self.assertFalse(plugin.NotificationBase._handle_event_type(
            'compute.instance.start', ['compute.*.*.foobar']))
        self.assertTrue(plugin.NotificationBase._handle_event_type(
            'compute.instance.start', ['compute.*']))
        self.assertTrue(plugin.NotificationBase._handle_event_type(
            'compute.instance.start', ['*']))
        self.assertTrue(plugin.NotificationBase._handle_event_type(
            'compute.instance.start', ['compute.*.start']))
        self.assertTrue(plugin.NotificationBase._handle_event_type(
            'compute.instance.start', ['*.start']))
        self.assertTrue(plugin.NotificationBase._handle_event_type(
            'compute.instance.start', ['compute.*.*.foobar', 'compute.*']))

    class FakePlugin(plugin.NotificationBase):
        def get_exchange_topics(self, conf):
            return [plugin.ExchangeTopics(exchange="exchange1",
                                          topics=["t1", "t2"]),
                    plugin.ExchangeTopics(exchange="exchange2",
                                          topics=['t3'])]

        def process_notification(self, message):
            return message

    class FakeComputePlugin(FakePlugin):
        event_types = ['compute.*']

    class FakeNetworkPlugin(FakePlugin):
        event_types = ['network.*']

    def _do_test_to_samples(self, plugin_class, match):
        pm = mock.MagicMock()
        plug = plugin_class(pm)
        publish = pm.publisher.return_value.__enter__.return_value

        plug.to_samples_and_publish(mock.Mock(), TEST_NOTIFICATION)

        if match:
            publish.assert_called_once_with(list(TEST_NOTIFICATION))
        else:
            self.assertEqual(0, publish.call_count)

    def test_to_samples_match(self):
        self._do_test_to_samples(self.FakeComputePlugin, True)

    def test_to_samples_no_match(self):
        self._do_test_to_samples(self.FakeNetworkPlugin, False)

    def test_get_targets_compat(self):
        targets = self.FakeComputePlugin(mock.Mock()).get_targets(self.CONF)
        self.assertEqual(3, len(targets))
        self.assertEqual('t1', targets[0].topic)
        self.assertEqual('exchange1', targets[0].exchange)
        self.assertEqual('t2', targets[1].topic)
        self.assertEqual('exchange1', targets[1].exchange)
        self.assertEqual('t3', targets[2].topic)
        self.assertEqual('exchange2', targets[2].exchange)
