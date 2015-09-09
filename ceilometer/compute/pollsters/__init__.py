# Copyright 2014 Mirantis, Inc.
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

import abc

from oslo_utils import timeutils
import six

from ceilometer.agent import plugin_base
from ceilometer.compute.virt import inspector as virt_inspector


@six.add_metaclass(abc.ABCMeta)
class BaseComputePollster(plugin_base.PollsterBase):

    def setup_environment(self):
        super(BaseComputePollster, self).setup_environment()
        # propagate exception from check_sanity
        self.inspector.check_sanity()

    @property
    def inspector(self):
        try:
            inspector = self._inspector
        except AttributeError:
            inspector = virt_inspector.get_hypervisor_inspector()
            BaseComputePollster._inspector = inspector
        return inspector

    @property
    def default_discovery(self):
        return 'local_instances'

    def _record_poll_time(self):
        """Method records current time as the poll time.

        :return: time in seconds since the last poll time was recorded
        """
        current_time = timeutils.utcnow()
        duration = None
        if hasattr(self, '_last_poll_time'):
            duration = timeutils.delta_seconds(self._last_poll_time,
                                               current_time)
        self._last_poll_time = current_time
        return duration
