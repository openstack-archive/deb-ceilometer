#
# Copyright 2013 IBM Corp
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

from oslo_log import log
from oslo_utils import timeutils

from ceilometer import dispatcher
from ceilometer.event.storage import models
from ceilometer.i18n import _LE
from ceilometer import storage

LOG = log.getLogger(__name__)


class DatabaseDispatcher(dispatcher.Base):
    """Dispatcher class for recording metering data into database.

    The dispatcher class which records each meter into a database configured
    in ceilometer configuration file.

    To enable this dispatcher, the following section needs to be present in
    ceilometer.conf file

    [DEFAULT]
    meter_dispatchers = database
    event_dispatchers = database
    """

    @property
    def conn(self):
        if not hasattr(self, "_conn"):
            self._conn = storage.get_connection_from_config(
                self.conf, self.CONNECTION_TYPE)
        return self._conn


class MeterDatabaseDispatcher(dispatcher.MeterDispatcherBase,
                              DatabaseDispatcher):
    CONNECTION_TYPE = 'metering'

    def record_metering_data(self, data):
        # We may have receive only one counter on the wire
        if not data:
            return
        if not isinstance(data, list):
            data = [data]

        for meter in data:
            LOG.debug(
                'metering data %(counter_name)s '
                'for %(resource_id)s @ %(timestamp)s: %(counter_volume)s',
                {'counter_name': meter['counter_name'],
                 'resource_id': meter['resource_id'],
                 'timestamp': meter.get('timestamp', 'NO TIMESTAMP'),
                 'counter_volume': meter['counter_volume']})
            # Convert the timestamp to a datetime instance.
            # Storage engines are responsible for converting
            # that value to something they can store.
            if meter.get('timestamp'):
                ts = timeutils.parse_isotime(meter['timestamp'])
                meter['timestamp'] = timeutils.normalize_time(ts)
        try:
            self.conn.record_metering_data_batch(data)
        except Exception as err:
            LOG.error(_LE('Failed to record %(len)s: %(err)s.'),
                      {'len': len(data), 'err': err})
            raise


class EventDatabaseDispatcher(dispatcher.EventDispatcherBase,
                              DatabaseDispatcher):
    CONNECTION_TYPE = 'event'

    def record_events(self, events):
        if not isinstance(events, list):
            events = [events]

        event_list = []
        for ev in events:
            try:
                event_list.append(
                    models.Event(
                        message_id=ev['message_id'],
                        event_type=ev['event_type'],
                        generated=timeutils.normalize_time(
                            timeutils.parse_isotime(ev['generated'])),
                        traits=[models.Trait(
                                name, dtype,
                                models.Trait.convert_value(dtype, value))
                                for name, dtype, value in ev['traits']],
                        raw=ev.get('raw', {}))
                )
            except Exception:
                LOG.exception(_LE("Error processing event and it will be "
                                  "dropped: %s"), ev)
        self.conn.record_events(event_list)
