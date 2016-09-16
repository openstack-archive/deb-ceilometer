#
# Copyright 2015 Red Hat
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
from oslo_config import cfg
from oslo_log import log
import six.moves.urllib.parse as urlparse
from stevedore import driver
import stevedore.exception

from ceilometer.i18n import _LE
from ceilometer import publisher
from ceilometer.publisher import utils

LOG = log.getLogger(__name__)


class DirectPublisher(publisher.PublisherBase):
    """A publisher that allows saving directly from the pipeline.

    Samples are saved to a configured dispatcher. This is useful
    where it is desirable to limit the number of external services that
    are required.

    By default, the database dispatcher is used to select another one we
    can use direct://?dispatcher=gnocchi, direct://?dispatcher=http,
    direct://?dispatcher=log, ...
    """
    def __init__(self, parsed_url):
        super(DirectPublisher, self).__init__(parsed_url)
        options = urlparse.parse_qs(parsed_url.query)
        self.dispatcher_name = options.get('dispatcher', ['database'])[-1]
        self._sample_dispatcher = None
        self._event_dispatcher = None

        try:
            self.sample_driver = driver.DriverManager(
                'ceilometer.dispatcher.meter', self.dispatcher_name).driver
        except stevedore.exception.NoMatches:
            self.sample_driver = None

        try:
            self.event_driver = driver.DriverManager(
                'ceilometer.dispatcher.event', self.dispatcher_name).driver
        except stevedore.exception.NoMatches:
            self.event_driver = None

    def get_sample_dispatcher(self):
        if not self._sample_dispatcher:
            self._sample_dispatcher = self.sample_driver(cfg.CONF)
        return self._sample_dispatcher

    def get_event_dispatcher(self):
        if not self._event_dispatcher:
            if self.event_driver != self.sample_driver:
                self._event_dispatcher = self.event_driver(cfg.CONF)
            else:
                self._event_dispatcher = self.get_sample_dispatcher()
        return self._event_dispatcher

    def publish_samples(self, samples):
        if not self.sample_driver:
            LOG.error(_LE("Can't publish samples to a non-existing dispatcher "
                          "'%s'"), self.dispatcher_name)
            return

        if not isinstance(samples, list):
            samples = [samples]
        self.get_sample_dispatcher().record_metering_data([
            utils.meter_message_from_counter(
                sample, cfg.CONF.publisher.telemetry_secret)
            for sample in samples
        ])

    def publish_events(self, events):
        if not self.event_driver:
            LOG.error(_LE("Can't publish events to a non-existing dispatcher"
                          "'%s'"), self.dispatcher_name)
            return

        if not isinstance(events, list):
            events = [events]
        self.get_event_dispatcher().record_events([
            utils.message_from_event(
                event, cfg.CONF.publisher.telemetry_secret)
            for event in events])
