# -*- encoding: utf-8 -*-
#
# Copyright © 2012 New Dream Network, LLC (DreamHost)
# Copyright © 2013 eNovance
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
"""MongoDB storage backend
"""

import copy
import datetime
import operator
import os
import re
import urlparse
import uuid

import bson.code
import bson.objectid
import pymongo

from oslo.config import cfg

from ceilometer.openstack.common import log
from ceilometer.openstack.common import timeutils
from ceilometer import storage
from ceilometer.storage import base
from ceilometer.storage import models

cfg.CONF.import_opt('time_to_live', 'ceilometer.storage',
                    group="database")

LOG = log.getLogger(__name__)


class MongoDBStorage(base.StorageEngine):
    """Put the data into a MongoDB database

    Collections::

        - user
          - { _id: user id
              source: [ array of source ids reporting for the user ]
              }
        - project
          - { _id: project id
              source: [ array of source ids reporting for the project ]
              }
        - meter
          - the raw incoming data
        - resource
          - the metadata for resources
          - { _id: uuid of resource,
              metadata: metadata dictionaries
              user_id: uuid
              project_id: uuid
              meter: [ array of {counter_name: string, counter_type: string,
                                 counter_unit: string} ]
            }
    """

    OPTIONS = [
        cfg.StrOpt('replica_set_name',
                   default='',
                   help='Used to identify the replication set name',
                   ),
    ]

    OPTION_GROUP = cfg.OptGroup(name='storage_mongodb',
                                title='Options for the mongodb storage')

    def register_opts(self, conf):
        """Register any configuration options used by this engine.
        """
        conf.register_group(self.OPTION_GROUP)
        conf.register_opts(self.OPTIONS, self.OPTION_GROUP)

    def get_connection(self, conf):
        """Return a Connection instance based on the configuration settings.
        """
        return Connection(conf)


def make_timestamp_range(start, end,
                         start_timestamp_op=None, end_timestamp_op=None):
    """Given two possible datetimes and their operations, create the query
    document to find timestamps within that range.
    By default, using $gte for the lower bound and $lt for the
    upper bound.
    """
    ts_range = {}

    if start:
        if start_timestamp_op == 'gt':
            start_timestamp_op = '$gt'
        else:
            start_timestamp_op = '$gte'
        ts_range[start_timestamp_op] = start

    if end:
        if end_timestamp_op == 'le':
            end_timestamp_op = '$lte'
        else:
            end_timestamp_op = '$lt'
        ts_range[end_timestamp_op] = end
    return ts_range


def make_query_from_filter(sample_filter, require_meter=True):
    """Return a query dictionary based on the settings in the filter.

    :param filter: SampleFilter instance
    :param require_meter: If true and the filter does not have a meter,
                          raise an error.
    """
    q = {}

    if sample_filter.user:
        q['user_id'] = sample_filter.user
    if sample_filter.project:
        q['project_id'] = sample_filter.project

    if sample_filter.meter:
        q['counter_name'] = sample_filter.meter
    elif require_meter:
        raise RuntimeError('Missing required meter specifier')

    ts_range = make_timestamp_range(sample_filter.start, sample_filter.end,
                                    sample_filter.start_timestamp_op,
                                    sample_filter.end_timestamp_op)
    if ts_range:
        q['timestamp'] = ts_range

    if sample_filter.resource:
        q['resource_id'] = sample_filter.resource
    if sample_filter.source:
        q['source'] = sample_filter.source

    # so the samples call metadata resource_metadata, so we convert
    # to that.
    q.update(dict(('resource_%s' % k, v)
                  for (k, v) in sample_filter.metaquery.iteritems()))
    return q


class ConnectionPool(object):

    def __init__(self):
        self._pool = {}

    def connect(self, opts):
        # opts is a dict, dict are unhashable, convert to tuple
        connection_pool_key = tuple(sorted(opts.items()))

        if connection_pool_key not in self._pool:
            LOG.info('connecting to MongoDB replicaset "%s" on %s',
                     opts['replica_set'],
                     opts['netloc'])
            self._pool[connection_pool_key] = pymongo.Connection(
                opts['netloc'],
                replicaSet=opts['replica_set'],
                safe=True)

        return self._pool.get(connection_pool_key)


class Connection(base.Connection):
    """MongoDB connection.
    """

    CONNECTION_POOL = ConnectionPool()

    REDUCE_GROUP_CLEAN = bson.code.Code("""
    function ( curr, result ) {
        if (result.resources.indexOf(curr.resource_id) < 0)
            result.resources.push(curr.resource_id);
        if (result.users.indexOf(curr.user_id) < 0)
            result.users.push(curr.user_id);
        if (result.projects.indexOf(curr.project_id) < 0)
            result.projects.push(curr.project_id);
    }
    """)

    MAP_STATS = bson.code.Code("""
    function () {
        emit('statistics', { min : this.counter_volume,
                             max : this.counter_volume,
                             sum : this.counter_volume,
                             count : NumberInt(1),
                             duration_start : this.timestamp,
                             duration_end : this.timestamp,
                             period_start : this.timestamp,
                             period_end : this.timestamp} )
    }
    """)

    MAP_STATS_PERIOD = bson.code.Code("""
    function () {
        var period = %d * 1000;
        var period_first = %d * 1000;
        var period_start = period_first
                           + (Math.floor(new Date(this.timestamp.getTime()
                                         - period_first) / period)
                              * period);
        emit(period_start,
             { min : this.counter_volume,
               max : this.counter_volume,
               sum : this.counter_volume,
               count : NumberInt(1),
               duration_start : this.timestamp,
               duration_end : this.timestamp,
               period_start : new Date(period_start),
               period_end : new Date(period_start + period) } )
    }
    """)

    REDUCE_STATS = bson.code.Code("""
    function (key, values) {
        var res = { min: values[0].min,
                    max: values[0].max,
                    count: values[0].count,
                    sum: values[0].sum,
                    period_start: values[0].period_start,
                    period_end: values[0].period_end,
                    duration_start: values[0].duration_start,
                    duration_end: values[0].duration_end };
        for ( var i=1; i<values.length; i++ ) {
            if ( values[i].min < res.min )
               res.min = values[i].min;
            if ( values[i].max > res.max )
               res.max = values[i].max;
            res.count = NumberInt(res.count + values[i].count);
            res.sum += values[i].sum;
            if ( values[i].duration_start < res.duration_start )
               res.duration_start = values[i].duration_start;
            if ( values[i].duration_end > res.duration_end )
               res.duration_end = values[i].duration_end;
        }
        return res;
    }
    """)

    FINALIZE_STATS = bson.code.Code("""
    function (key, value) {
        value.avg = value.sum / value.count;
        value.duration = (value.duration_end - value.duration_start) / 1000;
        value.period = NumberInt((value.period_end - value.period_start)
                                  / 1000);
        return value;
    }""")

    def __init__(self, conf):
        opts = self._parse_connection_url(conf.database.connection)

        if opts['netloc'] == '__test__':
            url = os.environ.get('CEILOMETER_TEST_MONGODB_URL')
            if not url:
                raise RuntimeError(
                    "No MongoDB test URL set,"
                    "export CEILOMETER_TEST_MONGODB_URL environment variable")
            opts = self._parse_connection_url(url)

        # FIXME(jd) This should be a parameter in the database URL, not global
        opts['replica_set'] = conf.storage_mongodb.replica_set_name

        # NOTE(jd) Use our own connection pooling on top of the Pymongo one.
        # We need that otherwise we overflow the MongoDB instance with new
        # connection since we instanciate a Pymongo client each time someone
        # requires a new storage connection.
        self.conn = self.CONNECTION_POOL.connect(opts)

        self.db = getattr(self.conn, opts['dbname'])
        if 'username' in opts:
            self.db.authenticate(opts['username'], opts['password'])

        # Establish indexes
        #
        # We need variations for user_id vs. project_id because of the
        # way the indexes are stored in b-trees. The user_id and
        # project_id values are usually mutually exclusive in the
        # queries, so the database won't take advantage of an index
        # including both.
        for primary in ['user_id', 'project_id']:
            self.db.resource.ensure_index([
                (primary, pymongo.ASCENDING),
                ('source', pymongo.ASCENDING),
            ], name='resource_idx')
            self.db.meter.ensure_index([
                ('resource_id', pymongo.ASCENDING),
                (primary, pymongo.ASCENDING),
                ('counter_name', pymongo.ASCENDING),
                ('timestamp', pymongo.ASCENDING),
                ('source', pymongo.ASCENDING),
            ], name='meter_idx')
        self.db.meter.ensure_index([('timestamp', pymongo.DESCENDING)],
                                   name='timestamp_idx')

        # Since mongodb 2.2 support db-ttl natively
        if self._is_natively_ttl_supported():
            self._ensure_meter_ttl_index()

    def _ensure_meter_ttl_index(self):
        indexes = self.db.meter.index_information()

        ttl = cfg.CONF.database.time_to_live

        if ttl <= 0:
            if 'meter_ttl' in indexes:
                self.db.meter.drop_index('meter_ttl')
            return

        if 'meter_ttl' in indexes:
            # NOTE(sileht): manually check expireAfterSeconds because
            # ensure_index doesn't update index options if the index already
            # exists
            if ttl == indexes['meter_ttl'].get('expireAfterSeconds', -1):
                return

            self.db.meter.drop_index('meter_ttl')

        self.db.meter.create_index(
            [('timestamp', pymongo.ASCENDING)],
            expireAfterSeconds=ttl,
            name='meter_ttl'
        )

    def _is_natively_ttl_supported(self):
        # Assume is not supported if we can get the version
        return self.conn.server_info().get('versionArray', []) >= [2, 2]

    @staticmethod
    def upgrade(version=None):
        pass

    def clear(self):
        self.conn.drop_database(self.db)

    @staticmethod
    def _parse_connection_url(url):
        opts = {}
        result = urlparse.urlparse(url)
        opts['dbtype'] = result.scheme
        opts['dbname'] = result.path.replace('/', '')
        netloc_match = re.match(r'(?:(\w+:\w+)@)?(.*)', result.netloc)
        auth = netloc_match.group(1)
        opts['netloc'] = netloc_match.group(2)
        if auth:
            opts['username'], opts['password'] = auth.split(':')
        return opts

    def record_metering_data(self, data):
        """Write the data to the backend storage system.

        :param data: a dictionary such as returned by
                     ceilometer.meter.meter_message_from_counter
        """
        # Make sure we know about the user and project
        self.db.user.update(
            {'_id': data['user_id']},
            {'$addToSet': {'source': data['source'],
                           },
             },
            upsert=True,
        )
        self.db.project.update(
            {'_id': data['project_id']},
            {'$addToSet': {'source': data['source'],
                           },
             },
            upsert=True,
        )

        # Record the updated resource metadata
        self.db.resource.update(
            {'_id': data['resource_id']},
            {'$set': {'project_id': data['project_id'],
                      'user_id': data['user_id'],
                      'metadata': data['resource_metadata'],
                      'source': data['source'],
                      },
             '$addToSet': {'meter': {'counter_name': data['counter_name'],
                                     'counter_type': data['counter_type'],
                                     'counter_unit': data['counter_unit'],
                                     },
                           },
             },
            upsert=True,
        )

        # Record the raw data for the meter. Use a copy so we do not
        # modify a data structure owned by our caller (the driver adds
        # a new key '_id').
        record = copy.copy(data)
        self.db.meter.insert(record)

    def clear_expired_metering_data(self, ttl):
        """Clear expired data from the backend storage system according to the
        time-to-live.

        :param ttl: Number of seconds to keep records for.

        """
        # Before mongodb 2.2 we need to clear expired data manually
        if not self._is_natively_ttl_supported():
            end = timeutils.utcnow() - datetime.timedelta(seconds=ttl)
            f = storage.SampleFilter(end=end)
            q = make_query_from_filter(f, require_meter=False)
            self.db.meter.remove(q)

        results = self.db.meter.group(
            key={},
            condition={},
            reduce=self.REDUCE_GROUP_CLEAN,
            initial={
                'resources': [],
                'users': [],
                'projects': [],
            }
        )[0]

        self.db.user.remove({'_id': {'$nin': results['users']}})
        self.db.project.remove({'_id': {'$nin': results['projects']}})
        self.db.resource.remove({'_id': {'$nin': results['resources']}})

    def get_users(self, source=None):
        """Return an iterable of user id strings.

        :param source: Optional source filter.
        """
        q = {}
        if source is not None:
            q['source'] = source
        return sorted(self.db.user.find(q).distinct('_id'))

    def get_projects(self, source=None):
        """Return an iterable of project id strings.

        :param source: Optional source filter.
        """
        q = {}
        if source is not None:
            q['source'] = source
        return sorted(self.db.project.find(q).distinct('_id'))

    def get_resources(self, user=None, project=None, source=None,
                      start_timestamp=None, start_timestamp_op=None,
                      end_timestamp=None, end_timestamp_op=None,
                      metaquery={}, resource=None):
        """Return an iterable of models.Resource instances

        :param user: Optional ID for user that owns the resource.
        :param project: Optional ID for project that owns the resource.
        :param source: Optional source filter.
        :param start_timestamp: Optional modified timestamp start range.
        :param start_timestamp_op: Optional start time operator, like gt, ge.
        :param end_timestamp: Optional modified timestamp end range.
        :param end_timestamp_op: Optional end time operator, like lt, le.
        :param metaquery: Optional dict with metadata to match on.
        :param resource: Optional resource filter.
        """
        q = {}
        if user is not None:
            q['user_id'] = user
        if project is not None:
            q['project_id'] = project
        if source is not None:
            q['source'] = source
        if resource is not None:
            q['resource_id'] = resource
        # Add resource_ prefix so it matches the field in the db
        q.update(dict(('resource_' + k, v)
                      for (k, v) in metaquery.iteritems()))

        # FIXME(dhellmann): This may not perform very well,
        # but doing any better will require changing the database
        # schema and that will need more thought than I have time
        # to put into it today.
        if start_timestamp or end_timestamp:
            # Look for resources matching the above criteria and with
            # samples in the time range we care about, then change the
            # resource query to return just those resources by id.
            ts_range = make_timestamp_range(start_timestamp, end_timestamp,
                                            start_timestamp_op,
                                            end_timestamp_op)
            if ts_range:
                q['timestamp'] = ts_range

        # FIXME(jd): We should use self.db.meter.group() and not use the
        # resource collection, but that's not supported by MIM, so it's not
        # easily testable yet. Since it was bugged before anyway, it's still
        # better for now.
        resource_ids = self.db.meter.find(q).distinct('resource_id')
        q = {'_id': {'$in': resource_ids}}
        for resource in self.db.resource.find(q):
            yield models.Resource(
                resource_id=resource['_id'],
                project_id=resource['project_id'],
                source=resource['source'],
                user_id=resource['user_id'],
                metadata=resource['metadata'],
                meter=[
                    models.ResourceMeter(
                        counter_name=meter['counter_name'],
                        counter_type=meter['counter_type'],
                        counter_unit=meter.get('counter_unit', ''),
                    )
                    for meter in resource['meter']
                ],
            )

    def get_meters(self, user=None, project=None, resource=None, source=None,
                   metaquery={}):
        """Return an iterable of models.Meter instances

        :param user: Optional ID for user that owns the resource.
        :param project: Optional ID for project that owns the resource.
        :param resource: Optional resource filter.
        :param source: Optional source filter.
        :param metaquery: Optional dict with metadata to match on.
        """
        q = {}
        if user is not None:
            q['user_id'] = user
        if project is not None:
            q['project_id'] = project
        if resource is not None:
            q['_id'] = resource
        if source is not None:
            q['source'] = source
        q.update(metaquery)

        for r in self.db.resource.find(q):
            for r_meter in r['meter']:
                yield models.Meter(
                    name=r_meter['counter_name'],
                    type=r_meter['counter_type'],
                    # Return empty string if 'counter_unit' is not valid for
                    # backward compatibility.
                    unit=r_meter.get('counter_unit', ''),
                    resource_id=r['_id'],
                    project_id=r['project_id'],
                    source=r['source'],
                    user_id=r['user_id'],
                )

    def get_samples(self, sample_filter, limit=None):
        """Return an iterable of model.Sample instances.

        :param sample_filter: Filter.
        :param limit: Maximum number of results to return.
        """
        if limit == 0:
            return
        q = make_query_from_filter(sample_filter, require_meter=False)
        if limit:
            samples = self.db.meter.find(
                q, limit=limit, sort=[("timestamp", pymongo.DESCENDING)])
        else:
            samples = self.db.meter.find(
                q, sort=[("timestamp", pymongo.DESCENDING)])

        for s in samples:
            # Remove the ObjectId generated by the database when
            # the sample was inserted. It is an implementation
            # detail that should not leak outside of the driver.
            del s['_id']
            # Backward compatibility for samples without units
            s['counter_unit'] = s.get('counter_unit', '')
            yield models.Sample(**s)

    def get_meter_statistics(self, sample_filter, period=None):
        """Return an iterable of models.Statistics instance containing meter
        statistics described by the query parameters.

        The filter must have a meter value set.

        """
        q = make_query_from_filter(sample_filter)

        if period:
            if sample_filter.start:
                period_start = sample_filter.start
            else:
                period_start = self.db.meter.find(
                    limit=1, sort=[('timestamp',
                                    pymongo.ASCENDING)])[0]['timestamp']
            period_start = int(period_start.strftime('%s'))
            map_stats = self.MAP_STATS_PERIOD % (period, period_start)
        else:
            map_stats = self.MAP_STATS

        results = self.db.meter.map_reduce(
            map_stats,
            self.REDUCE_STATS,
            {'inline': 1},
            finalize=self.FINALIZE_STATS,
            query=q,
        )

        return sorted((models.Statistics(**(r['value']))
                       for r in results['results']),
                      key=operator.attrgetter('period_start'))

    def get_alarms(self, name=None, user=None,
                   project=None, enabled=True, alarm_id=None):
        """Yields a lists of alarms that match filters
        """
        q = {}
        if user is not None:
            q['user_id'] = user
        if project is not None:
            q['project_id'] = project
        if name is not None:
            q['name'] = name
        if enabled is not None:
            q['enabled'] = enabled
        if alarm_id is not None:
            q['alarm_id'] = alarm_id

        for alarm in self.db.alarm.find(q):
            a = {}
            a.update(alarm)
            del a['_id']
            yield models.Alarm(**a)

    def update_alarm(self, alarm):
        """update alarm
        """
        if alarm.alarm_id is None:
            # This is an insert, generate an id
            alarm.alarm_id = str(uuid.uuid1())
        data = alarm.as_dict()
        self.db.alarm.update(
            {'alarm_id': alarm.alarm_id},
            {'$set': data},
            upsert=True)

        stored_alarm = self.db.alarm.find({'alarm_id': alarm.alarm_id})[0]
        del stored_alarm['_id']
        return models.Alarm(**stored_alarm)

    def delete_alarm(self, alarm_id):
        """Delete a alarm
        """
        self.db.alarm.remove({'alarm_id': alarm_id})

    @staticmethod
    def record_events(events):
        """Write the events.

        :param events: a list of model.Event objects.
        """
        raise NotImplementedError('Events not implemented.')

    @staticmethod
    def get_events(event_filter):
        """Return an iterable of model.Event objects.

        :param event_filter: EventFilter instance
        """
        raise NotImplementedError('Events not implemented.')
