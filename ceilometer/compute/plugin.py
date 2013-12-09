# -*- encoding: utf-8 -*-
#
# Copyright © 2012 New Dream Network, LLC (DreamHost)
#
# Author: Doug Hellmann <doug.hellmann@dreamhost.com>
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
"""Base class for plugins used by the compute agent.
"""

import abc
import six

from ceilometer import plugin


@six.add_metaclass(abc.ABCMeta)
class ComputePollster(plugin.PollsterBase):
    """Base class for plugins that support the polling API on the compute node.
    """

    @abc.abstractmethod
    def get_samples(self, manager, cache, instance):
        """Return a sequence of Counter instances from polling the resources.

        :param manager: The service manager invoking the plugin
        :param cache: A dictionary for passing data between plugins
        :param instance: The instance to examine
        """
