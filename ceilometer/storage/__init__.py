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
"""Storage backend management
"""

from oslo_config import cfg
from oslo_db import options as db_options
from oslo_log import log
import retrying
import six.moves.urllib.parse as urlparse
from stevedore import driver

from ceilometer import utils


LOG = log.getLogger(__name__)


OPTS = [
    cfg.IntOpt('metering_time_to_live',
               default=-1,
               help="Number of seconds that samples are kept "
               "in the database for (<= 0 means forever).",
               deprecated_opts=[cfg.DeprecatedOpt('time_to_live',
                                                  'database')]),
    cfg.IntOpt('event_time_to_live',
               default=-1,
               help=("Number of seconds that events are kept "
                     "in the database for (<= 0 means forever).")),
    cfg.StrOpt('metering_connection',
               secret=True,
               help='The connection string used to connect to the metering '
               'database. (if unset, connection is used)'),
    cfg.StrOpt('event_connection',
               secret=True,
               help='The connection string used to connect to the event '
               'database. (if unset, connection is used)'),
]

cfg.CONF.register_opts(OPTS, group='database')

CLI_OPTS = [
    cfg.BoolOpt('sql-expire-samples-only',
                default=False,
                help="Indicates if expirer expires only samples. If set true,"
                     " expired samples will be deleted, but residual"
                     " resource and meter definition data will remain.",
                ),
]

cfg.CONF.register_cli_opts(CLI_OPTS)

db_options.set_defaults(cfg.CONF)


class StorageUnknownWriteError(Exception):
    """Error raised when an unknown error occurs while recording."""


class StorageBadVersion(Exception):
    """Error raised when the storage backend version is not good enough."""


class StorageBadAggregate(Exception):
    """Error raised when an aggregate is unacceptable to storage backend."""
    code = 400


def get_connection_from_config(conf, purpose='metering'):
    retries = conf.database.max_retries

    # Convert retry_interval secs to msecs for retry decorator
    @retrying.retry(wait_fixed=conf.database.retry_interval * 1000,
                    stop_max_attempt_number=retries if retries >= 0 else None)
    def _inner():
        namespace = 'ceilometer.%s.storage' % purpose
        url = (getattr(conf.database, '%s_connection' % purpose) or
               conf.database.connection)
        return get_connection(url, namespace)

    return _inner()


def get_connection(url, namespace):
    """Return an open connection to the database."""
    connection_scheme = urlparse.urlparse(url).scheme
    # SqlAlchemy connections specify may specify a 'dialect' or
    # 'dialect+driver'. Handle the case where driver is specified.
    engine_name = connection_scheme.split('+')[0]
    # NOTE: translation not applied bug #1446983
    LOG.debug('looking for %(name)r driver in %(namespace)r',
              {'name': engine_name, 'namespace': namespace})
    mgr = driver.DriverManager(namespace, engine_name)
    return mgr.driver(url)


class SampleFilter(object):
    """Holds the properties for building a query from a meter/sample filter.

    :param user: The sample owner.
    :param project: The sample project.
    :param start_timestamp: Earliest time point in the request.
    :param start_timestamp_op: Earliest timestamp operation in the request.
    :param end_timestamp: Latest time point in the request.
    :param end_timestamp_op: Latest timestamp operation in the request.
    :param resource: Optional filter for resource id.
    :param meter: Optional filter for meter type using the meter name.
    :param source: Optional source filter.
    :param message_id: Optional sample_id filter.
    :param metaquery: Optional filter on the metadata
    """
    def __init__(self, user=None, project=None,
                 start_timestamp=None, start_timestamp_op=None,
                 end_timestamp=None, end_timestamp_op=None,
                 resource=None, meter=None,
                 source=None, message_id=None,
                 metaquery=None):
        self.user = user
        self.project = project
        self.start_timestamp = utils.sanitize_timestamp(start_timestamp)
        self.start_timestamp_op = start_timestamp_op
        self.end_timestamp = utils.sanitize_timestamp(end_timestamp)
        self.end_timestamp_op = end_timestamp_op
        self.resource = resource
        self.meter = meter
        self.source = source
        self.metaquery = metaquery or {}
        self.message_id = message_id

    def __repr__(self):
        return ("<SampleFilter(user: %s,"
                " project: %s,"
                " start_timestamp: %s,"
                " start_timestamp_op: %s,"
                " end_timestamp: %s,"
                " end_timestamp_op: %s,"
                " resource: %s,"
                " meter: %s,"
                " source: %s,"
                " metaquery: %s,"
                " message_id: %s)>" %
                (self.user,
                 self.project,
                 self.start_timestamp,
                 self.start_timestamp_op,
                 self.end_timestamp,
                 self.end_timestamp_op,
                 self.resource,
                 self.meter,
                 self.source,
                 self.metaquery,
                 self.message_id))
