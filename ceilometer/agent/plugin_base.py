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
"""Base class for plugins.
"""

import abc
import collections

from oslo_context import context
from oslo_log import log
import oslo_messaging
import six
from stevedore import extension

from ceilometer import messaging

LOG = log.getLogger(__name__)

ExchangeTopics = collections.namedtuple('ExchangeTopics',
                                        ['exchange', 'topics'])


class PluginBase(object):
    """Base class for all plugins."""


@six.add_metaclass(abc.ABCMeta)
class NotificationBase(PluginBase):
    """Base class for plugins that support the notification API."""
    def __init__(self, manager):
        super(NotificationBase, self).__init__()
        # NOTE(gordc): this is filter rule used by oslo.messaging to dispatch
        # messages to an endpoint.
        if self.event_types:
            self.filter_rule = oslo_messaging.NotificationFilter(
                event_type='|'.join(self.event_types))
        self.manager = manager

    @abc.abstractproperty
    def event_types(self):
        """Return a sequence of strings.

        Strings are defining the event types to be given to this plugin.
        """

    @abc.abstractmethod
    def get_targets(self, conf):
        """Return a sequence of oslo.messaging.Target.

        Sequence is defining the exchange and topics to be connected for this
        plugin.
        :param conf: Configuration.
        """

    @abc.abstractmethod
    def process_notification(self, message):
        """Return a sequence of Counter instances for the given message.

        :param message: Message to process.
        """

    def info(self, ctxt, publisher_id, event_type, payload, metadata):
        """RPC endpoint for notification messages at info level

        When another service sends a notification over the message
        bus, this method receives it.

        :param ctxt: oslo.messaging context
        :param publisher_id: publisher of the notification
        :param event_type: type of notification
        :param payload: notification payload
        :param metadata: metadata about the notification

        """
        notification = messaging.convert_to_old_notification_format(
            'info', ctxt, publisher_id, event_type, payload, metadata)
        self.to_samples_and_publish(context.get_admin_context(), notification)

    def sample(self, ctxt, publisher_id, event_type, payload, metadata):
        """RPC endpoint for notification messages at sample level

        When another service sends a notification over the message
        bus at sample priority, this method receives it.

        :param ctxt: oslo.messaging context
        :param publisher_id: publisher of the notification
        :param event_type: type of notification
        :param payload: notification payload
        :param metadata: metadata about the notification

        """
        notification = messaging.convert_to_old_notification_format(
            'sample', ctxt, publisher_id, event_type, payload, metadata)
        self.to_samples_and_publish(context.get_admin_context(), notification)

    def to_samples_and_publish(self, context, notification):
        """Return samples produced by *process_notification*.

        Samples produced for the given notification.
        :param context: Execution context from the service or RPC call
        :param notification: The notification to process.
        """
        with self.manager.publisher(context) as p:
            p(list(self.process_notification(notification)))


class NonMetricNotificationBase(object):
    """Use to mark non-measurement meters

    There are a number of historical non-measurement meters that should really
    be captured as events. This common base allows us to disable these invalid
    meters.
    """
    pass


class ExtensionLoadError(Exception):
    """Error of loading pollster plugin.

    PollsterBase provides a hook, setup_environment, called in pollster loading
    to setup required HW/SW dependency. Any exception from it would be
    propagated as ExtensionLoadError, then skip loading this pollster.
    """
    pass


class PollsterPermanentError(Exception):
    """Permanent error when polling.

    When unrecoverable error happened in polling, pollster can raise this
    exception with failed resource to prevent itself from polling any more.
    Resource is one of parameter resources from get_samples that cause polling
    error.
    """

    def __init__(self, resources):
        self.fail_res_list = resources


@six.add_metaclass(abc.ABCMeta)
class PollsterBase(PluginBase):
    """Base class for plugins that support the polling API."""

    def setup_environment(self):
        """Setup required environment for pollster.

        Each subclass could overwrite it for specific usage. Any exception
        raised in this function would prevent pollster being loaded.
        """
        pass

    def __init__(self):
        super(PollsterBase, self).__init__()
        try:
            self.setup_environment()
        except Exception as err:
            raise ExtensionLoadError(err)

    @abc.abstractproperty
    def default_discovery(self):
        """Default discovery to use for this pollster.

        There are three ways a pollster can get a list of resources to poll,
        listed here in ascending order of precedence:
        1. from the per-agent discovery,
        2. from the per-pollster discovery (defined here)
        3. from the per-pipeline configured discovery and/or per-pipeline
        configured static resources.

        If a pollster should only get resources from #1 or #3, this property
        should be set to None.
        """

    @abc.abstractmethod
    def get_samples(self, manager, cache, resources):
        """Return a sequence of Counter instances from polling the resources.

        :param manager: The service manager class invoking the plugin.
        :param cache: A dictionary to allow pollsters to pass data
                      between themselves when recomputing it would be
                      expensive (e.g., asking another service for a
                      list of objects).
        :param resources: A list of resources the pollster will get data
                          from. It's up to the specific pollster to decide
                          how to use it. It is usually supplied by a discovery,
                          see ``default_discovery`` for more information.

        """

    @classmethod
    def build_pollsters(cls):
        """Return a list of tuple (name, pollster).

        The name is the meter name which the pollster would return, the
        pollster is a pollster object instance. The pollster which implements
        this method should be registered in the namespace of
        ceilometer.builder.xxx instead of ceilometer.poll.xxx.
        """
        return []

    @classmethod
    def get_pollsters_extensions(cls):
        """Return a list of stevedore extensions.

        The returned stevedore extensions wrap the pollster object instances
        returned by build_pollsters.
        """
        extensions = []
        try:
            for name, pollster in cls.build_pollsters():
                ext = extension.Extension(name, None, cls, pollster)
                extensions.append(ext)
        except Exception as err:
            raise ExtensionLoadError(err)
        return extensions


@six.add_metaclass(abc.ABCMeta)
class DiscoveryBase(object):
    KEYSTONE_REQUIRED_FOR_SERVICE = None
    """Service type required in keystone catalog to works"""

    @abc.abstractmethod
    def discover(self, manager, param=None):
        """Discover resources to monitor.

        The most fine-grained discovery should be preferred, so the work is
        the most evenly distributed among multiple agents (if they exist).

        For example:
        if the pollster can separately poll individual resources, it should
        have its own discovery implementation to discover those resources. If
        it can only poll per-tenant, then the `TenantDiscovery` should be
        used. If even that is not possible, use `EndpointDiscovery` (see
        their respective docstrings).

        :param manager: The service manager class invoking the plugin.
        :param param: an optional parameter to guide the discovery
        """

    @property
    def group_id(self):
        """Return group id of this discovery.

        All running recoveries with the same group_id should return the same
        set of resources at a given point in time. By default, a discovery is
        put into a global group, meaning that all discoveries of its type
        running anywhere in the cloud, return the same set of resources.

        This property can be overridden to provide correct grouping of
        localized discoveries. For example, compute discovery is localized
        to a host, which is reflected in its group_id.

        A None value signifies that this discovery does not want to be part
        of workload partitioning at all.
        """
        return 'global'
