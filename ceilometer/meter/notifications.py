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

import fnmatch
import os
import six
import yaml

import jsonpath_rw
from oslo_config import cfg
from oslo_log import log
import oslo_messaging

from ceilometer.agent import plugin_base
from ceilometer.i18n import _LE
from ceilometer import sample

OPTS = [
    cfg.StrOpt('meter_definitions_cfg_file',
               default="meters.yaml",
               help="Configuration file for defining meter notifications."
               ),
]

cfg.CONF.register_opts(OPTS, group='meter')

LOG = log.getLogger(__name__)


class MeterDefinitionException(Exception):
    def __init__(self, message, definition_cfg):
        super(MeterDefinitionException, self).__init__(message)
        self.definition_cfg = definition_cfg

    def __str__(self):
        return '%s %s: %s' % (self.__class__.__name__,
                              self.definition_cfg, self.message)


class MeterDefinition(object):

    def __init__(self, definition_cfg):
        self.cfg = definition_cfg
        self._validate_type()

    def match_type(self, meter_name):
        try:
            event_type = self.cfg['event_type']
        except KeyError as err:
            raise MeterDefinitionException(
                _LE("Required field %s not specified") % err.args[0], self.cfg)

        if isinstance(event_type, six.string_types):
            event_type = [event_type]
        for t in event_type:
            if fnmatch.fnmatch(meter_name, t):
                return True

    def parse_fields(self, field, message):
        fval = self.cfg.get(field)
        if not fval:
            return
        if isinstance(fval, six.integer_types):
            return fval
        try:
            parts = jsonpath_rw.parse(fval)
        except Exception as e:
            raise MeterDefinitionException(
                _LE("Parse error in JSONPath specification "
                    "'%(jsonpath)s': %(err)s")
                % dict(jsonpath=parts, err=e), self.cfg)
        values = [match.value for match in parts.find(message)
                  if match.value is not None]
        if values:
            return values[0]

    def _validate_type(self):
        if self.cfg['type'] not in sample.TYPES:
            raise MeterDefinitionException(
                _LE("Invalid type %s specified") % self.cfg['type'], self.cfg)


def get_config_file():
    config_file = cfg.CONF.meter.meter_definitions_cfg_file
    if not os.path.exists(config_file):
        config_file = cfg.CONF.find_file(config_file)
    return config_file


def setup_meters_config():
    """Setup the meters definitions from yaml config file."""
    config_file = get_config_file()
    if config_file is not None:
        LOG.debug(_LE("Meter Definitions configuration file: %s"), config_file)

        with open(config_file) as cf:
            config = cf.read()

        try:
            meters_config = yaml.safe_load(config)
        except yaml.YAMLError as err:
            if hasattr(err, 'problem_mark'):
                mark = err.problem_mark
                errmsg = (_LE("Invalid YAML syntax in Meter Definitions file "
                          "%(file)s at line: %(line)s, column: %(column)s.")
                          % dict(file=config_file,
                                 line=mark.line + 1,
                                 column=mark.column + 1))
            else:
                errmsg = (_LE("YAML error reading Meter Definitions file "
                          "%(file)s")
                          % dict(file=config_file))
            LOG.error(errmsg)
            raise

    else:
        LOG.debug(_LE("No Meter Definitions configuration file found!"
                  " Using default config."))
        meters_config = []

    LOG.info(_LE("Meter Definitions: %s"), meters_config)

    return meters_config


def load_definitions(config_def):
    return [MeterDefinition(event_def)
            for event_def in reversed(config_def['metric'])]


class ProcessMeterNotifications(plugin_base.NotificationBase):

    event_types = None

    def __init__(self, manager):
        super(ProcessMeterNotifications, self).__init__(manager)
        self.definitions = load_definitions(setup_meters_config())

    def get_targets(self, conf):
        """Return a sequence of oslo_messaging.Target

        It is defining the exchange and topics to be connected for this plugin.
        :param conf: Configuration.
        #TODO(prad): This should be defined in the notification agent
        """
        targets = []
        exchanges = [
            conf.nova_control_exchange,
            conf.cinder_control_exchange,
            conf.glance_control_exchange,
            conf.neutron_control_exchange,
            conf.heat_control_exchange,
            conf.keystone_control_exchange,
            conf.sahara_control_exchange,
            conf.trove_control_exchange,
            conf.zaqar_control_exchange,
            conf.swift_control_exchange,
            conf.magnetodb_control_exchange,
            conf.ceilometer_control_exchange,
            ]

        for exchange in exchanges:
            targets.extend(oslo_messaging.Target(topic=topic,
                                                 exchange=exchange)
                           for topic in conf.notification_topics)
        return targets

    def process_notification(self, notification_body):
        for d in self.definitions:
            if d.match_type(notification_body['event_type']):
                userid = self.get_user_id(d, notification_body)
                projectid = self.get_project_id(d, notification_body)
                resourceid = d.parse_fields('resource_id', notification_body)
                yield sample.Sample.from_notification(
                    name=d.cfg['name'],
                    type=d.cfg['type'],
                    unit=d.cfg['unit'],
                    volume=d.parse_fields('volume', notification_body),
                    resource_id=resourceid,
                    user_id=userid,
                    project_id=projectid,
                    message=notification_body)

    @staticmethod
    def get_user_id(d, notification_body):
        return (d.parse_fields('user_id', notification_body) or
                notification_body.get('_context_user_id') or
                notification_body.get('_context_user', None))

    @staticmethod
    def get_project_id(d, notification_body):
        return (d.parse_fields('project_id', notification_body) or
                notification_body.get('_context_tenant_id') or
                notification_body.get('_context_tenant', None))
