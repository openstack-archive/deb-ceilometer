#
# Copyright 2013 eNovance
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
"""Publish a sample using an UDP mechanism
"""

import socket

import msgpack
from oslo_config import cfg
from oslo_log import log
from oslo_utils import netutils

import ceilometer
from ceilometer.i18n import _
from ceilometer import publisher
from ceilometer.publisher import utils

cfg.CONF.import_opt('udp_port', 'ceilometer.collector',
                    group='collector')

LOG = log.getLogger(__name__)


class UDPPublisher(publisher.PublisherBase):
    def __init__(self, parsed_url):
        self.host, self.port = netutils.parse_host_port(
            parsed_url.netloc,
            default_port=cfg.CONF.collector.udp_port)
        if netutils.is_valid_ipv6(self.host):
            addr_family = socket.AF_INET6
        else:
            addr_family = socket.AF_INET
        self.socket = socket.socket(addr_family,
                                    socket.SOCK_DGRAM)

    def publish_samples(self, context, samples):
        """Send a metering message for publishing

        :param context: Execution context from the service or RPC call
        :param samples: Samples from pipeline after transformation
        """

        for sample in samples:
            msg = utils.meter_message_from_counter(
                sample, cfg.CONF.publisher.telemetry_secret)
            host = self.host
            port = self.port
            LOG.debug("Publishing sample %(msg)s over UDP to "
                      "%(host)s:%(port)d", {'msg': msg, 'host': host,
                                            'port': port})
            try:
                self.socket.sendto(msgpack.dumps(msg),
                                   (self.host, self.port))
            except Exception as e:
                LOG.warning(_("Unable to send sample over UDP"))
                LOG.exception(e)

    def publish_events(self, context, events):
        """Send an event message for publishing

        :param context: Execution context from the service or RPC call
        :param events: events from pipeline after transformation
        """
        raise ceilometer.NotImplementedError
