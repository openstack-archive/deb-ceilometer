#
# Copyright 2013 Intel Corp.
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
""" Base classes for DB backend implementation test
"""

import datetime
import operator

import mock
from oslo_config import cfg
from oslo_db import api
from oslo_db import exception as dbexc
from oslo_utils import timeutils
import pymongo

import ceilometer
from ceilometer.alarm.storage import models as alarm_models
from ceilometer.event.storage import models as event_models
from ceilometer.publisher import utils
from ceilometer import sample
from ceilometer import storage
from ceilometer.tests import constants
from ceilometer.tests import db as tests_db


class DBTestBase(tests_db.TestBase):
    @staticmethod
    def create_side_effect(method, exception_type, test_exception):
        def side_effect(*args, **kwargs):
            if test_exception.pop():
                raise exception_type
            else:
                return method(*args, **kwargs)
        return side_effect

    def create_and_store_sample(self, timestamp=datetime.datetime.utcnow(),
                                metadata=None,
                                name='instance',
                                sample_type=sample.TYPE_CUMULATIVE, unit='',
                                volume=1, user_id='user-id',
                                project_id='project-id',
                                resource_id='resource-id', source=None):
        metadata = metadata or {'display_name': 'test-server',
                                'tag': 'self.counter'}
        s = sample.Sample(
            name, sample_type, unit=unit, volume=volume, user_id=user_id,
            project_id=project_id, resource_id=resource_id,
            timestamp=timestamp,
            resource_metadata=metadata, source=source
        )
        msg = utils.meter_message_from_counter(
            s, self.CONF.publisher.telemetry_secret
        )
        self.conn.record_metering_data(msg)
        return msg

    def setUp(self):
        super(DBTestBase, self).setUp()
        patcher = mock.patch.object(timeutils, 'utcnow')
        self.addCleanup(patcher.stop)
        self.mock_utcnow = patcher.start()
        self.mock_utcnow.return_value = datetime.datetime(2015, 7, 2, 10, 39)
        self.prepare_data()

    def prepare_data(self):
        original_timestamps = [(2012, 7, 2, 10, 40), (2012, 7, 2, 10, 41),
                               (2012, 7, 2, 10, 41), (2012, 7, 2, 10, 42),
                               (2012, 7, 2, 10, 43)]

        timestamps_for_test_samples_default_order = [(2012, 7, 2, 10, 44),
                                                     (2011, 5, 30, 18, 3),
                                                     (2012, 12, 1, 1, 25),
                                                     (2012, 2, 29, 6, 59),
                                                     (2013, 5, 31, 23, 7)]
        timestamp_list = (original_timestamps +
                          timestamps_for_test_samples_default_order)

        self.msgs = []

        self.msgs.append(self.create_and_store_sample(
            timestamp=datetime.datetime(2012, 7, 2, 10, 39),
            source='test-1')
        )
        self.msgs.append(self.create_and_store_sample(
            timestamp=datetime.datetime(*timestamp_list[0]),
            source='test-1')
        )
        self.msgs.append(self.create_and_store_sample(
            timestamp=datetime.datetime(*timestamp_list[1]),
            resource_id='resource-id-alternate',
            metadata={'display_name': 'test-server', 'tag': 'self.counter2'},
            source='test-2')
        )
        self.msgs.append(self.create_and_store_sample(
            timestamp=datetime.datetime(*timestamp_list[2]),
            resource_id='resource-id-alternate',
            user_id='user-id-alternate',
            metadata={'display_name': 'test-server', 'tag': 'self.counter3'},
            source='test-3')
        )

        start_idx = 3
        end_idx = len(timestamp_list)

        for i, ts in zip(range(start_idx - 1, end_idx - 1),
                         timestamp_list[start_idx:end_idx]):
            self.msgs.append(
                self.create_and_store_sample(
                    timestamp=datetime.datetime(*ts),
                    user_id='user-id-%s' % i,
                    project_id='project-id-%s' % i,
                    resource_id='resource-id-%s' % i,
                    metadata={
                        'display_name': 'test-server',
                        'tag': 'counter-%s' % i
                    },
                    source='test')
            )


class ResourceTest(DBTestBase,
                   tests_db.MixinTestsWithBackendScenarios):
    def prepare_data(self):
        super(ResourceTest, self).prepare_data()

        self.msgs.append(self.create_and_store_sample(
            timestamp=datetime.datetime(2012, 7, 2, 10, 39),
            user_id='mongodb_test',
            resource_id='resource-id-mongo_bad_key',
            project_id='project-id-test',
            metadata={'display.name': {'name.$1': 'test-server1',
                                       '$name_2': 'test-server2'},
                      'tag': 'self.counter'},
            source='test-4'
        ))

    def test_get_resources(self):
        expected_first_sample_timestamp = datetime.datetime(2012, 7, 2, 10, 39)
        expected_last_sample_timestamp = datetime.datetime(2012, 7, 2, 10, 40)
        msgs_sources = [msg['source'] for msg in self.msgs]
        resources = list(self.conn.get_resources())
        self.assertEqual(10, len(resources))
        for resource in resources:
            if resource.resource_id != 'resource-id':
                continue
            self.assertEqual(expected_first_sample_timestamp,
                             resource.first_sample_timestamp)
            self.assertEqual(expected_last_sample_timestamp,
                             resource.last_sample_timestamp)
            self.assertEqual('resource-id', resource.resource_id)
            self.assertEqual('project-id', resource.project_id)
            self.assertIn(resource.source, msgs_sources)
            self.assertEqual('user-id', resource.user_id)
            self.assertEqual('test-server', resource.metadata['display_name'])
            break
        else:
            self.fail('Never found resource-id')

    def test_get_resources_start_timestamp(self):
        timestamp = datetime.datetime(2012, 7, 2, 10, 42)
        expected = set(['resource-id-2', 'resource-id-3', 'resource-id-4',
                        'resource-id-6', 'resource-id-8'])

        resources = list(self.conn.get_resources(start_timestamp=timestamp))
        resource_ids = [r.resource_id for r in resources]
        self.assertEqual(expected, set(resource_ids))

        resources = list(self.conn.get_resources(start_timestamp=timestamp,
                                                 start_timestamp_op='ge'))
        resource_ids = [r.resource_id for r in resources]
        self.assertEqual(expected, set(resource_ids))

        resources = list(self.conn.get_resources(start_timestamp=timestamp,
                                                 start_timestamp_op='gt'))
        resource_ids = [r.resource_id for r in resources]
        expected.remove('resource-id-2')
        self.assertEqual(expected, set(resource_ids))

    def test_get_resources_end_timestamp(self):
        timestamp = datetime.datetime(2012, 7, 2, 10, 42)
        expected = set(['resource-id', 'resource-id-alternate',
                        'resource-id-5', 'resource-id-7',
                        'resource-id-mongo_bad_key'])

        resources = list(self.conn.get_resources(end_timestamp=timestamp))
        resource_ids = [r.resource_id for r in resources]
        self.assertEqual(expected, set(resource_ids))

        resources = list(self.conn.get_resources(end_timestamp=timestamp,
                                                 end_timestamp_op='lt'))
        resource_ids = [r.resource_id for r in resources]
        self.assertEqual(expected, set(resource_ids))

        resources = list(self.conn.get_resources(end_timestamp=timestamp,
                                                 end_timestamp_op='le'))
        resource_ids = [r.resource_id for r in resources]
        expected.add('resource-id-2')
        self.assertEqual(expected, set(resource_ids))

    def test_get_resources_both_timestamps(self):
        start_ts = datetime.datetime(2012, 7, 2, 10, 42)
        end_ts = datetime.datetime(2012, 7, 2, 10, 43)

        resources = list(self.conn.get_resources(start_timestamp=start_ts,
                                                 end_timestamp=end_ts))
        resource_ids = [r.resource_id for r in resources]
        self.assertEqual(set(['resource-id-2']), set(resource_ids))

        resources = list(self.conn.get_resources(start_timestamp=start_ts,
                                                 end_timestamp=end_ts,
                                                 start_timestamp_op='ge',
                                                 end_timestamp_op='lt'))
        resource_ids = [r.resource_id for r in resources]
        self.assertEqual(set(['resource-id-2']), set(resource_ids))

        resources = list(self.conn.get_resources(start_timestamp=start_ts,
                                                 end_timestamp=end_ts,
                                                 start_timestamp_op='gt',
                                                 end_timestamp_op='lt'))
        resource_ids = [r.resource_id for r in resources]
        self.assertEqual(0, len(resource_ids))

        resources = list(self.conn.get_resources(start_timestamp=start_ts,
                                                 end_timestamp=end_ts,
                                                 start_timestamp_op='gt',
                                                 end_timestamp_op='le'))
        resource_ids = [r.resource_id for r in resources]
        self.assertEqual(set(['resource-id-3']), set(resource_ids))

        resources = list(self.conn.get_resources(start_timestamp=start_ts,
                                                 end_timestamp=end_ts,
                                                 start_timestamp_op='ge',
                                                 end_timestamp_op='le'))
        resource_ids = [r.resource_id for r in resources]
        self.assertEqual(set(['resource-id-2', 'resource-id-3']),
                         set(resource_ids))

    def test_get_resources_by_source(self):
        resources = list(self.conn.get_resources(source='test-1'))
        self.assertEqual(1, len(resources))
        ids = set(r.resource_id for r in resources)
        self.assertEqual(set(['resource-id']), ids)

    def test_get_resources_by_user(self):
        resources = list(self.conn.get_resources(user='user-id'))
        self.assertTrue(len(resources) == 2 or len(resources) == 1)
        ids = set(r.resource_id for r in resources)
        # tolerate storage driver only reporting latest owner of resource
        resources_ever_owned_by = set(['resource-id',
                                       'resource-id-alternate'])
        resources_now_owned_by = set(['resource-id'])
        self.assertTrue(ids == resources_ever_owned_by or
                        ids == resources_now_owned_by,
                        'unexpected resources: %s' % ids)

    def test_get_resources_by_alternate_user(self):
        resources = list(self.conn.get_resources(user='user-id-alternate'))
        self.assertEqual(1, len(resources))
        # only a single resource owned by this user ever
        self.assertEqual('resource-id-alternate', resources[0].resource_id)

    def test_get_resources_by_project(self):
        resources = list(self.conn.get_resources(project='project-id'))
        self.assertEqual(2, len(resources))
        ids = set(r.resource_id for r in resources)
        self.assertEqual(set(['resource-id', 'resource-id-alternate']), ids)

    def test_get_resources_by_metaquery(self):
        q = {'metadata.display_name': 'test-server'}
        resources = list(self.conn.get_resources(metaquery=q))
        self.assertEqual(9, len(resources))

    def test_get_resources_by_metaquery_key_with_dot_in_metadata(self):
        q = {'metadata.display.name.$name_2': 'test-server2',
             'metadata.display.name.name.$1': 'test-server1'}
        resources = list(self.conn.get_resources(metaquery=q))
        self.assertEqual(1, len(resources))

    def test_get_resources_by_empty_metaquery(self):
        resources = list(self.conn.get_resources(metaquery={}))
        self.assertEqual(10, len(resources))

    def test_get_resources_most_recent_metadata_all(self):
        resources = self.conn.get_resources()
        expected_tags = ['self.counter', 'self.counter3', 'counter-2',
                         'counter-3', 'counter-4', 'counter-5', 'counter-6',
                         'counter-7', 'counter-8']

        for resource in resources:
            self.assertIn(resource.metadata['tag'], expected_tags)

    def test_get_resources_most_recent_metadata_single(self):
        resource = list(
            self.conn.get_resources(resource='resource-id-alternate')
        )[0]
        expected_tag = 'self.counter3'
        self.assertEqual(expected_tag, resource.metadata['tag'])


class ResourceTestOrdering(DBTestBase,
                           tests_db.MixinTestsWithBackendScenarios):
    def prepare_data(self):
        sample_timings = [('resource-id-1', [(2013, 8, 10, 10, 43),
                                             (2013, 8, 10, 10, 44),
                                             (2013, 8, 10, 10, 42),
                                             (2013, 8, 10, 10, 49),
                                             (2013, 8, 10, 10, 47)]),
                          ('resource-id-2', [(2013, 8, 10, 10, 43),
                                             (2013, 8, 10, 10, 48),
                                             (2013, 8, 10, 10, 42),
                                             (2013, 8, 10, 10, 48),
                                             (2013, 8, 10, 10, 47)]),
                          ('resource-id-3', [(2013, 8, 10, 10, 43),
                                             (2013, 8, 10, 10, 44),
                                             (2013, 8, 10, 10, 50),
                                             (2013, 8, 10, 10, 49),
                                             (2013, 8, 10, 10, 47)])]

        counter = 0
        for resource, timestamps in sample_timings:
            for timestamp in timestamps:
                self.create_and_store_sample(
                    timestamp=datetime.datetime(*timestamp),
                    resource_id=resource,
                    user_id=str(counter % 2),
                    project_id=str(counter % 3),
                    metadata={
                        'display_name': 'test-server',
                        'tag': 'sample-%s' % counter
                    },
                    source='test'
                )
                counter += 1

    def test_get_resources_ordering_all(self):
        resources = list(self.conn.get_resources())
        expected = set([
            ('resource-id-1', 'sample-3'),
            ('resource-id-2', 'sample-8'),
            ('resource-id-3', 'sample-12')
        ])
        received = set([(r.resource_id, r.metadata['tag']) for r in resources])
        self.assertEqual(expected, received)

    def test_get_resources_ordering_single(self):
        resource = list(self.conn.get_resources(resource='resource-id-2'))[0]
        self.assertEqual('resource-id-2', resource.resource_id)
        self.assertEqual('sample-8', resource.metadata['tag'])


class MeterTest(DBTestBase,
                tests_db.MixinTestsWithBackendScenarios):

    def test_get_meters(self):
        msgs_sources = [msg['source'] for msg in self.msgs]
        results = list(self.conn.get_meters())
        self.assertEqual(9, len(results))
        for meter in results:
            self.assertIn(meter.source, msgs_sources)

    def test_get_meters_by_user(self):
        results = list(self.conn.get_meters(user='user-id'))
        self.assertEqual(1, len(results))

    def test_get_meters_by_project(self):
        results = list(self.conn.get_meters(project='project-id'))
        self.assertEqual(2, len(results))

    def test_get_meters_by_metaquery(self):
        q = {'metadata.display_name': 'test-server'}
        results = list(self.conn.get_meters(metaquery=q))
        self.assertIsNotEmpty(results)
        self.assertEqual(9, len(results))

    def test_get_meters_by_empty_metaquery(self):
        results = list(self.conn.get_meters(metaquery={}))
        self.assertEqual(9, len(results))


class RawSampleTest(DBTestBase,
                    tests_db.MixinTestsWithBackendScenarios):

    def prepare_data(self):
        super(RawSampleTest, self).prepare_data()

        self.msgs.append(self.create_and_store_sample(
            timestamp=datetime.datetime(2012, 7, 2, 10, 39),
            user_id='mongodb_test',
            resource_id='resource-id-mongo_bad_key',
            project_id='project-id-test',
            metadata={'display.name': {'name.$1': 'test-server1',
                                       '$name_2': 'test-server2'},
                      'tag': 'self.counter'},
            source='test-4'
        ))

    def test_get_sample_counter_volume(self):
        # NOTE(idegtiarov) Because wsme expected a float type of data this test
        # checks type of counter_volume received from database.
        f = storage.SampleFilter()
        result = next(self.conn.get_samples(f, limit=1))
        self.assertIsInstance(result.counter_volume, float)

    def test_get_samples_limit_zero(self):
        f = storage.SampleFilter()
        results = list(self.conn.get_samples(f, limit=0))
        self.assertEqual(0, len(results))

    def test_get_samples_limit(self):
        f = storage.SampleFilter()
        results = list(self.conn.get_samples(f, limit=3))
        self.assertEqual(3, len(results))
        for result in results:
            self.assertTimestampEqual(timeutils.utcnow(), result.recorded_at)

    def test_get_samples_in_default_order(self):
        f = storage.SampleFilter()
        prev_timestamp = None
        for sample_item in self.conn.get_samples(f):
            if prev_timestamp is not None:
                self.assertTrue(prev_timestamp >= sample_item.timestamp)
            prev_timestamp = sample_item.timestamp

    def test_get_samples_by_user(self):
        f = storage.SampleFilter(user='user-id')
        results = list(self.conn.get_samples(f))
        self.assertEqual(3, len(results))
        for meter in results:
            d = meter.as_dict()
            self.assertTimestampEqual(timeutils.utcnow(), d['recorded_at'])
            del d['recorded_at']
            self.assertIn(d, self.msgs[:3])

    def test_get_samples_by_user_limit(self):
        f = storage.SampleFilter(user='user-id')
        results = list(self.conn.get_samples(f, limit=1))
        self.assertEqual(1, len(results))

    def test_get_samples_by_user_limit_bigger(self):
        f = storage.SampleFilter(user='user-id')
        results = list(self.conn.get_samples(f, limit=42))
        self.assertEqual(3, len(results))

    def test_get_samples_by_project(self):
        f = storage.SampleFilter(project='project-id')
        results = list(self.conn.get_samples(f))
        self.assertIsNotNone(results)
        for meter in results:
            d = meter.as_dict()
            self.assertTimestampEqual(timeutils.utcnow(), d['recorded_at'])
            del d['recorded_at']
            self.assertIn(d, self.msgs[:4])

    def test_get_samples_by_resource(self):
        f = storage.SampleFilter(user='user-id', resource='resource-id')
        results = list(self.conn.get_samples(f))
        self.assertEqual(2, len(results))
        d = results[1].as_dict()
        self.assertEqual(timeutils.utcnow(), d['recorded_at'])
        del d['recorded_at']
        self.assertEqual(self.msgs[0], d)

    def test_get_samples_by_metaquery(self):
        q = {'metadata.display_name': 'test-server'}
        f = storage.SampleFilter(metaquery=q)
        results = list(self.conn.get_samples(f))
        self.assertIsNotNone(results)
        for meter in results:
            d = meter.as_dict()
            self.assertTimestampEqual(timeutils.utcnow(), d['recorded_at'])
            del d['recorded_at']
            self.assertIn(d, self.msgs)

    def test_get_samples_by_metaquery_key_with_dot_in_metadata(self):
        q = {'metadata.display.name.name.$1': 'test-server1',
             'metadata.display.name.$name_2': 'test-server2'}
        f = storage.SampleFilter(metaquery=q)
        results = list(self.conn.get_samples(f))
        self.assertIsNotNone(results)
        self.assertEqual(1, len(results))

    def test_get_samples_by_start_time(self):
        timestamp = datetime.datetime(2012, 7, 2, 10, 41)
        f = storage.SampleFilter(
            user='user-id',
            start_timestamp=timestamp,
        )

        results = list(self.conn.get_samples(f))
        self.assertEqual(1, len(results))
        self.assertEqual(timestamp, results[0].timestamp)

        f.start_timestamp_op = 'ge'
        results = list(self.conn.get_samples(f))
        self.assertEqual(1, len(results))
        self.assertEqual(timestamp, results[0].timestamp)

        f.start_timestamp_op = 'gt'
        results = list(self.conn.get_samples(f))
        self.assertEqual(0, len(results))

    def test_get_samples_by_end_time(self):
        timestamp = datetime.datetime(2012, 7, 2, 10, 40)
        f = storage.SampleFilter(
            user='user-id',
            end_timestamp=timestamp,
        )

        results = list(self.conn.get_samples(f))
        self.assertEqual(1, len(results))

        f.end_timestamp_op = 'lt'
        results = list(self.conn.get_samples(f))
        self.assertEqual(1, len(results))

        f.end_timestamp_op = 'le'
        results = list(self.conn.get_samples(f))
        self.assertEqual(2, len(results))
        self.assertEqual(datetime.datetime(2012, 7, 2, 10, 39),
                         results[1].timestamp)

    def test_get_samples_by_both_times(self):
        start_ts = datetime.datetime(2012, 7, 2, 10, 42)
        end_ts = datetime.datetime(2012, 7, 2, 10, 43)
        f = storage.SampleFilter(
            start_timestamp=start_ts,
            end_timestamp=end_ts,
        )

        results = list(self.conn.get_samples(f))
        self.assertEqual(1, len(results))
        self.assertEqual(start_ts, results[0].timestamp)

        f.start_timestamp_op = 'gt'
        f.end_timestamp_op = 'lt'
        results = list(self.conn.get_samples(f))
        self.assertEqual(0, len(results))

        f.start_timestamp_op = 'ge'
        f.end_timestamp_op = 'lt'
        results = list(self.conn.get_samples(f))
        self.assertEqual(1, len(results))
        self.assertEqual(start_ts, results[0].timestamp)

        f.start_timestamp_op = 'gt'
        f.end_timestamp_op = 'le'
        results = list(self.conn.get_samples(f))
        self.assertEqual(1, len(results))
        self.assertEqual(end_ts, results[0].timestamp)

        f.start_timestamp_op = 'ge'
        f.end_timestamp_op = 'le'
        results = list(self.conn.get_samples(f))
        self.assertEqual(2, len(results))
        self.assertEqual(end_ts, results[0].timestamp)
        self.assertEqual(start_ts, results[1].timestamp)

    def test_get_samples_by_name(self):
        f = storage.SampleFilter(user='user-id', meter='no-such-meter')
        results = list(self.conn.get_samples(f))
        self.assertIsEmpty(results)

    def test_get_samples_by_name2(self):
        f = storage.SampleFilter(user='user-id', meter='instance')
        results = list(self.conn.get_samples(f))
        self.assertIsNotEmpty(results)

    def test_get_samples_by_source(self):
        f = storage.SampleFilter(source='test-1')
        results = list(self.conn.get_samples(f))
        self.assertEqual(2, len(results))

    @tests_db.run_with('sqlite', 'mysql', 'pgsql', 'hbase', 'db2')
    def test_clear_metering_data(self):
        # NOTE(jd) Override this test in MongoDB because our code doesn't clear
        # the collections, this is handled by MongoDB TTL feature.

        self.mock_utcnow.return_value = datetime.datetime(2012, 7, 2, 10, 45)
        self.conn.clear_expired_metering_data(3 * 60)
        f = storage.SampleFilter(meter='instance')
        results = list(self.conn.get_samples(f))
        self.assertEqual(5, len(results))
        results = list(self.conn.get_resources())
        self.assertEqual(5, len(results))

    @tests_db.run_with('sqlite', 'mysql', 'pgsql', 'hbase', 'db2')
    def test_clear_metering_data_no_data_to_remove(self):
        # NOTE(jd) Override this test in MongoDB because our code doesn't clear
        # the collections, this is handled by MongoDB TTL feature.

        self.mock_utcnow.return_value = datetime.datetime(2010, 7, 2, 10, 45)
        self.conn.clear_expired_metering_data(3 * 60)
        f = storage.SampleFilter(meter='instance')
        results = list(self.conn.get_samples(f))
        self.assertEqual(12, len(results))
        results = list(self.conn.get_resources())
        self.assertEqual(10, len(results))

    @tests_db.run_with('sqlite', 'mysql', 'pgsql')
    def test_clear_metering_data_expire_samples_only(self):

        cfg.CONF.set_override('sql_expire_samples_only', True)
        self.mock_utcnow.return_value = datetime.datetime(2012, 7, 2, 10, 45)
        self.conn.clear_expired_metering_data(4 * 60)
        f = storage.SampleFilter(meter='instance')
        results = list(self.conn.get_samples(f))
        self.assertEqual(7, len(results))
        results = list(self.conn.get_resources())
        self.assertEqual(6, len(results))

    @tests_db.run_with('sqlite', 'mysql', 'pgsql')
    def test_record_metering_data_retry_success_on_deadlock(self):
        raise_deadlock = [False, True]
        self.CONF.set_override('max_retries', 2, group='database')

        s = sample.Sample('instance', sample.TYPE_CUMULATIVE, unit='',
                          volume=1, user_id='user_id',
                          project_id='project_id',
                          resource_id='resource_id',
                          timestamp=datetime.datetime.utcnow(),
                          resource_metadata={'display_name': 'test-server',
                                             'tag': 'self.counter'},
                          source=None)

        msg = utils.meter_message_from_counter(
            s, self.CONF.publisher.telemetry_secret
        )

        mock_resource_create = mock.patch.object(self.conn, "_create_resource")

        mock_resource_create.side_effect = self.create_side_effect(
            self.conn._create_resource, dbexc.DBDeadlock, raise_deadlock)
        with mock.patch.object(api.time, 'sleep') as retry_sleep:
            self.conn.record_metering_data(msg)
            self.assertEqual(1, retry_sleep.call_count)

        f = storage.SampleFilter(meter='instance')
        results = list(self.conn.get_samples(f))
        self.assertEqual(13, len(results))

    @tests_db.run_with('sqlite', 'mysql', 'pgsql')
    def test_record_metering_data_retry_failure_on_deadlock(self):
        raise_deadlock = [True, True, True]
        self.CONF.set_override('max_retries', 3, group='database')

        s = sample.Sample('instance', sample.TYPE_CUMULATIVE, unit='',
                          volume=1, user_id='user_id',
                          project_id='project_id',
                          resource_id='resource_id',
                          timestamp=datetime.datetime.utcnow(),
                          resource_metadata={'display_name': 'test-server',
                                             'tag': 'self.counter'},
                          source=None)

        msg = utils.meter_message_from_counter(
            s, self.CONF.publisher.telemetry_secret
        )

        mock_resource_create = mock.patch.object(self.conn, "_create_resource")

        mock_resource_create.side_effect = self.create_side_effect(
            self.conn._create_resource, dbexc.DBDeadlock, raise_deadlock)
        with mock.patch.object(api.time, 'sleep') as retry_sleep:
            try:
                self.conn.record_metering_data(msg)
            except dbexc.DBError as err:
                self.assertIn('DBDeadlock', str(type(err)))
                self.assertEqual(3, retry_sleep.call_count)

    @tests_db.run_with('sqlite', 'mysql', 'pgsql', 'hbase', 'db2')
    def test_clear_metering_data_with_alarms(self):
        # NOTE(jd) Override this test in MongoDB because our code doesn't clear
        # the collections, this is handled by MongoDB TTL feature.
        alarm = alarm_models.Alarm(alarm_id='r3d',
                                   enabled=True,
                                   type='threshold',
                                   name='red-alert',
                                   description='my red-alert',
                                   timestamp=constants.MIN_DATETIME,
                                   user_id='user-id',
                                   project_id='project-id',
                                   state="insufficient data",
                                   state_timestamp=constants.MIN_DATETIME,
                                   ok_actions=[],
                                   alarm_actions=['http://nowhere/alarms'],
                                   insufficient_data_actions=[],
                                   repeat_actions=False,
                                   time_constraints=[],
                                   rule=dict(comparison_operator='eq',
                                             threshold=36,
                                             statistic='count',
                                             evaluation_periods=1,
                                             period=60,
                                             meter_name='test.one',
                                             query=[{'field': 'key',
                                                     'op': 'eq',
                                                     'value': 'value',
                                                     'type': 'string'}]),
                                   )

        self.alarm_conn.create_alarm(alarm)
        self.mock_utcnow.return_value = datetime.datetime(2012, 7, 2, 10, 45)
        self.conn.clear_expired_metering_data(5)
        f = storage.SampleFilter(meter='instance')
        results = list(self.conn.get_samples(f))
        self.assertEqual(2, len(results))
        results = list(self.conn.get_resources())
        self.assertEqual(2, len(results))


class ComplexSampleQueryTest(DBTestBase,
                             tests_db.MixinTestsWithBackendScenarios):
    def setUp(self):
        super(ComplexSampleQueryTest, self).setUp()
        self.complex_filter = {
            "and":
            [{"or":
              [{"=": {"resource_id": "resource-id-42"}},
               {"=": {"resource_id": "resource-id-44"}}]},
             {"and":
              [{"=": {"counter_name": "cpu_util"}},
               {"and":
                [{">": {"counter_volume": 0.4}},
                 {"not": {">": {"counter_volume": 0.8}}}]}]}]}
        or_expression = [{"=": {"resource_id": "resource-id-42"}},
                         {"=": {"resource_id": "resource-id-43"}},
                         {"=": {"resource_id": "resource-id-44"}}]
        and_expression = [{">": {"counter_volume": 0.4}},
                          {"not": {">": {"counter_volume": 0.8}}}]
        self.complex_filter_list = {"and":
                                    [{"or": or_expression},
                                     {"and":
                                      [{"=": {"counter_name": "cpu_util"}},
                                       {"and": and_expression}]}]}
        in_expression = {"in": {"resource_id": ["resource-id-42",
                                                "resource-id-43",
                                                "resource-id-44"]}}
        self.complex_filter_in = {"and":
                                  [in_expression,
                                   {"and":
                                    [{"=": {"counter_name": "cpu_util"}},
                                     {"and": and_expression}]}]}

    def _create_samples(self):
        for resource in range(42, 45):
            for volume in [0.79, 0.41, 0.4, 0.8, 0.39, 0.81]:
                metadata = {'a_string_key': "meta-value" + str(volume),
                            'a_float_key': volume,
                            'an_int_key': resource,
                            'a_bool_key': (resource == 43)}

                self.create_and_store_sample(resource_id="resource-id-%s"
                                                         % resource,
                                             metadata=metadata,
                                             name="cpu_util",
                                             volume=volume)

    def test_no_filter(self):
        results = list(self.conn.query_samples())
        self.assertEqual(len(self.msgs), len(results))
        for sample_item in results:
            d = sample_item.as_dict()
            del d['recorded_at']
            self.assertIn(d, self.msgs)

    def test_query_complex_filter_with_regexp(self):
        self._create_samples()
        complex_regex_filter = {"and": [
            {"=~": {"resource_id": "resource-id.*"}},
            {"=": {"counter_volume": 0.4}}]}
        results = list(
            self.conn.query_samples(filter_expr=complex_regex_filter))
        self.assertEqual(3, len(results))
        for sample_item in results:
            self.assertIn(sample_item.resource_id,
                          set(["resource-id-42",
                               "resource-id-43",
                               "resource-id-44"]))

    def test_query_complex_filter_with_regexp_metadata(self):
        self._create_samples()
        complex_regex_filter = {"and": [
            {"=~": {"resource_metadata.a_string_key": "meta-value.*"}},
            {"=": {"counter_volume": 0.4}}]}
        results = list(
            self.conn.query_samples(filter_expr=complex_regex_filter))
        self.assertEqual(3, len(results))
        for sample_item in results:
            self.assertEqual("meta-value0.4",
                             sample_item.resource_metadata['a_string_key'])

    def test_no_filter_with_zero_limit(self):
        limit = 0
        results = list(self.conn.query_samples(limit=limit))
        self.assertEqual(limit, len(results))

    def test_no_filter_with_limit(self):
        limit = 3
        results = list(self.conn.query_samples(limit=limit))
        self.assertEqual(limit, len(results))

    def test_query_simple_filter(self):
        simple_filter = {"=": {"resource_id": "resource-id-8"}}
        results = list(self.conn.query_samples(filter_expr=simple_filter))
        self.assertEqual(1, len(results))
        for sample_item in results:
            self.assertEqual("resource-id-8", sample_item.resource_id)

    def test_query_simple_filter_with_not_equal_relation(self):
        simple_filter = {"!=": {"resource_id": "resource-id-8"}}
        results = list(self.conn.query_samples(filter_expr=simple_filter))
        self.assertEqual(len(self.msgs) - 1, len(results))
        for sample_item in results:
            self.assertNotEqual("resource-id-8", sample_item.resource_id)

    def test_query_complex_filter(self):
        self._create_samples()
        results = list(self.conn.query_samples(filter_expr=(
                                               self.complex_filter)))
        self.assertEqual(6, len(results))
        for sample_item in results:
            self.assertIn(sample_item.resource_id,
                          set(["resource-id-42", "resource-id-44"]))
            self.assertEqual("cpu_util", sample_item.counter_name)
            self.assertTrue(sample_item.counter_volume > 0.4)
            self.assertTrue(sample_item.counter_volume <= 0.8)

    def test_query_complex_filter_with_limit(self):
        self._create_samples()
        limit = 3
        results = list(self.conn.query_samples(filter_expr=self.complex_filter,
                                               limit=limit))
        self.assertEqual(limit, len(results))

    def test_query_complex_filter_with_simple_orderby(self):
        self._create_samples()
        expected_volume_order = [0.41, 0.41, 0.79, 0.79, 0.8, 0.8]
        orderby = [{"counter_volume": "asc"}]
        results = list(self.conn.query_samples(filter_expr=self.complex_filter,
                                               orderby=orderby))
        self.assertEqual(expected_volume_order,
                         [s.counter_volume for s in results])

    def test_query_complex_filter_with_complex_orderby(self):
        self._create_samples()
        expected_volume_order = [0.41, 0.41, 0.79, 0.79, 0.8, 0.8]
        expected_resource_id_order = ["resource-id-44", "resource-id-42",
                                      "resource-id-44", "resource-id-42",
                                      "resource-id-44", "resource-id-42"]

        orderby = [{"counter_volume": "asc"}, {"resource_id": "desc"}]

        results = list(self.conn.query_samples(filter_expr=self.complex_filter,
                       orderby=orderby))

        self.assertEqual(expected_volume_order,
                         [s.counter_volume for s in results])
        self.assertEqual(expected_resource_id_order,
                         [s.resource_id for s in results])

    def test_query_complex_filter_with_list(self):
        self._create_samples()
        results = list(
            self.conn.query_samples(filter_expr=self.complex_filter_list))
        self.assertEqual(9, len(results))
        for sample_item in results:
            self.assertIn(sample_item.resource_id,
                          set(["resource-id-42",
                               "resource-id-43",
                               "resource-id-44"]))
            self.assertEqual("cpu_util", sample_item.counter_name)
            self.assertTrue(sample_item.counter_volume > 0.4)
            self.assertTrue(sample_item.counter_volume <= 0.8)

    def test_query_complex_filter_with_list_with_limit(self):
        self._create_samples()
        limit = 3
        results = list(
            self.conn.query_samples(filter_expr=self.complex_filter_list,
                                    limit=limit))
        self.assertEqual(limit, len(results))

    def test_query_complex_filter_with_list_with_simple_orderby(self):
        self._create_samples()
        expected_volume_order = [0.41, 0.41, 0.41, 0.79, 0.79,
                                 0.79, 0.8, 0.8, 0.8]
        orderby = [{"counter_volume": "asc"}]
        results = list(
            self.conn.query_samples(filter_expr=self.complex_filter_list,
                                    orderby=orderby))
        self.assertEqual(expected_volume_order,
                         [s.counter_volume for s in results])

    def test_query_complex_filterwith_list_with_complex_orderby(self):
        self._create_samples()
        expected_volume_order = [0.41, 0.41, 0.41, 0.79, 0.79,
                                 0.79, 0.8, 0.8, 0.8]
        expected_resource_id_order = ["resource-id-44", "resource-id-43",
                                      "resource-id-42", "resource-id-44",
                                      "resource-id-43", "resource-id-42",
                                      "resource-id-44", "resource-id-43",
                                      "resource-id-42"]

        orderby = [{"counter_volume": "asc"}, {"resource_id": "desc"}]

        results = list(
            self.conn.query_samples(filter_expr=self.complex_filter_list,
                                    orderby=orderby))

        self.assertEqual(expected_volume_order,
                         [s.counter_volume for s in results])
        self.assertEqual(expected_resource_id_order,
                         [s.resource_id for s in results])

    def test_query_complex_filter_with_wrong_order_in_orderby(self):
        self._create_samples()

        orderby = [{"counter_volume": "not valid order"},
                   {"resource_id": "desc"}]

        query = lambda: list(self.conn.query_samples(filter_expr=(
                                                     self.complex_filter),
                                                     orderby=orderby))
        self.assertRaises(KeyError, query)

    def test_query_complex_filter_with_in(self):
        self._create_samples()
        results = list(
            self.conn.query_samples(filter_expr=self.complex_filter_in))
        self.assertEqual(9, len(results))
        for sample_item in results:
            self.assertIn(sample_item.resource_id,
                          set(["resource-id-42",
                               "resource-id-43",
                               "resource-id-44"]))
            self.assertEqual("cpu_util", sample_item.counter_name)
            self.assertTrue(sample_item.counter_volume > 0.4)
            self.assertTrue(sample_item.counter_volume <= 0.8)

    def test_query_simple_metadata_filter(self):
        self._create_samples()

        filter_expr = {"=": {"resource_metadata.a_bool_key": True}}

        results = list(self.conn.query_samples(filter_expr=filter_expr))

        self.assertEqual(6, len(results))
        for sample_item in results:
            self.assertTrue(sample_item.resource_metadata["a_bool_key"])

    def test_query_simple_metadata_with_in_op(self):
        self._create_samples()

        filter_expr = {"in": {"resource_metadata.an_int_key": [42, 43]}}

        results = list(self.conn.query_samples(filter_expr=filter_expr))

        self.assertEqual(12, len(results))
        for sample_item in results:
            self.assertIn(sample_item.resource_metadata["an_int_key"],
                          [42, 43])

    def test_query_complex_metadata_filter(self):
        self._create_samples()
        subfilter = {"or": [{"=": {"resource_metadata.a_string_key":
                                   "meta-value0.81"}},
                            {"<=": {"resource_metadata.a_float_key": 0.41}}]}
        filter_expr = {"and": [{">": {"resource_metadata.an_int_key": 42}},
                               subfilter]}

        results = list(self.conn.query_samples(filter_expr=filter_expr))

        self.assertEqual(8, len(results))
        for sample_item in results:
            self.assertTrue((sample_item.resource_metadata["a_string_key"] ==
                            "meta-value0.81" or
                             sample_item.resource_metadata["a_float_key"] <=
                             0.41))
            self.assertTrue(sample_item.resource_metadata["an_int_key"] > 42)

    def test_query_mixed_data_and_metadata_filter(self):
        self._create_samples()
        subfilter = {"or": [{"=": {"resource_metadata.a_string_key":
                                   "meta-value0.81"}},
                            {"<=": {"resource_metadata.a_float_key": 0.41}}]}

        filter_expr = {"and": [{"=": {"resource_id": "resource-id-42"}},
                               subfilter]}

        results = list(self.conn.query_samples(filter_expr=filter_expr))

        self.assertEqual(4, len(results))
        for sample_item in results:
            self.assertTrue((sample_item.resource_metadata["a_string_key"] ==
                            "meta-value0.81" or
                             sample_item.resource_metadata["a_float_key"] <=
                             0.41))
            self.assertEqual("resource-id-42", sample_item.resource_id)

    def test_query_non_existing_metadata_with_result(self):
        self._create_samples()

        filter_expr = {
            "or": [{"=": {"resource_metadata.a_string_key":
                          "meta-value0.81"}},
                   {"<=": {"resource_metadata.key_not_exists": 0.41}}]}

        results = list(self.conn.query_samples(filter_expr=filter_expr))

        self.assertEqual(3, len(results))
        for sample_item in results:
            self.assertEqual("meta-value0.81",
                             sample_item.resource_metadata["a_string_key"])

    def test_query_non_existing_metadata_without_result(self):
        self._create_samples()

        filter_expr = {
            "or": [{"=": {"resource_metadata.key_not_exists":
                          "meta-value0.81"}},
                   {"<=": {"resource_metadata.key_not_exists": 0.41}}]}

        results = list(self.conn.query_samples(filter_expr=filter_expr))
        self.assertEqual(0, len(results))

    def test_query_negated_metadata(self):
        self._create_samples()

        filter_expr = {
            "and": [{"=": {"resource_id": "resource-id-42"}},
                    {"not": {"or": [{">": {"resource_metadata.an_int_key":
                                           43}},
                                    {"<=": {"resource_metadata.a_float_key":
                                            0.41}}]}}]}

        results = list(self.conn.query_samples(filter_expr=filter_expr))

        self.assertEqual(3, len(results))
        for sample_item in results:
            self.assertEqual("resource-id-42", sample_item.resource_id)
            self.assertTrue(sample_item.resource_metadata["an_int_key"] <= 43)
            self.assertTrue(sample_item.resource_metadata["a_float_key"] >
                            0.41)

    def test_query_negated_complex_expression(self):
        self._create_samples()
        filter_expr = {
            "and":
            [{"=": {"counter_name": "cpu_util"}},
             {"not":
              {"or":
               [{"or":
                 [{"=": {"resource_id": "resource-id-42"}},
                  {"=": {"resource_id": "resource-id-44"}}]},
                {"and":
                 [{">": {"counter_volume": 0.4}},
                  {"<": {"counter_volume": 0.8}}]}]}}]}

        results = list(self.conn.query_samples(filter_expr=filter_expr))

        self.assertEqual(4, len(results))
        for sample_item in results:
            self.assertEqual("resource-id-43", sample_item.resource_id)
            self.assertIn(sample_item.counter_volume, [0.39, 0.4, 0.8, 0.81])
            self.assertEqual("cpu_util", sample_item.counter_name)

    def test_query_with_double_negation(self):
        self._create_samples()
        filter_expr = {
            "and":
            [{"=": {"counter_name": "cpu_util"}},
             {"not":
              {"or":
               [{"or":
                 [{"=": {"resource_id": "resource-id-42"}},
                  {"=": {"resource_id": "resource-id-44"}}]},
                {"and": [{"not": {"<=": {"counter_volume": 0.4}}},
                         {"<": {"counter_volume": 0.8}}]}]}}]}

        results = list(self.conn.query_samples(filter_expr=filter_expr))

        self.assertEqual(4, len(results))
        for sample_item in results:
            self.assertEqual("resource-id-43", sample_item.resource_id)
            self.assertIn(sample_item.counter_volume, [0.39, 0.4, 0.8, 0.81])
            self.assertEqual("cpu_util", sample_item.counter_name)

    def test_query_negate_not_equal(self):
        self._create_samples()
        filter_expr = {"not": {"!=": {"resource_id": "resource-id-43"}}}

        results = list(self.conn.query_samples(filter_expr=filter_expr))

        self.assertEqual(6, len(results))
        for sample_item in results:
            self.assertEqual("resource-id-43", sample_item.resource_id)

    def test_query_negated_in_op(self):
        self._create_samples()
        filter_expr = {
            "and": [{"not": {"in": {"counter_volume": [0.39, 0.4, 0.79]}}},
                    {"=": {"resource_id": "resource-id-42"}}]}

        results = list(self.conn.query_samples(filter_expr=filter_expr))

        self.assertEqual(3, len(results))
        for sample_item in results:
            self.assertIn(sample_item.counter_volume,
                          [0.41, 0.8, 0.81])


class StatisticsTest(DBTestBase,
                     tests_db.MixinTestsWithBackendScenarios):

    def prepare_data(self):
        for i in range(3):
            c = sample.Sample(
                'volume.size',
                'gauge',
                'GiB',
                5 + i,
                'user-id',
                'project1',
                'resource-id',
                timestamp=datetime.datetime(2012, 9, 25, 10 + i, 30 + i),
                resource_metadata={'display_name': 'test-volume',
                                   'tag': 'self.counter',
                                   },
                source='test',
            )
            msg = utils.meter_message_from_counter(
                c,
                secret='not-so-secret',
            )
            self.conn.record_metering_data(msg)
        for i in range(3):
            c = sample.Sample(
                'volume.size',
                'gauge',
                'GiB',
                8 + i,
                'user-5',
                'project2',
                'resource-6',
                timestamp=datetime.datetime(2012, 9, 25, 10 + i, 30 + i),
                resource_metadata={'display_name': 'test-volume',
                                   'tag': 'self.counter',
                                   },
                source='test',
            )
            msg = utils.meter_message_from_counter(
                c,
                secret='not-so-secret',
            )
            self.conn.record_metering_data(msg)
        for i in range(3):
            c = sample.Sample(
                'memory',
                'gauge',
                'MB',
                8 + i,
                'user-5',
                'project2',
                'resource-6',
                timestamp=datetime.datetime(2012, 9, 25, 10 + i, 30 + i),
                resource_metadata={},
                source='test',
            )
            msg = utils.meter_message_from_counter(
                c,
                secret='not-so-secret',
            )
            self.conn.record_metering_data(msg)

    def test_by_meter(self):
        f = storage.SampleFilter(
            meter='memory'
        )
        results = list(self.conn.get_meter_statistics(f))[0]
        self.assertEqual((datetime.datetime(2012, 9, 25, 12, 32)
                          - datetime.datetime(2012, 9, 25, 10, 30)).seconds,
                         results.duration)
        self.assertEqual(3, results.count)
        self.assertEqual('MB', results.unit)
        self.assertEqual(8, results.min)
        self.assertEqual(10, results.max)
        self.assertEqual(27, results.sum)
        self.assertEqual(9, results.avg)
        self.assertEqual(datetime.datetime(2012, 9, 25, 10, 30),
                         results.period_start)
        self.assertEqual(datetime.datetime(2012, 9, 25, 12, 32),
                         results.period_end)

    def test_by_user(self):
        f = storage.SampleFilter(
            user='user-5',
            meter='volume.size',
        )
        results = list(self.conn.get_meter_statistics(f))[0]
        self.assertEqual((datetime.datetime(2012, 9, 25, 12, 32)
                          - datetime.datetime(2012, 9, 25, 10, 30)).seconds,
                         results.duration)
        self.assertEqual(3, results.count)
        self.assertEqual('GiB', results.unit)
        self.assertEqual(8, results.min)
        self.assertEqual(10, results.max)
        self.assertEqual(27, results.sum)
        self.assertEqual(9, results.avg)

    def test_no_period_in_query(self):
        f = storage.SampleFilter(
            user='user-5',
            meter='volume.size',
        )
        results = list(self.conn.get_meter_statistics(f))[0]
        self.assertEqual(0, results.period)

    def test_period_is_int(self):
        f = storage.SampleFilter(
            meter='volume.size',
        )
        results = list(self.conn.get_meter_statistics(f))[0]
        self.assertIs(int, type(results.period))
        self.assertEqual(6, results.count)

    def test_by_user_period(self):
        f = storage.SampleFilter(
            user='user-5',
            meter='volume.size',
            start_timestamp='2012-09-25T10:28:00',
        )
        results = list(self.conn.get_meter_statistics(f, period=7200))
        self.assertEqual(2, len(results))
        self.assertEqual(set([datetime.datetime(2012, 9, 25, 10, 28),
                              datetime.datetime(2012, 9, 25, 12, 28)]),
                         set(r.period_start for r in results))
        self.assertEqual(set([datetime.datetime(2012, 9, 25, 12, 28),
                              datetime.datetime(2012, 9, 25, 14, 28)]),
                         set(r.period_end for r in results))
        r = results[0]
        self.assertEqual(datetime.datetime(2012, 9, 25, 10, 28),
                         r.period_start)
        self.assertEqual(2, r.count)
        self.assertEqual('GiB', r.unit)
        self.assertEqual(8.5, r.avg)
        self.assertEqual(8, r.min)
        self.assertEqual(9, r.max)
        self.assertEqual(17, r.sum)
        self.assertEqual(7200, r.period)
        self.assertIsInstance(r.period, int)
        expected_end = r.period_start + datetime.timedelta(seconds=7200)
        self.assertEqual(expected_end, r.period_end)
        self.assertEqual(3660, r.duration)
        self.assertEqual(datetime.datetime(2012, 9, 25, 10, 30),
                         r.duration_start)
        self.assertEqual(datetime.datetime(2012, 9, 25, 11, 31),
                         r.duration_end)

    def test_by_user_period_with_timezone(self):
        dates = [
            '2012-09-25T00:28:00-10:00',
            '2012-09-25T01:28:00-09:00',
            '2012-09-25T02:28:00-08:00',
            '2012-09-25T03:28:00-07:00',
            '2012-09-25T04:28:00-06:00',
            '2012-09-25T05:28:00-05:00',
            '2012-09-25T06:28:00-04:00',
            '2012-09-25T07:28:00-03:00',
            '2012-09-25T08:28:00-02:00',
            '2012-09-25T09:28:00-01:00',
            '2012-09-25T10:28:00Z',
            '2012-09-25T11:28:00+01:00',
            '2012-09-25T12:28:00+02:00',
            '2012-09-25T13:28:00+03:00',
            '2012-09-25T14:28:00+04:00',
            '2012-09-25T15:28:00+05:00',
            '2012-09-25T16:28:00+06:00',
            '2012-09-25T17:28:00+07:00',
            '2012-09-25T18:28:00+08:00',
            '2012-09-25T19:28:00+09:00',
            '2012-09-25T20:28:00+10:00',
            '2012-09-25T21:28:00+11:00',
            '2012-09-25T22:28:00+12:00',
        ]
        for date in dates:
            f = storage.SampleFilter(
                user='user-5',
                meter='volume.size',
                start_timestamp=date
            )
            results = list(self.conn.get_meter_statistics(f, period=7200))
            self.assertEqual(2, len(results))
            self.assertEqual(set([datetime.datetime(2012, 9, 25, 10, 28),
                                  datetime.datetime(2012, 9, 25, 12, 28)]),
                             set(r.period_start for r in results))
            self.assertEqual(set([datetime.datetime(2012, 9, 25, 12, 28),
                                  datetime.datetime(2012, 9, 25, 14, 28)]),
                             set(r.period_end for r in results))

    def test_by_user_period_start_end(self):
        f = storage.SampleFilter(
            user='user-5',
            meter='volume.size',
            start_timestamp='2012-09-25T10:28:00',
            end_timestamp='2012-09-25T11:28:00',
        )
        results = list(self.conn.get_meter_statistics(f, period=1800))
        self.assertEqual(1, len(results))
        r = results[0]
        self.assertEqual(datetime.datetime(2012, 9, 25, 10, 28),
                         r.period_start)
        self.assertEqual(1, r.count)
        self.assertEqual('GiB', r.unit)
        self.assertEqual(8, r.avg)
        self.assertEqual(8, r.min)
        self.assertEqual(8, r.max)
        self.assertEqual(8, r.sum)
        self.assertEqual(1800, r.period)
        self.assertEqual(r.period_start + datetime.timedelta(seconds=1800),
                         r.period_end)
        self.assertEqual(0, r.duration)
        self.assertEqual(datetime.datetime(2012, 9, 25, 10, 30),
                         r.duration_start)
        self.assertEqual(datetime.datetime(2012, 9, 25, 10, 30),
                         r.duration_end)

    def test_by_project(self):
        f = storage.SampleFilter(
            meter='volume.size',
            resource='resource-id',
            start_timestamp='2012-09-25T11:30:00',
            end_timestamp='2012-09-25T11:32:00',
        )
        results = list(self.conn.get_meter_statistics(f))[0]
        self.assertEqual(0, results.duration)
        self.assertEqual(1, results.count)
        self.assertEqual('GiB', results.unit)
        self.assertEqual(6, results.min)
        self.assertEqual(6, results.max)
        self.assertEqual(6, results.sum)
        self.assertEqual(6, results.avg)

    def test_one_resource(self):
        f = storage.SampleFilter(
            user='user-id',
            meter='volume.size',
        )
        results = list(self.conn.get_meter_statistics(f))[0]
        self.assertEqual((datetime.datetime(2012, 9, 25, 12, 32)
                          - datetime.datetime(2012, 9, 25, 10, 30)).seconds,
                         results.duration)
        self.assertEqual(3, results.count)
        self.assertEqual('GiB', results.unit)
        self.assertEqual(5, results.min)
        self.assertEqual(7, results.max)
        self.assertEqual(18, results.sum)
        self.assertEqual(6, results.avg)

    def test_with_no_sample(self):
        f = storage.SampleFilter(
            user='user-not-exists',
            meter='volume.size',
        )
        results = list(self.conn.get_meter_statistics(f, period=1800))
        self.assertEqual([], results)


class StatisticsGroupByTest(DBTestBase,
                            tests_db.MixinTestsWithBackendScenarios):

    def prepare_data(self):
        test_sample_data = (
            {'volume': 2, 'user': 'user-1', 'project': 'project-1',
             'resource': 'resource-1', 'timestamp': (2013, 8, 1, 16, 10),
             'metadata_flavor': 'm1.tiny', 'metadata_event': 'event-1',
             'source': 'source-2', 'metadata_instance_type': '84'},
            {'volume': 2, 'user': 'user-1', 'project': 'project-2',
             'resource': 'resource-1', 'timestamp': (2013, 8, 1, 15, 37),
             'metadata_flavor': 'm1.large', 'metadata_event': 'event-1',
             'source': 'source-2', 'metadata_instance_type': '83'},
            {'volume': 1, 'user': 'user-2', 'project': 'project-1',
             'resource': 'resource-2', 'timestamp': (2013, 8, 1, 10, 11),
             'metadata_flavor': 'm1.tiny', 'metadata_event': 'event-2',
             'source': 'source-1', 'metadata_instance_type': '82'},
            {'volume': 1, 'user': 'user-2', 'project': 'project-1',
             'resource': 'resource-2', 'timestamp': (2013, 8, 1, 10, 40),
             'metadata_flavor': 'm1.large', 'metadata_event': 'event-2',
             'source': 'source-1', 'metadata_instance_type': '82'},
            {'volume': 2, 'user': 'user-2', 'project': 'project-1',
             'resource': 'resource-1', 'timestamp': (2013, 8, 1, 14, 59),
             'metadata_flavor': 'm1.large', 'metadata_event': 'event-2',
             'source': 'source-1', 'metadata_instance_type': '84'},
            {'volume': 4, 'user': 'user-2', 'project': 'project-2',
             'resource': 'resource-2', 'timestamp': (2013, 8, 1, 17, 28),
             'metadata_flavor': 'm1.large', 'metadata_event': 'event-2',
             'source': 'source-1', 'metadata_instance_type': '82'},
            {'volume': 4, 'user': 'user-3', 'project': 'project-1',
             'resource': 'resource-3', 'timestamp': (2013, 8, 1, 11, 22),
             'metadata_flavor': 'm1.tiny', 'metadata_event': 'event-2',
             'source': 'source-3', 'metadata_instance_type': '83'},
        )

        for test_sample in test_sample_data:
            c = sample.Sample(
                'instance',
                sample.TYPE_CUMULATIVE,
                unit='s',
                volume=test_sample['volume'],
                user_id=test_sample['user'],
                project_id=test_sample['project'],
                resource_id=test_sample['resource'],
                timestamp=datetime.datetime(*test_sample['timestamp']),
                resource_metadata={'flavor': test_sample['metadata_flavor'],
                                   'event': test_sample['metadata_event'],
                                   'instance_type':
                                       test_sample['metadata_instance_type']},
                source=test_sample['source'],
            )
            msg = utils.meter_message_from_counter(
                c, self.CONF.publisher.telemetry_secret,
            )
            self.conn.record_metering_data(msg)

    def test_group_by_user(self):
        f = storage.SampleFilter(
            meter='instance',
        )
        results = list(self.conn.get_meter_statistics(f, groupby=['user_id']))
        self.assertEqual(3, len(results))
        groupby_list = [r.groupby for r in results]
        groupby_keys_set = set(x for sub_dict in groupby_list
                               for x in sub_dict.keys())
        groupby_vals_set = set(x for sub_dict in groupby_list
                               for x in sub_dict.values())
        self.assertEqual(set(['user_id']), groupby_keys_set)
        self.assertEqual(set(['user-1', 'user-2', 'user-3']), groupby_vals_set)

        for r in results:
            if r.groupby == {'user_id': 'user-1'}:
                self.assertEqual(2, r.count)
                self.assertEqual('s', r.unit)
                self.assertEqual(2, r.min)
                self.assertEqual(2, r.max)
                self.assertEqual(4, r.sum)
                self.assertEqual(2, r.avg)
            elif r.groupby == {'user_id': 'user-2'}:
                self.assertEqual(4, r.count)
                self.assertEqual('s', r.unit)
                self.assertEqual(1, r.min)
                self.assertEqual(4, r.max)
                self.assertEqual(8, r.sum)
                self.assertEqual(2, r.avg)
            elif r.groupby == {'user_id': 'user-3'}:
                self.assertEqual(1, r.count)
                self.assertEqual('s', r.unit)
                self.assertEqual(4, r.min)
                self.assertEqual(4, r.max)
                self.assertEqual(4, r.sum)
                self.assertEqual(4, r.avg)

    def test_group_by_resource(self):
        f = storage.SampleFilter(
            meter='instance',
        )
        results = list(self.conn.get_meter_statistics(f,
                                                      groupby=['resource_id']))
        self.assertEqual(3, len(results))
        groupby_list = [r.groupby for r in results]
        groupby_keys_set = set(x for sub_dict in groupby_list
                               for x in sub_dict.keys())
        groupby_vals_set = set(x for sub_dict in groupby_list
                               for x in sub_dict.values())
        self.assertEqual(set(['resource_id']), groupby_keys_set)
        self.assertEqual(set(['resource-1', 'resource-2', 'resource-3']),
                         groupby_vals_set)
        for r in results:
            if r.groupby == {'resource_id': 'resource-1'}:
                self.assertEqual(3, r.count)
                self.assertEqual('s', r.unit)
                self.assertEqual(2, r.min)
                self.assertEqual(2, r.max)
                self.assertEqual(6, r.sum)
                self.assertEqual(2, r.avg)
            elif r.groupby == {'resource_id': 'resource-2'}:
                self.assertEqual(3, r.count)
                self.assertEqual('s', r.unit)
                self.assertEqual(1, r.min)
                self.assertEqual(4, r.max)
                self.assertEqual(6, r.sum)
                self.assertEqual(2, r.avg)
            elif r.groupby == {'resource_id': 'resource-3'}:
                self.assertEqual(1, r.count)
                self.assertEqual('s', r.unit)
                self.assertEqual(4, r.min)
                self.assertEqual(4, r.max)
                self.assertEqual(4, r.sum)
                self.assertEqual(4, r.avg)

    def test_group_by_project(self):
        f = storage.SampleFilter(
            meter='instance',
        )
        results = list(self.conn.get_meter_statistics(f,
                                                      groupby=['project_id']))
        self.assertEqual(2, len(results))
        groupby_list = [r.groupby for r in results]
        groupby_keys_set = set(x for sub_dict in groupby_list
                               for x in sub_dict.keys())
        groupby_vals_set = set(x for sub_dict in groupby_list
                               for x in sub_dict.values())
        self.assertEqual(set(['project_id']), groupby_keys_set)
        self.assertEqual(set(['project-1', 'project-2']), groupby_vals_set)

        for r in results:
            if r.groupby == {'project_id': 'project-1'}:
                self.assertEqual(5, r.count)
                self.assertEqual('s', r.unit)
                self.assertEqual(1, r.min)
                self.assertEqual(4, r.max)
                self.assertEqual(10, r.sum)
                self.assertEqual(2, r.avg)
            elif r.groupby == {'project_id': 'project-2'}:
                self.assertEqual(2, r.count)
                self.assertEqual('s', r.unit)
                self.assertEqual(2, r.min)
                self.assertEqual(4, r.max)
                self.assertEqual(6, r.sum)
                self.assertEqual(3, r.avg)

    def test_group_by_source(self):
        f = storage.SampleFilter(
            meter='instance',
        )
        results = list(self.conn.get_meter_statistics(f, groupby=['source']))
        self.assertEqual(3, len(results))
        groupby_list = [r.groupby for r in results]
        groupby_keys_set = set(x for sub_dict in groupby_list
                               for x in sub_dict.keys())
        groupby_vals_set = set(x for sub_dict in groupby_list
                               for x in sub_dict.values())
        self.assertEqual(set(['source']), groupby_keys_set)
        self.assertEqual(set(['source-1', 'source-2', 'source-3']),
                         groupby_vals_set)

        for r in results:
            if r.groupby == {'source': 'source-1'}:
                self.assertEqual(4, r.count)
                self.assertEqual('s', r.unit)
                self.assertEqual(1, r.min)
                self.assertEqual(4, r.max)
                self.assertEqual(8, r.sum)
                self.assertEqual(2, r.avg)
            elif r.groupby == {'source': 'source-2'}:
                self.assertEqual(2, r.count)
                self.assertEqual('s', r.unit)
                self.assertEqual(2, r.min)
                self.assertEqual(2, r.max)
                self.assertEqual(4, r.sum)
                self.assertEqual(2, r.avg)
            elif r.groupby == {'source': 'source-3'}:
                self.assertEqual(1, r.count)
                self.assertEqual('s', r.unit)
                self.assertEqual(4, r.min)
                self.assertEqual(4, r.max)
                self.assertEqual(4, r.sum)
                self.assertEqual(4, r.avg)

    def test_group_by_unknown_field(self):
        f = storage.SampleFilter(
            meter='instance',
        )
        # NOTE(terriyu): The MongoDB get_meter_statistics() returns a list
        # whereas the SQLAlchemy get_meter_statistics() returns a generator.
        # You have to apply list() to the SQLAlchemy generator to get it to
        # throw an error. The MongoDB get_meter_statistics() will throw an
        # error before list() is called. By using lambda, we can cover both
        # MongoDB and SQLAlchemy in a single test.
        self.assertRaises(
            ceilometer.NotImplementedError,
            lambda: list(self.conn.get_meter_statistics(f, groupby=['wtf']))
        )

    def test_group_by_metadata(self):
        # This test checks grouping by a single metadata field
        # (now only resource_metadata.instance_type is available).
        f = storage.SampleFilter(
            meter='instance',
        )
        results = list(
            self.conn.get_meter_statistics(
                f, groupby=['resource_metadata.instance_type']))
        self.assertEqual(3, len(results))
        groupby_list = [r.groupby for r in results]
        groupby_keys_set = set(x for sub_dict in groupby_list
                               for x in sub_dict.keys())
        groupby_vals_set = set(x for sub_dict in groupby_list
                               for x in sub_dict.values())
        self.assertEqual(set(['resource_metadata.instance_type']),
                         groupby_keys_set)
        self.assertEqual(set(['82', '83', '84']), groupby_vals_set)

        for r in results:
            if r.groupby == {'resource_metadata.instance_type': '82'}:
                self.assertEqual(3, r.count)
                self.assertEqual('s', r.unit)
                self.assertEqual(1, r.min)
                self.assertEqual(4, r.max)
                self.assertEqual(6, r.sum)
                self.assertEqual(2, r.avg)
            elif r.groupby == {'resource_metadata.instance_type': '83'}:
                self.assertEqual(2, r.count)
                self.assertEqual('s', r.unit)
                self.assertEqual(2, r.min)
                self.assertEqual(4, r.max)
                self.assertEqual(6, r.sum)
                self.assertEqual(3, r.avg)
            elif r.groupby == {'resource_metadata.instance_type': '84'}:
                self.assertEqual(2, r.count)
                self.assertEqual('s', r.unit)
                self.assertEqual(2, r.min)
                self.assertEqual(2, r.max)
                self.assertEqual(4, r.sum)
                self.assertEqual(2, r.avg)

    def test_group_by_multiple_regular(self):
        f = storage.SampleFilter(
            meter='instance',
        )
        results = list(self.conn.get_meter_statistics(f,
                                                      groupby=['user_id',
                                                               'resource_id']))
        self.assertEqual(4, len(results))
        groupby_list = [r.groupby for r in results]
        groupby_keys_set = set(x for sub_dict in groupby_list
                               for x in sub_dict.keys())
        groupby_vals_set = set(x for sub_dict in groupby_list
                               for x in sub_dict.values())
        self.assertEqual(set(['user_id', 'resource_id']), groupby_keys_set)
        self.assertEqual(set(['user-1', 'user-2', 'user-3', 'resource-1',
                              'resource-2', 'resource-3']),
                         groupby_vals_set)

        for r in results:
            if r.groupby == {'user_id': 'user-1', 'resource_id': 'resource-1'}:
                self.assertEqual(2, r.count)
                self.assertEqual('s', r.unit)
                self.assertEqual(2, r.min)
                self.assertEqual(2, r.max)
                self.assertEqual(4, r.sum)
                self.assertEqual(2, r.avg)
            elif r.groupby == {'user_id': 'user-2',
                               'resource_id': 'resource-1'}:
                self.assertEqual(1, r.count)
                self.assertEqual('s', r.unit)
                self.assertEqual(2, r.min)
                self.assertEqual(2, r.max)
                self.assertEqual(2, r.sum)
                self.assertEqual(2, r.avg)
            elif r.groupby == {'user_id': 'user-2',
                               'resource_id': 'resource-2'}:
                self.assertEqual(3, r.count)
                self.assertEqual('s', r.unit)
                self.assertEqual(1, r.min)
                self.assertEqual(4, r.max)
                self.assertEqual(6, r.sum)
                self.assertEqual(2, r.avg)
            elif r.groupby == {'user_id': 'user-3',
                               'resource_id': 'resource-3'}:
                self.assertEqual(1, r.count)
                self.assertEqual('s', r.unit)
                self.assertEqual(4, r.min)
                self.assertEqual(4, r.max)
                self.assertEqual(4, r.sum)
                self.assertEqual(4, r.avg)
            else:
                self.assertNotEqual({'user_id': 'user-1',
                                     'resource_id': 'resource-2'},
                                    r.groupby)
                self.assertNotEqual({'user_id': 'user-1',
                                     'resource_id': 'resource-3'},
                                    r.groupby)
                self.assertNotEqual({'user_id': 'user-2',
                                     'resource_id': 'resource-3'},
                                    r.groupby)
                self.assertNotEqual({'user_id': 'user-3',
                                     'resource_id': 'resource-1'},
                                    r.groupby)
                self.assertNotEqual({'user_id': 'user-3',
                                     'resource_id': 'resource-2'},
                                    r.groupby, )

    def test_group_by_multiple_metadata(self):
        # TODO(terriyu): test_group_by_multiple_metadata needs to be
        # implemented.
        # This test should check grouping by multiple metadata fields.
        pass

    def test_group_by_multiple_regular_metadata(self):
        # This test checks grouping by a combination of regular and
        # metadata fields.
        f = storage.SampleFilter(
            meter='instance',
        )
        results = list(
            self.conn.get_meter_statistics(
                f, groupby=['user_id', 'resource_metadata.instance_type']))
        self.assertEqual(5, len(results))
        groupby_list = [r.groupby for r in results]
        groupby_keys_set = set(x for sub_dict in groupby_list
                               for x in sub_dict.keys())
        groupby_vals_set = set(x for sub_dict in groupby_list
                               for x in sub_dict.values())
        self.assertEqual(set(['user_id', 'resource_metadata.instance_type']),
                         groupby_keys_set)
        self.assertEqual(set(['user-1', 'user-2', 'user-3', '82',
                              '83', '84']),
                         groupby_vals_set)

        for r in results:
            if r.groupby == {'user_id': 'user-1',
                             'resource_metadata.instance_type': '83'}:
                self.assertEqual(1, r.count)
                self.assertEqual('s', r.unit)
                self.assertEqual(2, r.min)
                self.assertEqual(2, r.max)
                self.assertEqual(2, r.sum)
                self.assertEqual(2, r.avg)
            elif r.groupby == {'user_id': 'user-1',
                               'resource_metadata.instance_type': '84'}:
                self.assertEqual(1, r.count)
                self.assertEqual('s', r.unit)
                self.assertEqual(2, r.min)
                self.assertEqual(2, r.max)
                self.assertEqual(2, r.sum)
                self.assertEqual(2, r.avg)
            elif r.groupby == {'user_id': 'user-2',
                               'resource_metadata.instance_type': '82'}:
                self.assertEqual(3, r.count)
                self.assertEqual('s', r.unit)
                self.assertEqual(1, r.min)
                self.assertEqual(4, r.max)
                self.assertEqual(6, r.sum)
                self.assertEqual(2, r.avg)
            elif r.groupby == {'user_id': 'user-2',
                               'resource_metadata.instance_type': '84'}:
                self.assertEqual(1, r.count)
                self.assertEqual('s', r.unit)
                self.assertEqual(2, r.min)
                self.assertEqual(2, r.max)
                self.assertEqual(2, r.sum)
                self.assertEqual(2, r.avg)
            elif r.groupby == {'user_id': 'user-3',
                               'resource_metadata.instance_type': '83'}:
                self.assertEqual(1, r.count)
                self.assertEqual('s', r.unit)
                self.assertEqual(4, r.min)
                self.assertEqual(4, r.max)
                self.assertEqual(4, r.sum)
                self.assertEqual(4, r.avg)
            else:
                self.assertNotEqual({'user_id': 'user-1',
                                     'resource_metadata.instance_type': '82'},
                                    r.groupby)
                self.assertNotEqual({'user_id': 'user-2',
                                     'resource_metadata.instance_type': '83'},
                                    r.groupby)
                self.assertNotEqual({'user_id': 'user-3',
                                     'resource_metadata.instance_type': '82'},
                                    r.groupby)
                self.assertNotEqual({'user_id': 'user-3',
                                     'resource_metadata.instance_type': '84'},
                                    r.groupby)

    def test_group_by_with_query_filter(self):
        f = storage.SampleFilter(
            meter='instance',
            project='project-1',
        )
        results = list(self.conn.get_meter_statistics(
            f,
            groupby=['resource_id']))
        self.assertEqual(3, len(results))
        groupby_list = [r.groupby for r in results]
        groupby_keys_set = set(x for sub_dict in groupby_list
                               for x in sub_dict.keys())
        groupby_vals_set = set(x for sub_dict in groupby_list
                               for x in sub_dict.values())
        self.assertEqual(set(['resource_id']), groupby_keys_set)
        self.assertEqual(set(['resource-1', 'resource-2', 'resource-3']),
                         groupby_vals_set)

        for r in results:
            if r.groupby == {'resource_id': 'resource-1'}:
                self.assertEqual(2, r.count)
                self.assertEqual('s', r.unit)
                self.assertEqual(2, r.min)
                self.assertEqual(2, r.max)
                self.assertEqual(4, r.sum)
                self.assertEqual(2, r.avg)
            elif r.groupby == {'resource_id': 'resource-2'}:
                self.assertEqual(2, r.count)
                self.assertEqual('s', r.unit)
                self.assertEqual(1, r.min)
                self.assertEqual(1, r.max)
                self.assertEqual(2, r.sum)
                self.assertEqual(1, r.avg)
            elif r.groupby == {'resource_id': 'resource-3'}:
                self.assertEqual(1, r.count)
                self.assertEqual('s', r.unit)
                self.assertEqual(4, r.min)
                self.assertEqual(4, r.max)
                self.assertEqual(4, r.sum)
                self.assertEqual(4, r.avg)

    def test_group_by_metadata_with_query_filter(self):
        # This test checks grouping by a metadata field in combination
        # with a query filter.
        f = storage.SampleFilter(
            meter='instance',
            project='project-1',
        )
        results = list(self.conn.get_meter_statistics(
            f,
            groupby=['resource_metadata.instance_type']))
        self.assertEqual(3, len(results))
        groupby_list = [r.groupby for r in results]
        groupby_keys_set = set(x for sub_dict in groupby_list
                               for x in sub_dict.keys())
        groupby_vals_set = set(x for sub_dict in groupby_list
                               for x in sub_dict.values())
        self.assertEqual(set(['resource_metadata.instance_type']),
                         groupby_keys_set)
        self.assertEqual(set(['82', '83', '84']),
                         groupby_vals_set)

        for r in results:
            if r.groupby == {'resource_metadata.instance_type': '82'}:
                self.assertEqual(2, r.count)
                self.assertEqual('s', r.unit)
                self.assertEqual(1, r.min)
                self.assertEqual(1, r.max)
                self.assertEqual(2, r.sum)
                self.assertEqual(1, r.avg)
            elif r.groupby == {'resource_metadata.instance_type': '83'}:
                self.assertEqual(1, r.count)
                self.assertEqual('s', r.unit)
                self.assertEqual(4, r.min)
                self.assertEqual(4, r.max)
                self.assertEqual(4, r.sum)
                self.assertEqual(4, r.avg)
            elif r.groupby == {'resource_metadata.instance_type': '84'}:
                self.assertEqual(2, r.count)
                self.assertEqual('s', r.unit)
                self.assertEqual(2, r.min)
                self.assertEqual(2, r.max)
                self.assertEqual(4, r.sum)
                self.assertEqual(2, r.avg)

    def test_group_by_with_query_filter_multiple(self):
        f = storage.SampleFilter(
            meter='instance',
            user='user-2',
            source='source-1',
        )
        results = list(self.conn.get_meter_statistics(
            f,
            groupby=['project_id', 'resource_id']))
        self.assertEqual(3, len(results))
        groupby_list = [r.groupby for r in results]
        groupby_keys_set = set(x for sub_dict in groupby_list
                               for x in sub_dict.keys())
        groupby_vals_set = set(x for sub_dict in groupby_list
                               for x in sub_dict.values())
        self.assertEqual(set(['project_id', 'resource_id']), groupby_keys_set)
        self.assertEqual(set(['project-1', 'project-2',
                              'resource-1', 'resource-2']),
                         groupby_vals_set)

        for r in results:
            if r.groupby == {'project_id': 'project-1',
                             'resource_id': 'resource-1'}:
                self.assertEqual(1, r.count)
                self.assertEqual('s', r.unit)
                self.assertEqual(2, r.min)
                self.assertEqual(2, r.max)
                self.assertEqual(2, r.sum)
                self.assertEqual(2, r.avg)
            elif r.groupby == {'project_id': 'project-1',
                               'resource_id': 'resource-2'}:
                self.assertEqual(2, r.count)
                self.assertEqual('s', r.unit)
                self.assertEqual(1, r.min)
                self.assertEqual(1, r.max)
                self.assertEqual(2, r.sum)
                self.assertEqual(1, r.avg)
            elif r.groupby == {'project_id': 'project-2',
                               'resource_id': 'resource-2'}:
                self.assertEqual(1, r.count)
                self.assertEqual('s', r.unit)
                self.assertEqual(4, r.min)
                self.assertEqual(4, r.max)
                self.assertEqual(4, r.sum)
                self.assertEqual(4, r.avg)
            else:
                self.assertNotEqual({'project_id': 'project-2',
                                     'resource_id': 'resource-1'},
                                    r.groupby)

    def test_group_by_metadata_with_query_filter_multiple(self):
        # TODO(terriyu): test_group_by_metadata_with_query_filter_multiple
        # needs to be implemented.
        # This test should check grouping by multiple metadata fields in
        # combination with a query filter.
        pass

    def test_group_by_with_period(self):
        f = storage.SampleFilter(
            meter='instance',
        )
        results = list(self.conn.get_meter_statistics(f,
                                                      period=7200,
                                                      groupby=['project_id']))
        self.assertEqual(4, len(results))
        groupby_list = [r.groupby for r in results]
        groupby_keys_set = set(x for sub_dict in groupby_list
                               for x in sub_dict.keys())
        groupby_vals_set = set(x for sub_dict in groupby_list
                               for x in sub_dict.values())
        self.assertEqual(set(['project_id']), groupby_keys_set)
        self.assertEqual(set(['project-1', 'project-2']), groupby_vals_set)
        period_start_set = set([r.period_start for r in results])
        period_start_valid = set([datetime.datetime(2013, 8, 1, 10, 11),
                                  datetime.datetime(2013, 8, 1, 14, 11),
                                  datetime.datetime(2013, 8, 1, 16, 11)])
        self.assertEqual(period_start_valid, period_start_set)

        for r in results:
            if (r.groupby == {'project_id': 'project-1'} and
                    r.period_start == datetime.datetime(2013, 8, 1, 10, 11)):
                self.assertEqual(3, r.count)
                self.assertEqual('s', r.unit)
                self.assertEqual(1, r.min)
                self.assertEqual(4, r.max)
                self.assertEqual(6, r.sum)
                self.assertEqual(2, r.avg)
                self.assertEqual(4260, r.duration)
                self.assertEqual(datetime.datetime(2013, 8, 1, 10, 11),
                                 r.duration_start)
                self.assertEqual(datetime.datetime(2013, 8, 1, 11, 22),
                                 r.duration_end)
                self.assertEqual(7200, r.period)
                self.assertEqual(datetime.datetime(2013, 8, 1, 12, 11),
                                 r.period_end)
            elif (r.groupby == {'project_id': 'project-1'} and
                    r.period_start == datetime.datetime(2013, 8, 1, 14, 11)):
                self.assertEqual(2, r.count)
                self.assertEqual('s', r.unit)
                self.assertEqual(2, r.min)
                self.assertEqual(2, r.max)
                self.assertEqual(4, r.sum)
                self.assertEqual(2, r.avg)
                self.assertEqual(4260, r.duration)
                self.assertEqual(datetime.datetime(2013, 8, 1, 14, 59),
                                 r.duration_start)
                self.assertEqual(datetime.datetime(2013, 8, 1, 16, 10),
                                 r.duration_end)
                self.assertEqual(7200, r.period)
                self.assertEqual(datetime.datetime(2013, 8, 1, 16, 11),
                                 r.period_end)
            elif (r.groupby == {'project_id': 'project-2'} and
                    r.period_start == datetime.datetime(2013, 8, 1, 14, 11)):
                self.assertEqual(1, r.count)
                self.assertEqual('s', r.unit)
                self.assertEqual(2, r.min)
                self.assertEqual(2, r.max)
                self.assertEqual(2, r.sum)
                self.assertEqual(2, r.avg)
                self.assertEqual(0, r.duration)
                self.assertEqual(datetime.datetime(2013, 8, 1, 15, 37),
                                 r.duration_start)
                self.assertEqual(datetime.datetime(2013, 8, 1, 15, 37),
                                 r.duration_end)
                self.assertEqual(7200, r.period)
                self.assertEqual(datetime.datetime(2013, 8, 1, 16, 11),
                                 r.period_end)
            elif (r.groupby == {'project_id': 'project-2'} and
                    r.period_start == datetime.datetime(2013, 8, 1, 16, 11)):
                self.assertEqual(1, r.count)
                self.assertEqual('s', r.unit)
                self.assertEqual(4, r.min)
                self.assertEqual(4, r.max)
                self.assertEqual(4, r.sum)
                self.assertEqual(4, r.avg)
                self.assertEqual(0, r.duration)
                self.assertEqual(datetime.datetime(2013, 8, 1, 17, 28),
                                 r.duration_start)
                self.assertEqual(datetime.datetime(2013, 8, 1, 17, 28),
                                 r.duration_end)
                self.assertEqual(7200, r.period)
                self.assertEqual(datetime.datetime(2013, 8, 1, 18, 11),
                                 r.period_end)
            else:
                self.assertNotEqual([{'project_id': 'project-1'},
                                     datetime.datetime(2013, 8, 1, 16, 11)],
                                    [r.groupby, r.period_start])
                self.assertNotEqual([{'project_id': 'project-2'},
                                     datetime.datetime(2013, 8, 1, 10, 11)],
                                    [r.groupby, r.period_start])

    def test_group_by_metadata_with_period(self):
        # This test checks grouping by metadata fields in combination
        # with period grouping.
        f = storage.SampleFilter(
            meter='instance')

        results = list(self.conn.get_meter_statistics(f, period=7200,
                       groupby=['resource_metadata.instance_type']))
        self.assertEqual(5, len(results))
        groupby_list = [r.groupby for r in results]
        groupby_keys_set = set(x for sub_dict in groupby_list
                               for x in sub_dict.keys())
        groupby_vals_set = set(x for sub_dict in groupby_list
                               for x in sub_dict.values())
        self.assertEqual(set(['resource_metadata.instance_type']),
                         groupby_keys_set)
        self.assertEqual(set(['82', '83', '84']), groupby_vals_set)
        period_start_set = set([r.period_start for r in results])
        period_start_valid = set([datetime.datetime(2013, 8, 1, 10, 11),
                                  datetime.datetime(2013, 8, 1, 14, 11),
                                  datetime.datetime(2013, 8, 1, 16, 11)])
        self.assertEqual(period_start_valid, period_start_set)

        for r in results:
            if (r.groupby == {'resource_metadata.instance_type': '82'} and
                    r.period_start == datetime.datetime(2013, 8, 1, 10, 11)):
                self.assertEqual(2, r.count)
                self.assertEqual('s', r.unit)
                self.assertEqual(1, r.min)
                self.assertEqual(1, r.max)
                self.assertEqual(2, r.sum)
                self.assertEqual(1, r.avg)
                self.assertEqual(1740, r.duration)
                self.assertEqual(datetime.datetime(2013, 8, 1, 10, 11),
                                 r.duration_start)
                self.assertEqual(datetime.datetime(2013, 8, 1, 10, 40),
                                 r.duration_end)
                self.assertEqual(7200, r.period)
                self.assertEqual(datetime.datetime(2013, 8, 1, 12, 11),
                                 r.period_end)
            elif (r.groupby == {'resource_metadata.instance_type': '82'} and
                  r.period_start == datetime.datetime(2013, 8, 1, 16, 11)):
                self.assertEqual(1, r.count)
                self.assertEqual('s', r.unit)
                self.assertEqual(4, r.min)
                self.assertEqual(4, r.max)
                self.assertEqual(4, r.sum)
                self.assertEqual(4, r.avg)
                self.assertEqual(0, r.duration)
                self.assertEqual(datetime.datetime(2013, 8, 1, 17, 28),
                                 r.duration_start)
                self.assertEqual(datetime.datetime(2013, 8, 1, 17, 28),
                                 r.duration_end)
                self.assertEqual(7200, r.period)
                self.assertEqual(datetime.datetime(2013, 8, 1, 18, 11),
                                 r.period_end)
            elif (r.groupby == {'resource_metadata.instance_type': '83'} and
                  r.period_start == datetime.datetime(2013, 8, 1, 10, 11)):
                self.assertEqual(1, r.count)
                self.assertEqual('s', r.unit)
                self.assertEqual(4, r.min)
                self.assertEqual(4, r.max)
                self.assertEqual(4, r.sum)
                self.assertEqual(4, r.avg)
                self.assertEqual(0, r.duration)
                self.assertEqual(datetime.datetime(2013, 8, 1, 11, 22),
                                 r.duration_start)
                self.assertEqual(datetime.datetime(2013, 8, 1, 11, 22),
                                 r.duration_end)
                self.assertEqual(7200, r.period)
                self.assertEqual(datetime.datetime(2013, 8, 1, 12, 11),
                                 r.period_end)
            elif (r.groupby == {'resource_metadata.instance_type': '83'} and
                  r.period_start == datetime.datetime(2013, 8, 1, 14, 11)):
                self.assertEqual(1, r.count)
                self.assertEqual('s', r.unit)
                self.assertEqual(2, r.min)
                self.assertEqual(2, r.max)
                self.assertEqual(2, r.sum)
                self.assertEqual(2, r.avg)
                self.assertEqual(0, r.duration)
                self.assertEqual(datetime.datetime(2013, 8, 1, 15, 37),
                                 r.duration_start)
                self.assertEqual(datetime.datetime(2013, 8, 1, 15, 37),
                                 r.duration_end)
                self.assertEqual(7200, r.period)
                self.assertEqual(datetime.datetime(2013, 8, 1, 16, 11),
                                 r.period_end)
            elif (r.groupby == {'resource_metadata.instance_type': '84'} and
                  r.period_start == datetime.datetime(2013, 8, 1, 14, 11)):
                self.assertEqual(2, r.count)
                self.assertEqual('s', r.unit)
                self.assertEqual(2, r.min)
                self.assertEqual(2, r.max)
                self.assertEqual(4, r.sum)
                self.assertEqual(2, r.avg)
                self.assertEqual(4260, r.duration)
                self.assertEqual(datetime.datetime(2013, 8, 1, 14, 59),
                                 r.duration_start)
                self.assertEqual(datetime.datetime(2013, 8, 1, 16, 10),
                                 r.duration_end)
                self.assertEqual(7200, r.period)
                self.assertEqual(datetime.datetime(2013, 8, 1, 16, 11),
                                 r.period_end)
            else:
                self.assertNotEqual([{'resource_metadata.instance_type': '82'},
                                     datetime.datetime(2013, 8, 1, 14, 11)],
                                    [r.groupby, r.period_start])
                self.assertNotEqual([{'resource_metadata.instance_type': '83'},
                                     datetime.datetime(2013, 8, 1, 16, 11)],
                                    [r.groupby, r.period_start])
                self.assertNotEqual([{'resource_metadata.instance_type': '84'},
                                     datetime.datetime(2013, 8, 1, 10, 11)],
                                    [r.groupby, r.period_start])
                self.assertNotEqual([{'resource_metadata.instance_type': '84'},
                                     datetime.datetime(2013, 8, 1, 16, 11)],
                                    [r.groupby, r.period_start])

    def test_group_by_with_query_filter_and_period(self):
        f = storage.SampleFilter(
            meter='instance',
            source='source-1',
        )
        results = list(self.conn.get_meter_statistics(f,
                                                      period=7200,
                                                      groupby=['project_id']))
        self.assertEqual(3, len(results))
        groupby_list = [r.groupby for r in results]
        groupby_keys_set = set(x for sub_dict in groupby_list
                               for x in sub_dict.keys())
        groupby_vals_set = set(x for sub_dict in groupby_list
                               for x in sub_dict.values())
        self.assertEqual(set(['project_id']), groupby_keys_set)
        self.assertEqual(set(['project-1', 'project-2']), groupby_vals_set)
        period_start_set = set([r.period_start for r in results])
        period_start_valid = set([datetime.datetime(2013, 8, 1, 10, 11),
                                  datetime.datetime(2013, 8, 1, 14, 11),
                                  datetime.datetime(2013, 8, 1, 16, 11)])
        self.assertEqual(period_start_valid, period_start_set)

        for r in results:
            if (r.groupby == {'project_id': 'project-1'} and
                    r.period_start == datetime.datetime(2013, 8, 1, 10, 11)):
                self.assertEqual(2, r.count)
                self.assertEqual('s', r.unit)
                self.assertEqual(1, r.min)
                self.assertEqual(1, r.max)
                self.assertEqual(2, r.sum)
                self.assertEqual(1, r.avg)
                self.assertEqual(1740, r.duration)
                self.assertEqual(datetime.datetime(2013, 8, 1, 10, 11),
                                 r.duration_start)
                self.assertEqual(datetime.datetime(2013, 8, 1, 10, 40),
                                 r.duration_end)
                self.assertEqual(7200, r.period)
                self.assertEqual(datetime.datetime(2013, 8, 1, 12, 11),
                                 r.period_end)
            elif (r.groupby == {'project_id': 'project-1'} and
                    r.period_start == datetime.datetime(2013, 8, 1, 14, 11)):
                self.assertEqual(1, r.count)
                self.assertEqual('s', r.unit)
                self.assertEqual(2, r.min)
                self.assertEqual(2, r.max)
                self.assertEqual(2, r.sum)
                self.assertEqual(2, r.avg)
                self.assertEqual(0, r.duration)
                self.assertEqual(datetime.datetime(2013, 8, 1, 14, 59),
                                 r.duration_start)
                self.assertEqual(datetime.datetime(2013, 8, 1, 14, 59),
                                 r.duration_end)
                self.assertEqual(7200, r.period)
                self.assertEqual(datetime.datetime(2013, 8, 1, 16, 11),
                                 r.period_end)
            elif (r.groupby == {'project_id': 'project-2'} and
                    r.period_start == datetime.datetime(2013, 8, 1, 16, 11)):
                self.assertEqual(1, r.count)
                self.assertEqual('s', r.unit)
                self.assertEqual(4, r.min)
                self.assertEqual(4, r.max)
                self.assertEqual(4, r.sum)
                self.assertEqual(4, r.avg)
                self.assertEqual(0, r.duration)
                self.assertEqual(datetime.datetime(2013, 8, 1, 17, 28),
                                 r.duration_start)
                self.assertEqual(datetime.datetime(2013, 8, 1, 17, 28),
                                 r.duration_end)
                self.assertEqual(7200, r.period)
                self.assertEqual(datetime.datetime(2013, 8, 1, 18, 11),
                                 r.period_end)
            else:
                self.assertNotEqual([{'project_id': 'project-1'},
                                     datetime.datetime(2013, 8, 1, 16, 11)],
                                    [r.groupby, r.period_start])
                self.assertNotEqual([{'project_id': 'project-2'},
                                     datetime.datetime(2013, 8, 1, 10, 11)],
                                    [r.groupby, r.period_start])

    def test_group_by_metadata_with_query_filter_and_period(self):
        # This test checks grouping with metadata fields in combination
        # with a query filter and period grouping.
        f = storage.SampleFilter(
            meter='instance',
            project='project-1',
        )
        results = list(
            self.conn.get_meter_statistics(
                f, period=7200, groupby=['resource_metadata.instance_type']))
        self.assertEqual(3, len(results))
        groupby_list = [r.groupby for r in results]
        groupby_keys_set = set(x for sub_dict in groupby_list
                               for x in sub_dict.keys())
        groupby_vals_set = set(x for sub_dict in groupby_list
                               for x in sub_dict.values())
        self.assertEqual(set(['resource_metadata.instance_type']),
                         groupby_keys_set)
        self.assertEqual(set(['82', '83', '84']), groupby_vals_set)
        period_start_set = set([r.period_start for r in results])
        period_start_valid = set([datetime.datetime(2013, 8, 1, 10, 11),
                                  datetime.datetime(2013, 8, 1, 14, 11)])
        self.assertEqual(period_start_valid, period_start_set)

        for r in results:
            if (r.groupby == {'resource_metadata.instance_type': '82'} and
                    r.period_start == datetime.datetime(2013, 8, 1, 10, 11)):
                self.assertEqual(2, r.count)
                self.assertEqual('s', r.unit)
                self.assertEqual(1, r.min)
                self.assertEqual(1, r.max)
                self.assertEqual(2, r.sum)
                self.assertEqual(1, r.avg)
                self.assertEqual(1740, r.duration)
                self.assertEqual(datetime.datetime(2013, 8, 1, 10, 11),
                                 r.duration_start)
                self.assertEqual(datetime.datetime(2013, 8, 1, 10, 40),
                                 r.duration_end)
                self.assertEqual(7200, r.period)
                self.assertEqual(datetime.datetime(2013, 8, 1, 12, 11),
                                 r.period_end)
            elif (r.groupby == {'resource_metadata.instance_type': '83'} and
                  r.period_start == datetime.datetime(2013, 8, 1, 10, 11)):
                self.assertEqual(1, r.count)
                self.assertEqual('s', r.unit)
                self.assertEqual(4, r.min)
                self.assertEqual(4, r.max)
                self.assertEqual(4, r.sum)
                self.assertEqual(4, r.avg)
                self.assertEqual(0, r.duration)
                self.assertEqual(datetime.datetime(2013, 8, 1, 11, 22),
                                 r.duration_start)
                self.assertEqual(datetime.datetime(2013, 8, 1, 11, 22),
                                 r.duration_end)
                self.assertEqual(7200, r.period)
                self.assertEqual(datetime.datetime(2013, 8, 1, 12, 11),
                                 r.period_end)
            elif (r.groupby == {'resource_metadata.instance_type': '84'} and
                  r.period_start == datetime.datetime(2013, 8, 1, 14, 11)):
                self.assertEqual(2, r.count)
                self.assertEqual('s', r.unit)
                self.assertEqual(2, r.min)
                self.assertEqual(2, r.max)
                self.assertEqual(4, r.sum)
                self.assertEqual(2, r.avg)
                self.assertEqual(4260, r.duration)
                self.assertEqual(datetime.datetime(2013, 8, 1, 14, 59),
                                 r.duration_start)
                self.assertEqual(datetime.datetime(2013, 8, 1, 16, 10),
                                 r.duration_end)
                self.assertEqual(7200, r.period)
                self.assertEqual(datetime.datetime(2013, 8, 1, 16, 11),
                                 r.period_end)
            else:
                self.assertNotEqual([{'resource_metadata.instance_type': '82'},
                                     datetime.datetime(2013, 8, 1, 14, 11)],
                                    [r.groupby, r.period_start])
                self.assertNotEqual([{'resource_metadata.instance_type': '83'},
                                     datetime.datetime(2013, 8, 1, 14, 11)],
                                    [r.groupby, r.period_start])
                self.assertNotEqual([{'resource_metadata.instance_type': '84'},
                                     datetime.datetime(2013, 8, 1, 10, 11)],
                                    [r.groupby, r.period_start])

    def test_group_by_start_timestamp_after(self):
        f = storage.SampleFilter(
            meter='instance',
            start_timestamp=datetime.datetime(2013, 8, 1, 17, 28, 1),
        )
        results = list(self.conn.get_meter_statistics(f,
                                                      groupby=['project_id']))

        self.assertEqual([], results)

    def test_group_by_end_timestamp_before(self):
        f = storage.SampleFilter(
            meter='instance',
            end_timestamp=datetime.datetime(2013, 8, 1, 10, 10, 59),
        )
        results = list(self.conn.get_meter_statistics(f,
                                                      groupby=['project_id']))

        self.assertEqual([], results)

    def test_group_by_start_timestamp(self):
        f = storage.SampleFilter(
            meter='instance',
            start_timestamp=datetime.datetime(2013, 8, 1, 14, 58),
        )
        results = list(self.conn.get_meter_statistics(f,
                                                      groupby=['project_id']))
        self.assertEqual(2, len(results))
        groupby_list = [r.groupby for r in results]
        groupby_keys_set = set(x for sub_dict in groupby_list
                               for x in sub_dict.keys())
        groupby_vals_set = set(x for sub_dict in groupby_list
                               for x in sub_dict.values())
        self.assertEqual(set(['project_id']), groupby_keys_set)
        self.assertEqual(set(['project-1', 'project-2']), groupby_vals_set)

        for r in results:
            if r.groupby == {'project_id': 'project-1'}:
                self.assertEqual(2, r.count)
                self.assertEqual('s', r.unit)
                self.assertEqual(2, r.min)
                self.assertEqual(2, r.max)
                self.assertEqual(4, r.sum)
                self.assertEqual(2, r.avg)
            elif r.groupby == {'project_id': 'project-2'}:
                self.assertEqual(2, r.count)
                self.assertEqual('s', r.unit)
                self.assertEqual(2, r.min)
                self.assertEqual(4, r.max)
                self.assertEqual(6, r.sum)
                self.assertEqual(3, r.avg)

    def test_group_by_end_timestamp(self):
        f = storage.SampleFilter(
            meter='instance',
            end_timestamp=datetime.datetime(2013, 8, 1, 11, 45),
        )
        results = list(self.conn.get_meter_statistics(f,
                                                      groupby=['project_id']))
        self.assertEqual(1, len(results))
        groupby_list = [r.groupby for r in results]
        groupby_keys_set = set(x for sub_dict in groupby_list
                               for x in sub_dict.keys())
        groupby_vals_set = set(x for sub_dict in groupby_list
                               for x in sub_dict.values())
        self.assertEqual(set(['project_id']), groupby_keys_set)
        self.assertEqual(set(['project-1']), groupby_vals_set)

        for r in results:
            if r.groupby == {'project_id': 'project-1'}:
                self.assertEqual(3, r.count)
                self.assertEqual('s', r.unit)
                self.assertEqual(1, r.min)
                self.assertEqual(4, r.max)
                self.assertEqual(6, r.sum)
                self.assertEqual(2, r.avg)

    def test_group_by_start_end_timestamp(self):
        f = storage.SampleFilter(
            meter='instance',
            start_timestamp=datetime.datetime(2013, 8, 1, 8, 17, 3),
            end_timestamp=datetime.datetime(2013, 8, 1, 23, 59, 59),
        )
        results = list(self.conn.get_meter_statistics(f,
                                                      groupby=['project_id']))
        self.assertEqual(2, len(results))
        groupby_list = [r.groupby for r in results]
        groupby_keys_set = set(x for sub_dict in groupby_list
                               for x in sub_dict.keys())
        groupby_vals_set = set(x for sub_dict in groupby_list
                               for x in sub_dict.values())
        self.assertEqual(set(['project_id']), groupby_keys_set)
        self.assertEqual(set(['project-1', 'project-2']), groupby_vals_set)

        for r in results:
            if r.groupby == {'project_id': 'project-1'}:
                self.assertEqual(5, r.count)
                self.assertEqual('s', r.unit)
                self.assertEqual(1, r.min)
                self.assertEqual(4, r.max)
                self.assertEqual(10, r.sum)
                self.assertEqual(2, r.avg)
            elif r.groupby == {'project_id': 'project-2'}:
                self.assertEqual(2, r.count)
                self.assertEqual('s', r.unit)
                self.assertEqual(2, r.min)
                self.assertEqual(4, r.max)
                self.assertEqual(6, r.sum)
                self.assertEqual(3, r.avg)

    def test_group_by_start_end_timestamp_with_query_filter(self):
        f = storage.SampleFilter(
            meter='instance',
            project='project-1',
            start_timestamp=datetime.datetime(2013, 8, 1, 11, 1),
            end_timestamp=datetime.datetime(2013, 8, 1, 20, 0),
        )
        results = list(self.conn.get_meter_statistics(f,
                                                      groupby=['resource_id']))
        groupby_list = [r.groupby for r in results]
        groupby_keys_set = set(x for sub_dict in groupby_list
                               for x in sub_dict.keys())
        groupby_vals_set = set(x for sub_dict in groupby_list
                               for x in sub_dict.values())
        self.assertEqual(set(['resource_id']), groupby_keys_set)
        self.assertEqual(set(['resource-1', 'resource-3']), groupby_vals_set)

        for r in results:
            if r.groupby == {'resource_id': 'resource-1'}:
                self.assertEqual(2, r.count)
                self.assertEqual('s', r.unit)
                self.assertEqual(2, r.min)
                self.assertEqual(2, r.max)
                self.assertEqual(4, r.sum)
                self.assertEqual(2, r.avg)
            elif r.groupby == {'resource_id': 'resource-3'}:
                self.assertEqual(1, r.count)
                self.assertEqual('s', r.unit)
                self.assertEqual(4, r.min)
                self.assertEqual(4, r.max)
                self.assertEqual(4, r.sum)
                self.assertEqual(4, r.avg)

    def test_group_by_start_end_timestamp_with_period(self):
        f = storage.SampleFilter(
            meter='instance',
            start_timestamp=datetime.datetime(2013, 8, 1, 14, 0),
            end_timestamp=datetime.datetime(2013, 8, 1, 17, 0),
        )
        results = list(self.conn.get_meter_statistics(f,
                                                      period=3600,
                                                      groupby=['project_id']))
        self.assertEqual(3, len(results))
        groupby_list = [r.groupby for r in results]
        groupby_keys_set = set(x for sub_dict in groupby_list
                               for x in sub_dict.keys())
        groupby_vals_set = set(x for sub_dict in groupby_list
                               for x in sub_dict.values())
        self.assertEqual(set(['project_id']), groupby_keys_set)
        self.assertEqual(set(['project-1', 'project-2']), groupby_vals_set)
        period_start_set = set([r.period_start for r in results])
        period_start_valid = set([datetime.datetime(2013, 8, 1, 14, 0),
                                  datetime.datetime(2013, 8, 1, 15, 0),
                                  datetime.datetime(2013, 8, 1, 16, 0)])
        self.assertEqual(period_start_valid, period_start_set)

        for r in results:
            if (r.groupby == {'project_id': 'project-1'} and
                    r.period_start == datetime.datetime(2013, 8, 1, 14, 0)):
                self.assertEqual(1, r.count)
                self.assertEqual('s', r.unit)
                self.assertEqual(2, r.min)
                self.assertEqual(2, r.max)
                self.assertEqual(2, r.sum)
                self.assertEqual(2, r.avg)
                self.assertEqual(0, r.duration)
                self.assertEqual(datetime.datetime(2013, 8, 1, 14, 59),
                                 r.duration_start)
                self.assertEqual(datetime.datetime(2013, 8, 1, 14, 59),
                                 r.duration_end)
                self.assertEqual(3600, r.period)
                self.assertEqual(datetime.datetime(2013, 8, 1, 15, 0),
                                 r.period_end)
            elif (r.groupby == {'project_id': 'project-1'} and
                    r.period_start == datetime.datetime(2013, 8, 1, 16, 0)):
                self.assertEqual(1, r.count)
                self.assertEqual('s', r.unit)
                self.assertEqual(2, r.min)
                self.assertEqual(2, r.max)
                self.assertEqual(2, r.sum)
                self.assertEqual(2, r.avg)
                self.assertEqual(0, r.duration)
                self.assertEqual(datetime.datetime(2013, 8, 1, 16, 10),
                                 r.duration_start)
                self.assertEqual(datetime.datetime(2013, 8, 1, 16, 10),
                                 r.duration_end)
                self.assertEqual(3600, r.period)
                self.assertEqual(datetime.datetime(2013, 8, 1, 17, 0),
                                 r.period_end)
            elif (r.groupby == {'project_id': 'project-2'} and
                    r.period_start == datetime.datetime(2013, 8, 1, 15, 0)):
                self.assertEqual(1, r.count)
                self.assertEqual('s', r.unit)
                self.assertEqual(2, r.min)
                self.assertEqual(2, r.max)
                self.assertEqual(2, r.sum)
                self.assertEqual(2, r.avg)
                self.assertEqual(0, r.duration)
                self.assertEqual(datetime.datetime(2013, 8, 1, 15, 37),
                                 r.duration_start)
                self.assertEqual(datetime.datetime(2013, 8, 1, 15, 37),
                                 r.duration_end)
                self.assertEqual(3600, r.period)
                self.assertEqual(datetime.datetime(2013, 8, 1, 16, 0),
                                 r.period_end)
            else:
                self.assertNotEqual([{'project_id': 'project-1'},
                                     datetime.datetime(2013, 8, 1, 15, 0)],
                                    [r.groupby, r.period_start])
                self.assertNotEqual([{'project_id': 'project-2'},
                                     datetime.datetime(2013, 8, 1, 14, 0)],
                                    [r.groupby, r.period_start])
                self.assertNotEqual([{'project_id': 'project-2'},
                                     datetime.datetime(2013, 8, 1, 16, 0)],
                                    [r.groupby, r.period_start])

    def test_group_by_start_end_timestamp_with_query_filter_and_period(self):
        f = storage.SampleFilter(
            meter='instance',
            source='source-1',
            start_timestamp=datetime.datetime(2013, 8, 1, 10, 0),
            end_timestamp=datetime.datetime(2013, 8, 1, 18, 0),
        )
        results = list(self.conn.get_meter_statistics(f,
                                                      period=7200,
                                                      groupby=['project_id']))
        self.assertEqual(3, len(results))
        groupby_list = [r.groupby for r in results]
        groupby_keys_set = set(x for sub_dict in groupby_list
                               for x in sub_dict.keys())
        groupby_vals_set = set(x for sub_dict in groupby_list
                               for x in sub_dict.values())
        self.assertEqual(set(['project_id']), groupby_keys_set)
        self.assertEqual(set(['project-1', 'project-2']), groupby_vals_set)
        period_start_set = set([r.period_start for r in results])
        period_start_valid = set([datetime.datetime(2013, 8, 1, 10, 0),
                                  datetime.datetime(2013, 8, 1, 14, 0),
                                  datetime.datetime(2013, 8, 1, 16, 0)])
        self.assertEqual(period_start_valid, period_start_set)

        for r in results:
            if (r.groupby == {'project_id': 'project-1'} and
                    r.period_start == datetime.datetime(2013, 8, 1, 10, 0)):
                self.assertEqual(2, r.count)
                self.assertEqual('s', r.unit)
                self.assertEqual(1, r.min)
                self.assertEqual(1, r.max)
                self.assertEqual(2, r.sum)
                self.assertEqual(1, r.avg)
                self.assertEqual(1740, r.duration)
                self.assertEqual(datetime.datetime(2013, 8, 1, 10, 11),
                                 r.duration_start)
                self.assertEqual(datetime.datetime(2013, 8, 1, 10, 40),
                                 r.duration_end)
                self.assertEqual(7200, r.period)
                self.assertEqual(datetime.datetime(2013, 8, 1, 12, 0),
                                 r.period_end)
            elif (r.groupby == {'project_id': 'project-1'} and
                    r.period_start == datetime.datetime(2013, 8, 1, 14, 0)):
                self.assertEqual(1, r.count)
                self.assertEqual('s', r.unit)
                self.assertEqual(2, r.min)
                self.assertEqual(2, r.max)
                self.assertEqual(2, r.sum)
                self.assertEqual(2, r.avg)
                self.assertEqual(0, r.duration)
                self.assertEqual(datetime.datetime(2013, 8, 1, 14, 59),
                                 r.duration_start)
                self.assertEqual(datetime.datetime(2013, 8, 1, 14, 59),
                                 r.duration_end)
                self.assertEqual(7200, r.period)
                self.assertEqual(datetime.datetime(2013, 8, 1, 16, 0),
                                 r.period_end)
            elif (r.groupby == {'project_id': 'project-2'} and
                    r.period_start == datetime.datetime(2013, 8, 1, 16, 0)):
                self.assertEqual(1, r.count)
                self.assertEqual('s', r.unit)
                self.assertEqual(4, r.min)
                self.assertEqual(4, r.max)
                self.assertEqual(4, r.sum)
                self.assertEqual(4, r.avg)
                self.assertEqual(0, r.duration)
                self.assertEqual(datetime.datetime(2013, 8, 1, 17, 28),
                                 r.duration_start)
                self.assertEqual(datetime.datetime(2013, 8, 1, 17, 28),
                                 r.duration_end)
                self.assertEqual(7200, r.period)
                self.assertEqual(datetime.datetime(2013, 8, 1, 18, 0),
                                 r.period_end)
            else:
                self.assertNotEqual([{'project_id': 'project-1'},
                                     datetime.datetime(2013, 8, 1, 16, 0)],
                                    [r.groupby, r.period_start])
                self.assertNotEqual([{'project_id': 'project-2'},
                                     datetime.datetime(2013, 8, 1, 10, 0)],
                                    [r.groupby, r.period_start])
                self.assertNotEqual([{'project_id': 'project-2'},
                                     datetime.datetime(2013, 8, 1, 14, 0)],
                                    [r.groupby, r.period_start])


class CounterDataTypeTest(DBTestBase,
                          tests_db.MixinTestsWithBackendScenarios):
    def prepare_data(self):
        c = sample.Sample(
            'dummyBigCounter',
            sample.TYPE_CUMULATIVE,
            unit='',
            volume=337203685477580,
            user_id='user-id',
            project_id='project-id',
            resource_id='resource-id',
            timestamp=datetime.datetime(2012, 7, 2, 10, 40),
            resource_metadata={},
            source='test-1',
        )
        msg = utils.meter_message_from_counter(
            c, self.CONF.publisher.telemetry_secret,
        )

        self.conn.record_metering_data(msg)

        c = sample.Sample(
            'dummySmallCounter',
            sample.TYPE_CUMULATIVE,
            unit='',
            volume=-337203685477580,
            user_id='user-id',
            project_id='project-id',
            resource_id='resource-id',
            timestamp=datetime.datetime(2012, 7, 2, 10, 40),
            resource_metadata={},
            source='test-1',
        )
        msg = utils.meter_message_from_counter(
            c, self.CONF.publisher.telemetry_secret,
        )
        self.conn.record_metering_data(msg)

        c = sample.Sample(
            'floatCounter',
            sample.TYPE_CUMULATIVE,
            unit='',
            volume=1938495037.53697,
            user_id='user-id',
            project_id='project-id',
            resource_id='resource-id',
            timestamp=datetime.datetime(2012, 7, 2, 10, 40),
            resource_metadata={},
            source='test-1',
        )
        msg = utils.meter_message_from_counter(
            c, self.CONF.publisher.telemetry_secret,
        )
        self.conn.record_metering_data(msg)

    def test_storage_can_handle_large_values(self):
        f = storage.SampleFilter(
            meter='dummyBigCounter',
        )
        results = list(self.conn.get_samples(f))
        self.assertEqual(337203685477580, results[0].counter_volume)
        f = storage.SampleFilter(
            meter='dummySmallCounter',
        )
        results = list(self.conn.get_samples(f))
        observed_num = int(results[0].counter_volume)
        self.assertEqual(-337203685477580, observed_num)

    def test_storage_can_handle_float_values(self):
        f = storage.SampleFilter(
            meter='floatCounter',
        )
        results = list(self.conn.get_samples(f))
        self.assertEqual(1938495037.53697, results[0].counter_volume)


class AlarmTestBase(DBTestBase):
    def add_some_alarms(self):
        alarms = [alarm_models.Alarm(alarm_id='r3d',
                                     enabled=True,
                                     type='threshold',
                                     name='red-alert',
                                     description='my red-alert',
                                     timestamp=datetime.datetime(2015, 7,
                                                                 2, 10, 25),
                                     user_id='me',
                                     project_id='and-da-boys',
                                     state="insufficient data",
                                     state_timestamp=constants.MIN_DATETIME,
                                     ok_actions=[],
                                     alarm_actions=['http://nowhere/alarms'],
                                     insufficient_data_actions=[],
                                     repeat_actions=False,
                                     time_constraints=[dict(name='testcons',
                                                            start='0 11 * * *',
                                                            duration=300)],
                                     rule=dict(comparison_operator='eq',
                                               threshold=36,
                                               statistic='count',
                                               evaluation_periods=1,
                                               period=60,
                                               meter_name='test.one',
                                               query=[{'field': 'key',
                                                       'op': 'eq',
                                                       'value': 'value',
                                                       'type': 'string'}]),
                                     ),
                  alarm_models.Alarm(alarm_id='0r4ng3',
                                     enabled=True,
                                     type='threshold',
                                     name='orange-alert',
                                     description='a orange',
                                     timestamp=datetime.datetime(2015, 7,
                                                                 2, 10, 40),
                                     user_id='me',
                                     project_id='and-da-boys',
                                     state="insufficient data",
                                     state_timestamp=constants.MIN_DATETIME,
                                     ok_actions=[],
                                     alarm_actions=['http://nowhere/alarms'],
                                     insufficient_data_actions=[],
                                     repeat_actions=False,
                                     time_constraints=[],
                                     rule=dict(comparison_operator='gt',
                                               threshold=75,
                                               statistic='avg',
                                               evaluation_periods=1,
                                               period=60,
                                               meter_name='test.forty',
                                               query=[{'field': 'key2',
                                                       'op': 'eq',
                                                       'value': 'value2',
                                                       'type': 'string'}]),
                                     ),
                  alarm_models.Alarm(alarm_id='y3ll0w',
                                     enabled=False,
                                     type='threshold',
                                     name='yellow-alert',
                                     description='yellow',
                                     timestamp=datetime.datetime(2015, 7,
                                                                 2, 10, 10),
                                     user_id='me',
                                     project_id='and-da-boys',
                                     state="insufficient data",
                                     state_timestamp=constants.MIN_DATETIME,
                                     ok_actions=[],
                                     alarm_actions=['http://nowhere/alarms'],
                                     insufficient_data_actions=[],
                                     repeat_actions=False,
                                     time_constraints=[],
                                     rule=dict(comparison_operator='lt',
                                               threshold=10,
                                               statistic='min',
                                               evaluation_periods=1,
                                               period=60,
                                               meter_name='test.five',
                                               query=[{'field': 'key2',
                                                       'op': 'eq',
                                                       'value': 'value2',
                                                       'type': 'string'},
                                                      {'field':
                                                       'user_metadata.key3',
                                                       'op': 'eq',
                                                       'value': 'value3',
                                                       'type': 'string'}]),
                                     )]

        for a in alarms:
            self.alarm_conn.create_alarm(a)


class AlarmTest(AlarmTestBase,
                tests_db.MixinTestsWithBackendScenarios):

    def test_empty(self):
        alarms = list(self.alarm_conn.get_alarms())
        self.assertEqual([], alarms)

    def test_list(self):
        self.add_some_alarms()
        alarms = list(self.alarm_conn.get_alarms())
        self.assertEqual(3, len(alarms))

    def test_list_ordered_by_timestamp(self):
        self.add_some_alarms()
        alarms = list(self.alarm_conn.get_alarms())
        self.assertEqual(len(alarms), 3)
        alarm_l = [a.timestamp for a in alarms]
        alarm_l_ordered = [datetime.datetime(2015, 7, 2, 10, 40),
                           datetime.datetime(2015, 7, 2, 10, 25),
                           datetime.datetime(2015, 7, 2, 10, 10)]
        self.assertEqual(alarm_l_ordered, alarm_l)

    def test_list_enabled(self):
        self.add_some_alarms()
        alarms = list(self.alarm_conn.get_alarms(enabled=True))
        self.assertEqual(2, len(alarms))

    def test_list_disabled(self):
        self.add_some_alarms()
        alarms = list(self.alarm_conn.get_alarms(enabled=False))
        self.assertEqual(1, len(alarms))

    def test_list_by_type(self):
        self.add_some_alarms()
        alarms = list(self.alarm_conn.get_alarms(alarm_type='threshold'))
        self.assertEqual(3, len(alarms))
        alarms = list(self.alarm_conn.get_alarms(alarm_type='combination'))
        self.assertEqual(0, len(alarms))

    def test_add(self):
        self.add_some_alarms()
        alarms = list(self.alarm_conn.get_alarms())
        self.assertEqual(3, len(alarms))

        meter_names = sorted([a.rule['meter_name'] for a in alarms])
        self.assertEqual(['test.five', 'test.forty', 'test.one'], meter_names)

    def test_update(self):
        self.add_some_alarms()
        orange = list(self.alarm_conn.get_alarms(name='orange-alert'))[0]
        orange.enabled = False
        orange.state = alarm_models.Alarm.ALARM_INSUFFICIENT_DATA
        query = [{'field': 'metadata.group',
                  'op': 'eq',
                  'value': 'test.updated',
                  'type': 'string'}]
        orange.rule['query'] = query
        orange.rule['meter_name'] = 'new_meter_name'
        updated = self.alarm_conn.update_alarm(orange)
        self.assertEqual(False, updated.enabled)
        self.assertEqual(alarm_models.Alarm.ALARM_INSUFFICIENT_DATA,
                         updated.state)
        self.assertEqual(query, updated.rule['query'])
        self.assertEqual('new_meter_name', updated.rule['meter_name'])

    def test_update_llu(self):
        llu = alarm_models.Alarm(alarm_id='llu',
                                 enabled=True,
                                 type='threshold',
                                 name='llu',
                                 description='llu',
                                 timestamp=constants.MIN_DATETIME,
                                 user_id='bla',
                                 project_id='ffo',
                                 state="insufficient data",
                                 state_timestamp=constants.MIN_DATETIME,
                                 ok_actions=[],
                                 alarm_actions=[],
                                 insufficient_data_actions=[],
                                 repeat_actions=False,
                                 time_constraints=[],
                                 rule=dict(comparison_operator='lt',
                                           threshold=34,
                                           statistic='max',
                                           evaluation_periods=1,
                                           period=60,
                                           meter_name='llt',
                                           query=[])
                                 )
        updated = self.alarm_conn.update_alarm(llu)
        updated.state = alarm_models.Alarm.ALARM_OK
        updated.description = ':)'
        self.alarm_conn.update_alarm(updated)

        all = list(self.alarm_conn.get_alarms())
        self.assertEqual(1, len(all))

    def test_delete(self):
        self.add_some_alarms()
        victim = list(self.alarm_conn.get_alarms(name='orange-alert'))[0]
        self.alarm_conn.delete_alarm(victim.alarm_id)
        survivors = list(self.alarm_conn.get_alarms())
        self.assertEqual(2, len(survivors))
        for s in survivors:
            self.assertNotEqual(victim.name, s.name)


@tests_db.run_with('sqlite', 'mysql', 'pgsql', 'hbase', 'db2')
class AlarmHistoryTest(AlarmTestBase,
                       tests_db.MixinTestsWithBackendScenarios):

    def setUp(self):
        super(AlarmTestBase, self).setUp()
        self.add_some_alarms()
        self.prepare_alarm_history()

    def prepare_alarm_history(self):
        alarms = list(self.alarm_conn.get_alarms())
        for alarm in alarms:
            i = alarms.index(alarm)
            alarm_change = {
                "event_id": "3e11800c-a3ca-4991-b34b-d97efb6047d%s" % i,
                "alarm_id": alarm.alarm_id,
                "type": alarm_models.AlarmChange.CREATION,
                "detail": "detail %s" % alarm.name,
                "user_id": alarm.user_id,
                "project_id": alarm.project_id,
                "on_behalf_of": alarm.project_id,
                "timestamp": datetime.datetime(2014, 4, 7, 7, 30 + i)
            }
            self.alarm_conn.record_alarm_change(alarm_change=alarm_change)

    def _clear_alarm_history(self, utcnow, ttl, count):
        self.mock_utcnow.return_value = utcnow
        self.alarm_conn.clear_expired_alarm_history_data(ttl)
        history = list(self.alarm_conn.query_alarm_history())
        self.assertEqual(count, len(history))

    def test_clear_alarm_history_no_data_to_remove(self):
        utcnow = datetime.datetime(2013, 4, 7, 7, 30)
        self._clear_alarm_history(utcnow, 1, 3)

    def test_clear_some_alarm_history(self):
        utcnow = datetime.datetime(2014, 4, 7, 7, 35)
        self._clear_alarm_history(utcnow, 3 * 60, 1)

    def test_clear_all_alarm_history(self):
        utcnow = datetime.datetime(2014, 4, 7, 7, 45)
        self._clear_alarm_history(utcnow, 3 * 60, 0)

    def test_delete_history_when_delete_alarm(self):
        alarms = list(self.alarm_conn.get_alarms())
        self.assertEqual(3, len(alarms))
        history = list(self.alarm_conn.query_alarm_history())
        self.assertEqual(3, len(history))
        for alarm in alarms:
            self.alarm_conn.delete_alarm(alarm.alarm_id)
        self.assertEqual(3, len(alarms))
        history = list(self.alarm_conn.query_alarm_history())
        self.assertEqual(0, len(history))


class ComplexAlarmQueryTest(AlarmTestBase,
                            tests_db.MixinTestsWithBackendScenarios):

    def test_no_filter(self):
        self.add_some_alarms()
        result = list(self.alarm_conn.query_alarms())
        self.assertEqual(3, len(result))

    def test_no_filter_with_limit(self):
        self.add_some_alarms()
        result = list(self.alarm_conn.query_alarms(limit=2))
        self.assertEqual(2, len(result))

    def test_filter(self):
        self.add_some_alarms()
        filter_expr = {"and":
                       [{"or":
                        [{"=": {"name": "yellow-alert"}},
                         {"=": {"name": "red-alert"}}]},
                        {"=": {"enabled": True}}]}

        result = list(self.alarm_conn.query_alarms(filter_expr=filter_expr))

        self.assertEqual(1, len(result))
        for a in result:
            self.assertIn(a.name, set(["yellow-alert", "red-alert"]))
            self.assertTrue(a.enabled)

    def test_filter_with_regexp(self):
        self.add_some_alarms()
        filter_expr = {"and":
                       [{"or": [{"=": {"name": "yellow-alert"}},
                                {"=": {"name": "red-alert"}}]},
                        {"=~": {"description": "yel.*"}}]}

        result = list(self.alarm_conn.query_alarms(filter_expr=filter_expr))

        self.assertEqual(1, len(result))
        for a in result:
            self.assertEqual("yellow", a.description)

    def test_filter_for_alarm_id(self):
        self.add_some_alarms()
        filter_expr = {"=": {"alarm_id": "0r4ng3"}}

        result = list(self.alarm_conn.query_alarms(filter_expr=filter_expr))

        self.assertEqual(1, len(result))
        for a in result:
            self.assertEqual("0r4ng3", a.alarm_id)

    def test_filter_and_orderby(self):
        self.add_some_alarms()
        result = list(self.alarm_conn.query_alarms(filter_expr=(
            {"=": {"enabled": True}}),
            orderby=[{"name": "asc"}]))
        self.assertEqual(2, len(result))
        self.assertEqual(["orange-alert", "red-alert"],
                         [a.name for a in result])
        for a in result:
            self.assertTrue(a.enabled)


class ComplexAlarmHistoryQueryTest(AlarmTestBase,
                                   tests_db.MixinTestsWithBackendScenarios):
    def setUp(self):
        super(DBTestBase, self).setUp()
        self.filter_expr = {"and":
                            [{"or":
                              [{"=": {"type": "rule change"}},
                               {"=": {"type": "state transition"}}]},
                             {"=": {"alarm_id": "0r4ng3"}}]}
        self.add_some_alarms()
        self.prepare_alarm_history()

    def prepare_alarm_history(self):
        alarms = list(self.alarm_conn.get_alarms())
        name_index = {
            'red-alert': 0,
            'orange-alert': 1,
            'yellow-alert': 2
        }

        for alarm in alarms:
            i = name_index[alarm.name]
            alarm_change = dict(event_id=(
                                "16fd2706-8baf-433b-82eb-8c7fada847c%s" % i),
                                alarm_id=alarm.alarm_id,
                                type=alarm_models.AlarmChange.CREATION,
                                detail="detail %s" % alarm.name,
                                user_id=alarm.user_id,
                                project_id=alarm.project_id,
                                on_behalf_of=alarm.project_id,
                                timestamp=datetime.datetime(2012, 9, 24,
                                                            7 + i,
                                                            30 + i))
            self.alarm_conn.record_alarm_change(alarm_change=alarm_change)

            alarm_change2 = dict(event_id=(
                                 "16fd2706-8baf-433b-82eb-8c7fada847d%s" % i),
                                 alarm_id=alarm.alarm_id,
                                 type=alarm_models.AlarmChange.RULE_CHANGE,
                                 detail="detail %s" % i,
                                 user_id=alarm.user_id,
                                 project_id=alarm.project_id,
                                 on_behalf_of=alarm.project_id,
                                 timestamp=datetime.datetime(2012, 9, 25,
                                                             10 + i,
                                                             30 + i))
            self.alarm_conn.record_alarm_change(alarm_change=alarm_change2)

            alarm_change3 = dict(
                event_id="16fd2706-8baf-433b-82eb-8c7fada847e%s" % i,
                alarm_id=alarm.alarm_id,
                type=alarm_models.AlarmChange.STATE_TRANSITION,
                detail="detail %s" % (i + 1),
                user_id=alarm.user_id,
                project_id=alarm.project_id,
                on_behalf_of=alarm.project_id,
                timestamp=datetime.datetime(2012, 9, 26, 10 + i, 30 + i)
            )

            if alarm.name == "red-alert":
                alarm_change3['on_behalf_of'] = 'and-da-girls'

            self.alarm_conn.record_alarm_change(alarm_change=alarm_change3)

    def test_alarm_history_with_no_filter(self):
        history = list(self.alarm_conn.query_alarm_history())
        self.assertEqual(9, len(history))

    def test_alarm_history_with_no_filter_and_limit(self):
        history = list(self.alarm_conn.query_alarm_history(limit=3))
        self.assertEqual(3, len(history))

    def test_alarm_history_with_filter(self):
        history = list(
            self.alarm_conn.query_alarm_history(filter_expr=self.filter_expr))
        self.assertEqual(2, len(history))

    def test_alarm_history_with_regexp(self):
        filter_expr = {"and":
                       [{"=~": {"type": "(rule)|(state)"}},
                        {"=": {"alarm_id": "0r4ng3"}}]}
        history = list(
            self.alarm_conn.query_alarm_history(filter_expr=filter_expr))
        self.assertEqual(2, len(history))

    def test_alarm_history_with_filter_and_orderby(self):
        history = list(
            self.alarm_conn.query_alarm_history(filter_expr=self.filter_expr,
                                                orderby=[{"timestamp":
                                                          "asc"}]))
        self.assertEqual([alarm_models.AlarmChange.RULE_CHANGE,
                          alarm_models.AlarmChange.STATE_TRANSITION],
                         [h.type for h in history])

    def test_alarm_history_with_filter_and_orderby_and_limit(self):
        history = list(
            self.alarm_conn.query_alarm_history(filter_expr=self.filter_expr,
                                                orderby=[{"timestamp":
                                                          "asc"}],
                                                limit=1))
        self.assertEqual(alarm_models.AlarmChange.RULE_CHANGE, history[0].type)

    def test_alarm_history_with_on_behalf_of_filter(self):
        filter_expr = {"=": {"on_behalf_of": "and-da-girls"}}
        history = list(self.alarm_conn.query_alarm_history(
            filter_expr=filter_expr))
        self.assertEqual(1, len(history))
        self.assertEqual("16fd2706-8baf-433b-82eb-8c7fada847e0",
                         history[0].event_id)

    def test_alarm_history_with_alarm_id_as_filter(self):
        filter_expr = {"=": {"alarm_id": "r3d"}}
        history = list(self.alarm_conn.query_alarm_history(
            filter_expr=filter_expr, orderby=[{"timestamp": "asc"}]))
        self.assertEqual(3, len(history))
        self.assertEqual([alarm_models.AlarmChange.CREATION,
                          alarm_models.AlarmChange.RULE_CHANGE,
                          alarm_models.AlarmChange.STATE_TRANSITION],
                         [h.type for h in history])


class EventTestBase(tests_db.TestBase,
                    tests_db.MixinTestsWithBackendScenarios):
    """Separate test base class.

    We don't want to inherit all the Meter stuff.
    """

    def setUp(self):
        super(EventTestBase, self).setUp()
        self.prepare_data()

    def prepare_data(self):
        self.event_models = []
        base = 0
        self.start = datetime.datetime(2013, 12, 31, 5, 0)
        now = self.start
        for event_type in ['Foo', 'Bar', 'Zoo', 'Foo', 'Bar', 'Zoo']:
            trait_models = [event_models.Trait(name, dtype, value)
                            for name, dtype, value in [
                                ('trait_A', event_models.Trait.TEXT_TYPE,
                                    "my_%s_text" % event_type),
                                ('trait_B', event_models.Trait.INT_TYPE,
                                    base + 1),
                                ('trait_C', event_models.Trait.FLOAT_TYPE,
                                    float(base) + 0.123456),
                                ('trait_D', event_models.Trait.DATETIME_TYPE,
                                    now)]]
            self.event_models.append(
                event_models.Event("id_%s_%d" % (event_type, base),
                                   event_type, now, trait_models,
                                   {'status': {'nested': 'started'}}))
            base += 100
            now = now + datetime.timedelta(hours=1)
        self.end = now

        self.event_conn.record_events(self.event_models)


@tests_db.run_with('sqlite', 'mysql', 'pgsql')
class EventTTLTest(EventTestBase):

    @mock.patch.object(timeutils, 'utcnow')
    def test_clear_expired_event_data(self, mock_utcnow):
        mock_utcnow.return_value = datetime.datetime(2013, 12, 31, 10, 0)
        self.event_conn.clear_expired_event_data(3600)

        events = list(self.event_conn.get_events(storage.EventFilter()))
        self.assertEqual(2, len(events))
        event_types = list(self.event_conn.get_event_types())
        self.assertEqual(['Bar', 'Zoo'], event_types)
        for event_type in event_types:
            trait_types = list(self.event_conn.get_trait_types(event_type))
            self.assertEqual(4, len(trait_types))
            traits = list(self.event_conn.get_traits(event_type))
            self.assertEqual(4, len(traits))


@tests_db.run_with('sqlite', 'mysql', 'pgsql', 'mongodb', 'db2')
class EventTest(EventTestBase):
    def test_duplicate_message_id(self):
        now = datetime.datetime.utcnow()
        m = [event_models.Event("1", "Foo", now, None, {}),
             event_models.Event("1", "Zoo", now, [], {})]
        with mock.patch('%s.LOG' %
                        self.event_conn.record_events.__module__) as log:
            self.event_conn.record_events(m)
            self.assertEqual(1, log.info.call_count)

    def test_bad_event(self):
        now = datetime.datetime.utcnow()
        broken_event = event_models.Event("1", "Foo", now, None, {})
        del(broken_event.__dict__['raw'])
        m = [broken_event, broken_event]
        with mock.patch('%s.LOG' %
                        self.event_conn.record_events.__module__) as log:
            self.assertRaises(AttributeError, self.event_conn.record_events, m)
            # ensure that record_events does not break on first error but
            # delays exception and tries to record each event.
            self.assertEqual(2, log.exception.call_count)


class GetEventTest(EventTestBase):

    def test_generated_is_datetime(self):
        event_filter = storage.EventFilter(self.start, self.end)
        events = [event for event in self.event_conn.get_events(event_filter)]
        self.assertEqual(6, len(events))
        for i, event in enumerate(events):
            self.assertIsInstance(event.generated, datetime.datetime)
            self.assertEqual(event.generated,
                             self.event_models[i].generated)
            model_traits = self.event_models[i].traits
            for j, trait in enumerate(event.traits):
                if trait.dtype == event_models.Trait.DATETIME_TYPE:
                    self.assertIsInstance(trait.value, datetime.datetime)
                    self.assertEqual(trait.value, model_traits[j].value)

    def test_simple_get(self):
        event_filter = storage.EventFilter(self.start, self.end)
        events = [event for event in self.event_conn.get_events(event_filter)]
        self.assertEqual(6, len(events))
        start_time = None
        for i, type in enumerate(['Foo', 'Bar', 'Zoo']):
            self.assertEqual(type, events[i].event_type)
            self.assertEqual(4, len(events[i].traits))
            # Ensure sorted results ...
            if start_time is not None:
                # Python 2.6 has no assertLess :(
                self.assertTrue(start_time < events[i].generated)
            start_time = events[i].generated

    def test_simple_get_event_type(self):
        expected_trait_values = {
            'id_Bar_100': {
                'trait_A': 'my_Bar_text',
                'trait_B': 101,
                'trait_C': 100.123456,
                'trait_D': self.start + datetime.timedelta(hours=1)
            },
            'id_Bar_400': {
                'trait_A': 'my_Bar_text',
                'trait_B': 401,
                'trait_C': 400.123456,
                'trait_D': self.start + datetime.timedelta(hours=4)
            }
        }

        event_filter = storage.EventFilter(self.start, self.end, "Bar")
        events = [event for event in self.event_conn.get_events(event_filter)]
        self.assertEqual(2, len(events))
        self.assertEqual("Bar", events[0].event_type)
        self.assertEqual("Bar", events[1].event_type)
        self.assertEqual(4, len(events[0].traits))
        self.assertEqual(4, len(events[1].traits))
        for event in events:
            trait_values = expected_trait_values.get(event.message_id,
                                                     None)
            if not trait_values:
                self.fail("Unexpected event ID returned:" % event.message_id)

            for trait in event.traits:
                expected_val = trait_values.get(trait.name)
                if not expected_val:
                    self.fail("Unexpected trait type: %s" % trait.dtype)
                self.assertEqual(expected_val, trait.value)

    def test_get_event_trait_filter(self):
        trait_filters = [{'key': 'trait_B', 'integer': 101}]
        event_filter = storage.EventFilter(self.start, self.end,
                                           traits_filter=trait_filters)
        events = [event for event in self.event_conn.get_events(event_filter)]
        self.assertEqual(1, len(events))
        self.assertEqual("Bar", events[0].event_type)
        self.assertEqual(4, len(events[0].traits))

    def test_get_event_trait_filter_op_string(self):
        trait_filters = [{'key': 'trait_A', 'string': 'my_Foo_text',
                          'op': 'eq'}]
        event_filter = storage.EventFilter(self.start, self.end,
                                           traits_filter=trait_filters)
        events = [event for event in self.event_conn.get_events(event_filter)]
        self.assertEqual(2, len(events))
        self.assertEqual("Foo", events[0].event_type)
        self.assertEqual(4, len(events[0].traits))
        trait_filters[0].update({'key': 'trait_A', 'op': 'lt'})
        event_filter = storage.EventFilter(self.start, self.end,
                                           traits_filter=trait_filters)
        events = [event for event in self.event_conn.get_events(event_filter)]
        self.assertEqual(2, len(events))
        self.assertEqual("Bar", events[0].event_type)
        trait_filters[0].update({'key': 'trait_A', 'op': 'le'})
        event_filter = storage.EventFilter(self.start, self.end,
                                           traits_filter=trait_filters)
        events = [event for event in self.event_conn.get_events(event_filter)]
        self.assertEqual(4, len(events))
        self.assertEqual("Bar", events[1].event_type)
        trait_filters[0].update({'key': 'trait_A', 'op': 'ne'})
        event_filter = storage.EventFilter(self.start, self.end,
                                           traits_filter=trait_filters)
        events = [event for event in self.event_conn.get_events(event_filter)]
        self.assertEqual(4, len(events))
        self.assertEqual("Zoo", events[3].event_type)
        trait_filters[0].update({'key': 'trait_A', 'op': 'gt'})
        event_filter = storage.EventFilter(self.start, self.end,
                                           traits_filter=trait_filters)
        events = [event for event in self.event_conn.get_events(event_filter)]
        self.assertEqual(2, len(events))
        self.assertEqual("Zoo", events[0].event_type)
        trait_filters[0].update({'key': 'trait_A', 'op': 'ge'})
        event_filter = storage.EventFilter(self.start, self.end,
                                           traits_filter=trait_filters)
        events = [event for event in self.event_conn.get_events(event_filter)]
        self.assertEqual(4, len(events))
        self.assertEqual("Foo", events[2].event_type)

    def test_get_event_trait_filter_op_integer(self):
        trait_filters = [{'key': 'trait_B', 'integer': 101, 'op': 'eq'}]
        event_filter = storage.EventFilter(self.start, self.end,
                                           traits_filter=trait_filters)
        events = [event for event in self.event_conn.get_events(event_filter)]
        self.assertEqual(1, len(events))
        self.assertEqual("Bar", events[0].event_type)
        self.assertEqual(4, len(events[0].traits))
        trait_filters[0].update({'key': 'trait_B', 'op': 'lt'})
        event_filter = storage.EventFilter(self.start, self.end,
                                           traits_filter=trait_filters)
        events = [event for event in self.event_conn.get_events(event_filter)]
        self.assertEqual(1, len(events))
        self.assertEqual("Foo", events[0].event_type)
        trait_filters[0].update({'key': 'trait_B', 'op': 'le'})
        event_filter = storage.EventFilter(self.start, self.end,
                                           traits_filter=trait_filters)
        events = [event for event in self.event_conn.get_events(event_filter)]
        self.assertEqual(2, len(events))
        self.assertEqual("Bar", events[1].event_type)
        trait_filters[0].update({'key': 'trait_B', 'op': 'ne'})
        event_filter = storage.EventFilter(self.start, self.end,
                                           traits_filter=trait_filters)
        events = [event for event in self.event_conn.get_events(event_filter)]
        self.assertEqual(5, len(events))
        self.assertEqual("Zoo", events[4].event_type)
        trait_filters[0].update({'key': 'trait_B', 'op': 'gt'})
        event_filter = storage.EventFilter(self.start, self.end,
                                           traits_filter=trait_filters)
        events = [event for event in self.event_conn.get_events(event_filter)]
        self.assertEqual(4, len(events))
        self.assertEqual("Zoo", events[0].event_type)
        trait_filters[0].update({'key': 'trait_B', 'op': 'ge'})
        event_filter = storage.EventFilter(self.start, self.end,
                                           traits_filter=trait_filters)
        events = [event for event in self.event_conn.get_events(event_filter)]
        self.assertEqual(5, len(events))
        self.assertEqual("Foo", events[2].event_type)

    def test_get_event_trait_filter_op_float(self):
        trait_filters = [{'key': 'trait_C', 'float': 300.123456, 'op': 'eq'}]
        event_filter = storage.EventFilter(self.start, self.end,
                                           traits_filter=trait_filters)
        events = [event for event in self.event_conn.get_events(event_filter)]
        self.assertEqual(1, len(events))
        self.assertEqual("Foo", events[0].event_type)
        self.assertEqual(4, len(events[0].traits))
        trait_filters[0].update({'key': 'trait_C', 'op': 'lt'})
        event_filter = storage.EventFilter(self.start, self.end,
                                           traits_filter=trait_filters)
        events = [event for event in self.event_conn.get_events(event_filter)]
        self.assertEqual(3, len(events))
        self.assertEqual("Zoo", events[2].event_type)
        trait_filters[0].update({'key': 'trait_C', 'op': 'le'})
        event_filter = storage.EventFilter(self.start, self.end,
                                           traits_filter=trait_filters)
        events = [event for event in self.event_conn.get_events(event_filter)]
        self.assertEqual(4, len(events))
        self.assertEqual("Bar", events[1].event_type)
        trait_filters[0].update({'key': 'trait_C', 'op': 'ne'})
        event_filter = storage.EventFilter(self.start, self.end,
                                           traits_filter=trait_filters)
        events = [event for event in self.event_conn.get_events(event_filter)]
        self.assertEqual(5, len(events))
        self.assertEqual("Zoo", events[2].event_type)
        trait_filters[0].update({'key': 'trait_C', 'op': 'gt'})
        event_filter = storage.EventFilter(self.start, self.end,
                                           traits_filter=trait_filters)
        events = [event for event in self.event_conn.get_events(event_filter)]
        self.assertEqual(2, len(events))
        self.assertEqual("Bar", events[0].event_type)
        trait_filters[0].update({'key': 'trait_C', 'op': 'ge'})
        event_filter = storage.EventFilter(self.start, self.end,
                                           traits_filter=trait_filters)
        events = [event for event in self.event_conn.get_events(event_filter)]
        self.assertEqual(3, len(events))
        self.assertEqual("Zoo", events[2].event_type)

    def test_get_event_trait_filter_op_datetime(self):
        trait_filters = [{'key': 'trait_D',
                          'datetime': self.start + datetime.timedelta(hours=2),
                          'op': 'eq'}]
        event_filter = storage.EventFilter(self.start, self.end,
                                           traits_filter=trait_filters)
        events = [event for event in self.event_conn.get_events(event_filter)]
        self.assertEqual(1, len(events))
        self.assertEqual("Zoo", events[0].event_type)
        self.assertEqual(4, len(events[0].traits))
        trait_filters[0].update({'key': 'trait_D', 'op': 'lt'})
        event_filter = storage.EventFilter(self.start, self.end,
                                           traits_filter=trait_filters)
        events = [event for event in self.event_conn.get_events(event_filter)]
        self.assertEqual(2, len(events))
        trait_filters[0].update({'key': 'trait_D', 'op': 'le'})
        self.assertEqual("Bar", events[1].event_type)
        event_filter = storage.EventFilter(self.start, self.end,
                                           traits_filter=trait_filters)
        events = [event for event in self.event_conn.get_events(event_filter)]
        self.assertEqual(3, len(events))
        self.assertEqual("Bar", events[1].event_type)
        trait_filters[0].update({'key': 'trait_D', 'op': 'ne'})
        event_filter = storage.EventFilter(self.start, self.end,
                                           traits_filter=trait_filters)
        events = [event for event in self.event_conn.get_events(event_filter)]
        self.assertEqual(5, len(events))
        self.assertEqual("Foo", events[2].event_type)
        trait_filters[0].update({'key': 'trait_D', 'op': 'gt'})
        event_filter = storage.EventFilter(self.start, self.end,
                                           traits_filter=trait_filters)
        events = [event for event in self.event_conn.get_events(event_filter)]
        self.assertEqual(3, len(events))
        self.assertEqual("Zoo", events[2].event_type)
        trait_filters[0].update({'key': 'trait_D', 'op': 'ge'})
        event_filter = storage.EventFilter(self.start, self.end,
                                           traits_filter=trait_filters)
        events = [event for event in self.event_conn.get_events(event_filter)]
        self.assertEqual(4, len(events))
        self.assertEqual("Bar", events[2].event_type)

    def test_get_event_multiple_trait_filter(self):
        trait_filters = [{'key': 'trait_B', 'integer': 1},
                         {'key': 'trait_A', 'string': 'my_Foo_text'},
                         {'key': 'trait_C', 'float': 0.123456}]
        event_filter = storage.EventFilter(self.start, self.end,
                                           traits_filter=trait_filters)
        events = [event for event in self.event_conn.get_events(event_filter)]
        self.assertEqual(1, len(events))
        self.assertEqual("Foo", events[0].event_type)
        self.assertEqual(4, len(events[0].traits))

    def test_get_event_multiple_trait_filter_expect_none(self):
        trait_filters = [{'key': 'trait_B', 'integer': 1},
                         {'key': 'trait_A', 'string': 'my_Zoo_text'}]
        event_filter = storage.EventFilter(self.start, self.end,
                                           traits_filter=trait_filters)
        events = [event for event in self.event_conn.get_events(event_filter)]
        self.assertEqual(0, len(events))

    def test_get_event_types(self):
        event_types = [e for e in
                       self.event_conn.get_event_types()]

        self.assertEqual(3, len(event_types))
        self.assertIn("Bar", event_types)
        self.assertIn("Foo", event_types)
        self.assertIn("Zoo", event_types)

    def test_get_trait_types(self):
        trait_types = [tt for tt in
                       self.event_conn.get_trait_types("Foo")]
        self.assertEqual(4, len(trait_types))
        trait_type_names = map(lambda x: x['name'], trait_types)
        self.assertIn("trait_A", trait_type_names)
        self.assertIn("trait_B", trait_type_names)
        self.assertIn("trait_C", trait_type_names)
        self.assertIn("trait_D", trait_type_names)

    def test_get_trait_types_unknown_event(self):
        trait_types = [tt for tt in
                       self.event_conn.get_trait_types("Moo")]
        self.assertEqual(0, len(trait_types))

    def test_get_traits(self):
        traits = self.event_conn.get_traits("Bar")
        # format results in a way that makes them easier to work with
        trait_dict = {}
        for trait in traits:
            trait_dict[trait.name] = trait.dtype

        self.assertIn("trait_A", trait_dict)
        self.assertEqual(event_models.Trait.TEXT_TYPE, trait_dict["trait_A"])
        self.assertIn("trait_B", trait_dict)
        self.assertEqual(event_models.Trait.INT_TYPE, trait_dict["trait_B"])
        self.assertIn("trait_C", trait_dict)
        self.assertEqual(event_models.Trait.FLOAT_TYPE, trait_dict["trait_C"])
        self.assertIn("trait_D", trait_dict)
        self.assertEqual(event_models.Trait.DATETIME_TYPE,
                         trait_dict["trait_D"])

    def test_get_all_traits(self):
        traits = self.event_conn.get_traits("Foo")
        traits = sorted([t for t in traits], key=operator.attrgetter('dtype'))
        self.assertEqual(8, len(traits))
        trait = traits[0]
        self.assertEqual("trait_A", trait.name)
        self.assertEqual(event_models.Trait.TEXT_TYPE, trait.dtype)

    def test_simple_get_event_no_traits(self):
        new_events = [event_models.Event("id_notraits", "NoTraits",
                      self.start, [], {})]
        self.event_conn.record_events(new_events)
        event_filter = storage.EventFilter(self.start, self.end, "NoTraits")
        events = [event for event in self.event_conn.get_events(event_filter)]
        self.assertEqual(1, len(events))
        self.assertEqual("id_notraits", events[0].message_id)
        self.assertEqual("NoTraits", events[0].event_type)
        self.assertEqual(0, len(events[0].traits))

    def test_simple_get_no_filters(self):
        event_filter = storage.EventFilter(None, None, None)
        events = [event for event in self.event_conn.get_events(event_filter)]
        self.assertEqual(6, len(events))

    def test_get_by_message_id(self):
        new_events = [event_models.Event("id_testid",
                                         "MessageIDTest",
                                         self.start,
                                         [], {})]

        self.event_conn.record_events(new_events)
        event_filter = storage.EventFilter(message_id="id_testid")
        events = [event for event in self.event_conn.get_events(event_filter)]
        self.assertEqual(1, len(events))
        event = events[0]
        self.assertEqual("id_testid", event.message_id)

    def test_simple_get_raw(self):
        event_filter = storage.EventFilter()
        events = [event for event in self.event_conn.get_events(event_filter)]
        self.assertTrue(events)
        self.assertEqual({'status': {'nested': 'started'}}, events[0].raw)

    def test_trait_type_enforced_on_none(self):
        new_events = [event_models.Event(
            "id_testid", "MessageIDTest", self.start,
            [event_models.Trait('text', event_models.Trait.TEXT_TYPE, ''),
             event_models.Trait('int', event_models.Trait.INT_TYPE, 0),
             event_models.Trait('float', event_models.Trait.FLOAT_TYPE, 0.0)],
            {})]
        self.event_conn.record_events(new_events)
        event_filter = storage.EventFilter(message_id="id_testid")
        events = [event for event in self.event_conn.get_events(event_filter)]
        options = [(event_models.Trait.TEXT_TYPE, ''),
                   (event_models.Trait.INT_TYPE, 0.0),
                   (event_models.Trait.FLOAT_TYPE, 0.0)]
        for trait in events[0].traits:
            options.remove((trait.dtype, trait.value))


class BigIntegerTest(tests_db.TestBase,
                     tests_db.MixinTestsWithBackendScenarios):
    def test_metadata_bigint(self):
        metadata = {'bigint': 99999999999999}
        s = sample.Sample(name='name',
                          type=sample.TYPE_GAUGE,
                          unit='B',
                          volume=1,
                          user_id='user-id',
                          project_id='project-id',
                          resource_id='resource-id',
                          timestamp=datetime.datetime.utcnow(),
                          resource_metadata=metadata)
        msg = utils.meter_message_from_counter(
            s, self.CONF.publisher.telemetry_secret)
        self.conn.record_metering_data(msg)


@tests_db.run_with('mongodb')
class MongoAutoReconnectTest(DBTestBase,
                             tests_db.MixinTestsWithBackendScenarios):

    def setUp(self):
        super(MongoAutoReconnectTest, self).setUp()
        self.CONF.set_override('retry_interval', 0, group='database')

    def test_mongo_client(self):
        if cfg.CONF.database.mongodb_replica_set:
            self.assertIsInstance(self.conn.conn.conn,
                                  pymongo.MongoReplicaSetClient)
        else:
            self.assertIsInstance(self.conn.conn.conn,
                                  pymongo.MongoClient)

    def test_mongo_cursor_next(self):
        expected_first_sample_timestamp = datetime.datetime(2012, 7, 2, 10, 39)
        raise_exc = [False, True]
        method = self.conn.db.resource.find().cursor.next
        with mock.patch('pymongo.cursor.Cursor.next',
                        mock.Mock()) as mock_next:
            mock_next.side_effect = self.create_side_effect(
                method, pymongo.errors.AutoReconnect, raise_exc)
            resource = self.conn.db.resource.find().next()
            self.assertEqual(expected_first_sample_timestamp,
                             resource['first_sample_timestamp'])

    def test_mongo_insert(self):
        raise_exc = [False, True]
        method = self.conn.db.meter.insert

        with mock.patch('pymongo.collection.Collection.insert',
                        mock.Mock(return_value=method)) as mock_insert:
            mock_insert.side_effect = self.create_side_effect(
                method, pymongo.errors.AutoReconnect, raise_exc)
            mock_insert.__name__ = 'insert'
            self.create_and_store_sample(
                timestamp=datetime.datetime(2014, 10, 15, 14, 39),
                source='test-proxy')
            meters = list(self.conn.db.meter.find())
            self.assertEqual(12, len(meters))

    def test_mongo_find_and_modify(self):
        raise_exc = [False, True]
        method = self.conn.db.resource.find_and_modify

        with mock.patch('pymongo.collection.Collection.find_and_modify',
                        mock.Mock()) as mock_fam:
            mock_fam.side_effect = self.create_side_effect(
                method, pymongo.errors.AutoReconnect, raise_exc)
            mock_fam.__name__ = 'find_and_modify'
            self.create_and_store_sample(
                timestamp=datetime.datetime(2014, 10, 15, 14, 39),
                source='test-proxy')
            data = self.conn.db.resource.find(
                {'last_sample_timestamp':
                 datetime.datetime(2014, 10, 15, 14, 39)})[0]['source']
            self.assertEqual('test-proxy', data)

    def test_mongo_update(self):
        raise_exc = [False, True]
        method = self.conn.db.resource.update

        with mock.patch('pymongo.collection.Collection.update',
                        mock.Mock()) as mock_update:
            mock_update.side_effect = self.create_side_effect(
                method, pymongo.errors.AutoReconnect, raise_exc)
            mock_update.__name__ = 'update'
            self.create_and_store_sample(
                timestamp=datetime.datetime(2014, 10, 15, 17, 39),
                source='test-proxy-update')
            data = self.conn.db.resource.find(
                {'last_sample_timestamp':
                 datetime.datetime(2014, 10, 15, 17, 39)})[0]['source']
            self.assertEqual('test-proxy-update', data)


@tests_db.run_with('mongodb')
class MongoTimeToLiveTest(DBTestBase, tests_db.MixinTestsWithBackendScenarios):

    def test_ensure_index(self):
        cfg.CONF.set_override('metering_time_to_live', 5, group='database')
        self.conn.upgrade()
        self.assertEqual(5, self.conn.db.resource.index_information()
                         ['resource_ttl']['expireAfterSeconds'])
        self.assertEqual(5, self.conn.db.meter.index_information()
                         ['meter_ttl']['expireAfterSeconds'])

    def test_modification_of_index(self):
        cfg.CONF.set_override('metering_time_to_live', 5, group='database')
        self.conn.upgrade()
        cfg.CONF.set_override('metering_time_to_live', 15, group='database')
        self.conn.upgrade()
        self.assertEqual(15, self.conn.db.resource.index_information()
                         ['resource_ttl']['expireAfterSeconds'])
        self.assertEqual(15, self.conn.db.meter.index_information()
                         ['meter_ttl']['expireAfterSeconds'])


class TestRecordUnicodeSamples(DBTestBase,
                               tests_db.MixinTestsWithBackendScenarios):
    def prepare_data(self):
        self.msgs = []
        self.msgs.append(self.create_and_store_sample(
            name=u'meter.accent\xe9\u0437',
            metadata={u"metadata_key\xe9\u0437": "test",
                      u"metadata_key": u"test\xe9\u0437"},
        ))

    def test_unicode_sample(self):
        f = storage.SampleFilter()
        results = list(self.conn.get_samples(f))
        self.assertEqual(1, len(results))
        expected = self.msgs[0]
        actual = results[0].as_dict()
        self.assertEqual(expected['counter_name'], actual['counter_name'])
        self.assertEqual(expected['resource_metadata'],
                         actual['resource_metadata'])
