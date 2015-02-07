#
# Copyright Ericsson AB 2014. All rights reserved
#
# Authors: Ildiko Vancsa <ildiko.vancsa@ericsson.com>
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
"""Tests for ceilometer/storage/impl_db2.py

.. note::
  In order to run the tests against another MongoDB server set the
  environment variable CEILOMETER_TEST_DB2_URL to point to a DB2
  server before running the tests.

"""

import bson
import mock
from oslo.utils import timeutils

from ceilometer.alarm.storage import impl_db2 as impl_db2_alarm
from ceilometer.storage import impl_db2
from ceilometer.storage.mongo import utils as pymongo_utils
from ceilometer.tests import base as test_base


class CapabilitiesTest(test_base.BaseTestCase):
    # Check the returned capabilities list, which is specific to each DB
    # driver

    def test_capabilities(self):
        expected_capabilities = {
            'meters': {'pagination': False,
                       'query': {'simple': True,
                                 'metadata': True,
                                 'complex': False}},
            'resources': {'pagination': False,
                          'query': {'simple': True,
                                    'metadata': True,
                                    'complex': False}},
            'samples': {'pagination': False,
                        'groupby': False,
                        'query': {'simple': True,
                                  'metadata': True,
                                  'complex': True}},
            'statistics': {'pagination': False,
                           'groupby': True,
                           'query': {'simple': True,
                                     'metadata': True,
                                     'complex': False},
                           'aggregation': {'standard': True,
                                           'selectable': {
                                               'max': False,
                                               'min': False,
                                               'sum': False,
                                               'avg': False,
                                               'count': False,
                                               'stddev': False,
                                               'cardinality': False}}
                           },
            'events': {'query': {'simple': True}}
        }

        actual_capabilities = impl_db2.Connection.get_capabilities()
        self.assertEqual(expected_capabilities, actual_capabilities)

    def test_alarm_capabilities(self):
        expected_capabilities = {
            'alarms': {'query': {'simple': True,
                                 'complex': True},
                       'history': {'query': {'simple': True,
                                             'complex': True}}},
        }

        actual_capabilities = impl_db2_alarm.Connection.get_capabilities()
        self.assertEqual(expected_capabilities, actual_capabilities)

    def test_storage_capabilities(self):
        expected_capabilities = {
            'storage': {'production_ready': True},
        }
        actual_capabilities = impl_db2.Connection.get_storage_capabilities()
        self.assertEqual(expected_capabilities, actual_capabilities)


class ConnectionTest(test_base.BaseTestCase):
    @mock.patch.object(pymongo_utils.ConnectionPool, 'connect')
    @mock.patch.object(timeutils, 'utcnow')
    @mock.patch.object(bson.objectid, 'ObjectId')
    def test_upgrade(self, meter_id, timestamp, mongo_connect):
        conn_mock = mock.MagicMock()
        conn_mock.server_info.return_value = {}
        conn_mock.ceilodb2.resource.index_information.return_value = {}
        mongo_connect.return_value = conn_mock
        meter_id.return_value = '54b8860d75bfe43b54e84ce7'
        timestamp.return_value = 'timestamp'
        impl_db2.Connection('db2://user:pwd@localhost:27017/ceilodb2')
        conn_mock.ceilodb2.resource.insert.assert_called_with(
            {'_id': '54b8860d75bfe43b54e84ce7',
             'no_key': '54b8860d75bfe43b54e84ce7'})
        conn_mock.ceilodb2.meter.insert.assert_called_with(
            {'_id': '54b8860d75bfe43b54e84ce7',
             'no_key': '54b8860d75bfe43b54e84ce7',
             'timestamp': 'timestamp'})
