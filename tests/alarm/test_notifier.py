# -*- encoding: utf-8 -*-
#
# Copyright © 2013 eNovance
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
import eventlet
import urlparse
import mock
import requests

from ceilometer.alarm import service
from ceilometer.openstack.common import context
from ceilometer.openstack.common import network_utils
from ceilometer.tests import base


class TestAlarmNotifier(base.TestCase):

    def setUp(self):
        super(TestAlarmNotifier, self).setUp()
        self.service = service.AlarmNotifierService('somehost', 'sometopic')

    def test_notify_alarm(self):
        data = {
            'actions': ['test://'],
            'alarm': {'name': 'foobar'},
            'state': 'ALARM',
            'reason': 'Everything is on fire',
        }
        self.service.notify_alarm(context.get_admin_context(), data)
        notifications = self.service.notifiers['test'].obj.notifications
        self.assertEqual(len(notifications), 1)
        self.assertEqual(notifications[0], (
            urlparse.urlsplit(data['actions'][0]),
            data['alarm'],
            data['state'],
            data['reason']))

    def test_notify_alarm_no_action(self):
        self.service.notify_alarm(context.get_admin_context(), {})

    def test_notify_alarm_log_action(self):
        self.service.notify_alarm(context.get_admin_context(),
                                  {
                                      'actions': ['log://'],
                                      'alarm': {'name': 'foobar'},
                                      'condition': {'threshold': 42},
                                  })

    def test_notify_alarm_rest_action(self):
        action = 'http://host/action'
        data_json = '{"state": "ALARM", "reason": "what ?"}'

        self.mox.StubOutWithMock(requests, "post")
        requests.post(network_utils.urlsplit(action), data=data_json)
        self.mox.ReplayAll()
        self.service.notify_alarm(context.get_admin_context(),
                                  {
                                      'actions': [action],
                                      'alarm': {'name': 'foobar'},
                                      'condition': {'threshold': 42},
                                      'reason': 'what ?',
                                      'state': 'ALARM',
                                  })
        eventlet.sleep(1)
        self.mox.UnsetStubs()
        self.mox.VerifyAll()

    @staticmethod
    def _fake_urlsplit(*args, **kwargs):
        raise Exception("Evil urlsplit!")

    def test_notify_alarm_invalid_url(self):
        with mock.patch('ceilometer.openstack.common.network_utils.urlsplit',
                        self._fake_urlsplit):
            LOG = mock.MagicMock()
            with mock.patch('ceilometer.alarm.service.LOG', LOG):
                self.service.notify_alarm(
                    context.get_admin_context(),
                    {
                        'actions': ['no-such-action-i-am-sure'],
                        'alarm': {'name': 'foobar'},
                        'condition': {'threshold': 42},
                    })
                self.assertTrue(LOG.error.called)

    def test_notify_alarm_invalid_action(self):
        LOG = mock.MagicMock()
        with mock.patch('ceilometer.alarm.service.LOG', LOG):
            self.service.notify_alarm(
                context.get_admin_context(),
                {
                    'actions': ['no-such-action-i-am-sure://'],
                    'alarm': {'name': 'foobar'},
                    'condition': {'threshold': 42},
                })
            self.assertTrue(LOG.error.called)
