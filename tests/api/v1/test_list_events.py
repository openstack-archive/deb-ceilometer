# -*- encoding: utf-8 -*-
#
# Copyright © 2012 New Dream Network, LLC (DreamHost)
#
# Author: Doug Hellmann <doug.hellmann@dreamhost.com>
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
"""Test listing raw events.
"""

import datetime
import logging

from ceilometer import counter
from ceilometer import meter
from ceilometer.openstack.common import cfg

from ceilometer.tests import api as tests_api

LOG = logging.getLogger(__name__)


class TestListEvents(tests_api.TestBase):

    def setUp(self):
        super(TestListEvents, self).setUp()
        for cnt in [
                counter.Counter(
                    'instance',
                    'cumulative',
                    1,
                    'user-id',
                    'project1',
                    'resource-id',
                    timestamp=datetime.datetime(2012, 7, 2, 10, 40),
                    resource_metadata={'display_name': 'test-server',
                                       'tag': 'self.counter',
                                   }
                ),
                counter.Counter(
                    'instance',
                    'cumulative',
                    2,
                    'user-id',
                    'project1',
                    'resource-id',
                    timestamp=datetime.datetime(2012, 7, 2, 10, 41),
                    resource_metadata={'display_name': 'test-server',
                                       'tag': 'self.counter',
                                   }
                ),
                counter.Counter(
                    'instance',
                    'cumulative',
                    1,
                    'user-id2',
                    'project2',
                    'resource-id-alternate',
                    timestamp=datetime.datetime(2012, 7, 2, 10, 42),
                    resource_metadata={'display_name': 'test-server',
                                       'tag': 'self.counter2',
                                   }
                ),
        ]:
            msg = meter.meter_message_from_counter(cnt,
                                                   cfg.CONF.metering_secret,
                                                   'source1')
            self.conn.record_metering_data(msg)

    def test_empty_project(self):
        data = self.get('/projects/no-such-project/meters/instance')
        self.assertEquals({'events': []}, data)

    def test_by_project(self):
        data = self.get('/projects/project1/meters/instance')
        self.assertEquals(2, len(data['events']))

    def test_by_project_with_timestamps(self):
        data = self.get('/projects/project1/meters/instance',
                        start_timestamp=datetime.datetime(2012, 7, 2, 10, 42))
        self.assertEquals(0, len(data['events']))

    def test_empty_resource(self):
        data = self.get('/resources/no-such-resource/meters/instance')
        self.assertEquals({'events': []}, data)

    def test_by_resource(self):
        data = self.get('/resources/resource-id/meters/instance')
        self.assertEquals(2, len(data['events']))

    def test_empty_source(self):
        data = self.get('/sources/no-such-source/meters/instance')
        self.assertEquals({'events': []}, data)

    def test_by_source(self):
        data = self.get('/sources/source1/meters/instance')
        self.assertEquals(3, len(data['events']))

    def test_by_source_with_timestamps(self):
        data = self.get('/sources/source1/meters/instance',
                        end_timestamp=datetime.datetime(2012, 7, 2, 10, 42))
        self.assertEquals(2, len(data['events']))

    def test_empty_user(self):
        data = self.get('/users/no-such-user/meters/instance')
        self.assertEquals({'events': []}, data)

    def test_by_user(self):
        data = self.get('/users/user-id/meters/instance')
        self.assertEquals(2, len(data['events']))

    def test_by_user_with_timestamps(self):
        data = self.get('/users/user-id/meters/instance',
                        start_timestamp=datetime.datetime(2012, 7, 2, 10, 41),
                          end_timestamp=datetime.datetime(2012, 7, 2, 10, 42))
        self.assertEquals(1, len(data['events']))
