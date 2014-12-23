#
# Copyright 2012-2013 eNovance <licensing@enovance.com>
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

from oslo.config import cfg
import oslo.messaging
from stevedore import extension

from ceilometer import coordination
from ceilometer.event import endpoint as event_endpoint
from ceilometer.i18n import _
from ceilometer import messaging
from ceilometer.openstack.common import context
from ceilometer.openstack.common import log
from ceilometer.openstack.common import service as os_service
from ceilometer import pipeline


LOG = log.getLogger(__name__)


OPTS = [
    cfg.BoolOpt('ack_on_event_error',
                default=True,
                deprecated_group='collector',
                help='Acknowledge message when event persistence fails.'),
    cfg.BoolOpt('store_events',
                deprecated_group='collector',
                default=False,
                help='Save event details.'),
    cfg.BoolOpt('workload_partitioning',
                default=False,
                help='Enable workload partitioning, allowing multiple '
                     'notification agents to be run simultaneously.'),
    cfg.MultiStrOpt('messaging_urls',
                    default=[],
                    help="Messaging URLs to listen for notifications. "
                         "Example: transport://user:pass@host1:port"
                         "[,hostN:portN]/virtual_host "
                         "(DEFAULT/transport_url is used if empty)"),
]

cfg.CONF.register_opts(OPTS, group="notification")


class NotificationService(os_service.Service):
    """Notification service.

    When running multiple agents, additional queuing sequence is required for
    inter process communication. Each agent has two listeners: one to listen
    to the main OpenStack queue and another listener(and notifier) for IPC to
    divide pipeline sink endpoints. Coordination should be enabled to have
    proper active/active HA.
    """

    NOTIFICATION_NAMESPACE = 'ceilometer.notification'
    NOTIFICATION_IPC = 'ceilometer-pipe'

    @classmethod
    def _get_notifications_manager(cls, transporter):
        return extension.ExtensionManager(
            namespace=cls.NOTIFICATION_NAMESPACE,
            invoke_on_load=True,
            invoke_args=(transporter, )
        )

    def start(self):
        super(NotificationService, self).start()
        self.pipeline_manager = pipeline.setup_pipeline()

        transport = messaging.get_transport()
        self.partition_coordinator = coordination.PartitionCoordinator()
        self.partition_coordinator.start()

        if cfg.CONF.notification.workload_partitioning:
            transporter = []
            for pipe in self.pipeline_manager.pipelines:
                transporter.append(oslo.messaging.Notifier(
                    transport,
                    driver=cfg.CONF.publisher_notifier.metering_driver,
                    publisher_id='ceilometer.notification',
                    topic='%s-%s' % (self.NOTIFICATION_IPC, pipe.name)))

            self.ctxt = context.get_admin_context()
            self.group_id = self.NOTIFICATION_NAMESPACE
        else:
            # FIXME(sileht): endpoint use notification_topics option
            # and it should not because this is oslo.messaging option
            # not a ceilometer, until we have a something to get
            # the notification_topics in an other way
            # we must create a transport to ensure the option have
            # beeen registered by oslo.messaging
            messaging.get_notifier(transport, '')
            transporter = self.pipeline_manager
            self.group_id = None

        self.listeners = self.pipeline_listeners = []
        self._configure_main_queue_listeners(transporter)

        if cfg.CONF.notification.workload_partitioning:
            self.partition_coordinator.join_group(self.group_id)
            self._configure_pipeline_listeners()
            self.partition_coordinator.watch_group(self.group_id,
                                                   self._refresh_agent)

            self.tg.add_timer(cfg.CONF.coordination.heartbeat,
                              self.partition_coordinator.heartbeat)
            self.tg.add_timer(cfg.CONF.coordination.check_watchers,
                              self.partition_coordinator.run_watchers)

        # Add a dummy thread to have wait() working
        self.tg.add_timer(604800, lambda: None)

    def _configure_main_queue_listeners(self, transporter):
        self.notification_manager = self._get_notifications_manager(
            transporter)
        if not list(self.notification_manager):
            LOG.warning(_('Failed to load any notification handlers for %s'),
                        self.NOTIFICATION_NAMESPACE)

        ack_on_error = cfg.CONF.notification.ack_on_event_error

        endpoints = []
        if cfg.CONF.notification.store_events:
            endpoints = [event_endpoint.EventsNotificationEndpoint()]

        targets = []
        for ext in self.notification_manager:
            handler = ext.obj
            LOG.debug(_('Event types from %(name)s: %(type)s'
                        ' (ack_on_error=%(error)s)') %
                      {'name': ext.name,
                       'type': ', '.join(handler.event_types),
                       'error': ack_on_error})
            # NOTE(gordc): this could be a set check but oslo.messaging issue
            # https://bugs.launchpad.net/oslo.messaging/+bug/1398511
            # This ensures we don't create multiple duplicate consumers.
            for new_tar in handler.get_targets(cfg.CONF):
                if new_tar not in targets:
                    targets.append(new_tar)
            endpoints.append(handler)

        urls = cfg.CONF.notification.messaging_urls or [None]
        for url in urls:
            transport = messaging.get_transport(url)
            listener = messaging.get_notification_listener(
                transport, targets, endpoints)
            listener.start()
            self.listeners.append(listener)

    @staticmethod
    def _kill_listeners(listeners):
        # NOTE(gordc): correct usage of oslo.messaging listener is to stop(),
        # which stops new messages, and wait(), which processes remaining
        # messages and closes connection
        for listener in listeners:
            listener.stop()
            listener.wait()

    def _refresh_agent(self, event):
        self._kill_listeners(self.pipeline_listeners)
        self._configure_pipeline_listeners()

    def _configure_pipeline_listeners(self):
        if cfg.CONF.notification.workload_partitioning:
            partitioned = self.partition_coordinator.extract_my_subset(
                self.group_id, self.pipeline_manager.pipelines)
            transport = messaging.get_transport()
            for pipe in partitioned:
                LOG.debug(_('Pipeline endpoint: %s'), pipe.name)
                listener = messaging.get_notification_listener(
                    transport,
                    [oslo.messaging.Target(
                        topic='%s-%s' % (self.NOTIFICATION_IPC, pipe.name))],
                    [pipeline.PipelineEndpoint(self.ctxt, pipe)])
                listener.start()
                self.pipeline_listeners.append(listener)

    def stop(self):
        self.partition_coordinator.leave_group(self.group_id)
        self._kill_listeners(self.listeners + self.pipeline_listeners)
        super(NotificationService, self).stop()
