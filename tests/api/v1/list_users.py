# -*- encoding: utf-8 -*-
#
# Copyright © 2012 New Dream Network, LLC (DreamHost)
#
# Author: Doug Hellmann <doug.hellmann@dreamhost.com>
#         Julien Danjou <julien@danjou.info>
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
"""Test listing users.
"""

import datetime
import logging

from oslo.config import cfg

from ceilometer.publisher import rpc
from ceilometer import counter

from ceilometer.tests import api as tests_api

LOG = logging.getLogger(__name__)


class TestListEmptyUsers(tests_api.TestBase):

    def test_empty(self):
        data = self.get('/users')
        self.assertEquals({'users': []}, data)


class TestListUsers(tests_api.TestBase):

    def setUp(self):
        super(TestListUsers, self).setUp()

        counter1 = counter.Counter(
            'instance',
            'cumulative',
            'instance',
            1,
            'user-id',
            'project-id',
            'resource-id',
            timestamp=datetime.datetime(2012, 7, 2, 10, 40),
            resource_metadata={'display_name': 'test-server',
                               'tag': 'self.counter',
                               }
        )
        msg = rpc.meter_message_from_counter(
            counter1,
            cfg.CONF.publisher_rpc.metering_secret,
            'test_list_users',
        )
        self.conn.record_metering_data(msg)

        counter2 = counter.Counter(
            'instance',
            'cumulative',
            '',
            1,
            'user-id2',
            'project-id',
            'resource-id-alternate',
            timestamp=datetime.datetime(2012, 7, 2, 10, 41),
            resource_metadata={'display_name': 'test-server',
                               'tag': 'self.counter2',
                               }
        )
        msg2 = rpc.meter_message_from_counter(
            counter2,
            cfg.CONF.publisher_rpc.metering_secret,
            'not-test',
        )
        self.conn.record_metering_data(msg2)

    def test_users(self):
        data = self.get('/users')
        self.assertEquals(['user-id', 'user-id2'], data['users'])

    def test_users_non_admin(self):
        data = self.get('/users',
                        headers={"X-Roles": "Member",
                                 "X-User-Id": "user-id",
                                 "X-Tenant-Id": "project-id"})
        self.assertEquals(['user-id'], data['users'])

    def test_with_source(self):
        data = self.get('/sources/test_list_users/users')
        self.assertEquals(['user-id'], data['users'])

    def test_with_source_non_admin(self):
        data = self.get('/sources/test_list_users/users',
                        headers={"X-Roles": "Member",
                                 "X-User-Id": "user-id",
                                 "X-Tenant-Id": "project-id"})
        self.assertEquals(['user-id'], data['users'])
