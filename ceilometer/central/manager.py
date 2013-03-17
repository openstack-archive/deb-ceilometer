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

from keystoneclient.v2_0 import client as ksclient
from oslo.config import cfg

from ceilometer import agent
from ceilometer import extension_manager
from ceilometer.openstack.common import log
from ceilometer import service  # For cfg.CONF.os_*

OPTS = [
    cfg.ListOpt('disabled_central_pollsters',
                default=[],
                help='list of central pollsters to disable',
                ),
]

cfg.CONF.register_opts(OPTS)


LOG = log.getLogger(__name__)


class PollingTask(agent.PollingTask):
    def poll_and_publish(self):
        """Tasks to be run at a periodic interval."""
        with self.publish_context as publisher:
            # TODO(yjiang5) passing counters into get_counters to avoid
            # polling all counters one by one
            for pollster in self.pollsters:
                try:
                    LOG.info("Polling pollster %s", pollster.name)
                    publisher(list(pollster.obj.get_counters(
                        self.manager)))
                except Exception as err:
                    LOG.warning('Continue after error from %s: %s',
                                pollster.name, err)
                    LOG.exception(err)


class AgentManager(agent.AgentManager):

    def __init__(self):
        super(AgentManager, self).__init__(
            extension_manager.ActivatedExtensionManager(
                namespace='ceilometer.poll.central',
                disabled_names=cfg.CONF.disabled_central_pollsters,
            ),
        )

    def create_polling_task(self):
        return PollingTask(self)

    def interval_task(self, task):
        self.keystone = ksclient.Client(
            username=cfg.CONF.os_username,
            password=cfg.CONF.os_password,
            tenant_id=cfg.CONF.os_tenant_id,
            tenant_name=cfg.CONF.os_tenant_name,
            auth_url=cfg.CONF.os_auth_url)

        super(AgentManager, self).interval_task(task)
