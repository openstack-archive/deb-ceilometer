# -*- encoding: utf-8 -*-
#
# Copyright © 2012-2013 eNovance <licensing@enovance.com>
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

import msgpack
from oslo.config import cfg
import socket
from stevedore import extension

from ceilometer.publisher import rpc as publisher_rpc
from ceilometer.service import prepare_service
from ceilometer.openstack.common import context
from ceilometer.openstack.common.gettextutils import _
from ceilometer.openstack.common import log
from ceilometer.openstack.common import service as os_service
from ceilometer.openstack.common.rpc import dispatcher as rpc_dispatcher
from ceilometer.openstack.common.rpc import service as rpc_service


from ceilometer.openstack.common import timeutils
from ceilometer import pipeline
from ceilometer import storage
from ceilometer.storage import models
from ceilometer import transformer

OPTS = [
    cfg.StrOpt('udp_address',
               default='0.0.0.0',
               help='address to bind the UDP socket to'
               'disabled if set to an empty string'),
    cfg.IntOpt('udp_port',
               default=4952,
               help='port to bind the UDP socket to'),
    cfg.BoolOpt('ack_on_event_error',
                default=True,
                help='Acknowledge message when event persistence fails'),
    cfg.BoolOpt('store_events',
                default=False,
                help='Save event details'),
]

cfg.CONF.register_opts(OPTS, group="collector")

LOG = log.getLogger(__name__)


class UDPCollectorService(os_service.Service):
    """UDP listener for the collector service."""

    def __init__(self):
        super(UDPCollectorService, self).__init__()
        self.storage_conn = storage.get_connection(cfg.CONF)

    def start(self):
        """Bind the UDP socket and handle incoming data."""
        super(UDPCollectorService, self).start()

        udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        udp.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        udp.bind((cfg.CONF.collector.udp_address,
                  cfg.CONF.collector.udp_port))

        self.running = True
        while self.running:
            # NOTE(jd) Arbitrary limit of 64K because that ought to be
            # enough for anybody.
            data, source = udp.recvfrom(64 * 1024)
            try:
                counter = msgpack.loads(data)
            except Exception:
                LOG.warn(_("UDP: Cannot decode data sent by %s"), str(source))
            else:
                try:
                    counter['counter_name'] = counter['name']
                    counter['counter_volume'] = counter['volume']
                    counter['counter_unit'] = counter['unit']
                    counter['counter_type'] = counter['type']
                    LOG.debug("UDP: Storing %s", str(counter))
                    self.storage_conn.record_metering_data(counter)
                except Exception as err:
                    LOG.debug(_("UDP: Unable to store meter"))
                    LOG.exception(err)

    def stop(self):
        self.running = False
        super(UDPCollectorService, self).stop()


def udp_collector():
    prepare_service()
    os_service.launch(UDPCollectorService()).wait()


class CollectorService(rpc_service.Service):

    COLLECTOR_NAMESPACE = 'ceilometer.collector'

    def __init__(self, host, topic, manager=None):
        super(CollectorService, self).__init__(host, topic, manager)
        self.storage_conn = storage.get_connection(cfg.CONF)

    def start(self):
        super(CollectorService, self).start()
        # Add a dummy thread to have wait() working
        self.tg.add_timer(604800, lambda: None)

    def initialize_service_hook(self, service):
        '''Consumers must be declared before consume_thread start.'''
        LOG.debug('initialize_service_hooks')
        self.pipeline_manager = pipeline.setup_pipeline(
            transformer.TransformerExtensionManager(
                'ceilometer.transformer',
            ),
        )

        LOG.debug('loading notification handlers from %s',
                  self.COLLECTOR_NAMESPACE)
        self.notification_manager = \
            extension.ExtensionManager(
                namespace=self.COLLECTOR_NAMESPACE,
                invoke_on_load=True,
            )

        if not list(self.notification_manager):
            LOG.warning('Failed to load any notification handlers for %s',
                        self.COLLECTOR_NAMESPACE)
        self.notification_manager.map(self._setup_subscription)

        # Set ourselves up as a separate worker for the metering data,
        # since the default for service is to use create_consumer().
        self.conn.create_worker(
            cfg.CONF.publisher_rpc.metering_topic,
            rpc_dispatcher.RpcDispatcher([self]),
            'ceilometer.collector.' + cfg.CONF.publisher_rpc.metering_topic,
        )

    def _setup_subscription(self, ext, *args, **kwds):
        handler = ext.obj
        ack_on_error = cfg.CONF.collector.ack_on_event_error
        LOG.debug('Event types from %s: %s (ack_on_error=%s)',
                  ext.name, ', '.join(handler.get_event_types()),
                  ack_on_error)

        for exchange_topic in handler.get_exchange_topics(cfg.CONF):
            for topic in exchange_topic.topics:
                try:
                    self.conn.join_consumer_pool(
                        callback=self.process_notification,
                        pool_name='ceilometer.notifications',
                        topic=topic,
                        exchange_name=exchange_topic.exchange,
                        ack_on_error=ack_on_error)
                except Exception:
                    LOG.exception('Could not join consumer pool %s/%s' %
                                  (topic, exchange_topic.exchange))

    def process_notification(self, notification):
        """Make a notification processed by an handler."""
        LOG.debug('notification %r', notification.get('event_type'))
        self.notification_manager.map(self._process_notification_for_ext,
                                      notification=notification)

        if cfg.CONF.collector.store_events:
            self._message_to_event(notification)

    @staticmethod
    def _extract_when(body):
        """Extract the generated datetime from the notification.
        """
        when = body.get('timestamp', body.get('_context_timestamp'))
        if when:
            return timeutils.normalize_time(timeutils.parse_isotime(when))

        return timeutils.utcnow()

    def _message_to_event(self, body):
        """Convert message to Ceilometer Event.

        NOTE: this is currently based on the Nova notification format.
        We will need to make this driver-based to support other formats.

        NOTE: the rpc layer currently rips out the notification
        delivery_info, which is critical to determining the
        source of the notification. This will have to get added back later.
        """
        event_name = body['event_type']
        when = self._extract_when(body)

        LOG.debug('Saving event "%s"', event_name)

        message_id = body.get('message_id')

        # TODO(sandy) - check we have not already saved this notification.
        #               (possible on retries) Use message_id to spot dups.
        publisher = body.get('publisher_id')
        request_id = body.get('_context_request_id')
        tenant_id = body.get('_context_tenant')

        text = models.Trait.TEXT_TYPE
        all_traits = [models.Trait('message_id', text, message_id),
                      models.Trait('service', text, publisher),
                      models.Trait('request_id', text, request_id),
                      models.Trait('tenant_id', text, tenant_id),
                      ]
        # Only store non-None value traits ...
        traits = [trait for trait in all_traits if trait.value is not None]

        event = models.Event(event_name, when, traits)
        try:
            self.storage_conn.record_events([event, ])
        except Exception as err:
            LOG.exception(_("Unable to store events: %s"), err)
            # By re-raising we avoid ack()'ing the message.
            raise

    def _process_notification_for_ext(self, ext, notification):
        handler = ext.obj
        if notification['event_type'] in handler.get_event_types():
            ctxt = context.get_admin_context()
            with self.pipeline_manager.publisher(ctxt,
                                                 cfg.CONF.counter_source) as p:
                # FIXME(dhellmann): Spawn green thread?
                p(list(handler.process_notification(notification)))

    def record_metering_data(self, context, data):
        """This method is triggered when metering data is
        cast from an agent.
        """
        # We may have receive only one counter on the wire
        if not isinstance(data, list):
            data = [data]

        for meter in data:
            LOG.info('metering data %s for %s @ %s: %s',
                     meter['counter_name'],
                     meter['resource_id'],
                     meter.get('timestamp', 'NO TIMESTAMP'),
                     meter['counter_volume'])
            if publisher_rpc.verify_signature(
                    meter,
                    cfg.CONF.publisher_rpc.metering_secret):
                try:
                    # Convert the timestamp to a datetime instance.
                    # Storage engines are responsible for converting
                    # that value to something they can store.
                    if meter.get('timestamp'):
                        ts = timeutils.parse_isotime(meter['timestamp'])
                        meter['timestamp'] = timeutils.normalize_time(ts)
                    self.storage_conn.record_metering_data(meter)
                except Exception as err:
                    LOG.error('Failed to record metering data: %s', err)
                    LOG.exception(err)
            else:
                LOG.warning(
                    'message signature invalid, discarding message: %r',
                    meter)


def collector():
    prepare_service()
    os_service.launch(CollectorService(cfg.CONF.host,
                                       'ceilometer.collector')).wait()
