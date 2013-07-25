# -*- encoding: utf-8 -*-
#
# Copyright © 2013 Intel Corp.
#
# Author: Lianhao Lu <lianhao.lu@intel.com>
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
"""Tests for ceilometer/central/manager.py
"""

import mock
from keystoneclient.v2_0 import client as ksclient

from ceilometer.central import manager
from ceilometer.tests import base
from tests import agentbase


class TestManager(base.TestCase):

    @mock.patch('ceilometer.pipeline.setup_pipeline', mock.MagicMock())
    def test_load_plugins(self):
        mgr = manager.AgentManager()
        self.assertIsNotNone(list(mgr.pollster_manager))


class TestRunTasks(agentbase.BaseAgentManagerTestCase):

    def setup_manager(self):
        self.mgr = manager.AgentManager()

    def setUp(self):
        super(TestRunTasks, self).setUp()
        self.stubs.Set(ksclient, 'Client', lambda *args, **kwargs: None)

    def tearDown(self):
        super(TestRunTasks, self).tearDown()
