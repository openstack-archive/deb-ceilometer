#
# Copyright 2014 Red Hat Inc.
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
from oslo_config import fixture as fixture_config
from oslotest import base

from ceilometer.agent.discovery import endpoint


class TestEndpointDiscovery(base.BaseTestCase):

    def setUp(self):
        super(TestEndpointDiscovery, self).setUp()
        self.discovery = endpoint.EndpointDiscovery()
        self.manager = mock.MagicMock()
        self.CONF = self.useFixture(fixture_config.Config()).conf
        self.CONF.set_override('os_endpoint_type', 'test-endpoint-type',
                               group='service_credentials')
        self.CONF.set_override('os_region_name', 'test-region-name',
                               group='service_credentials')

    def test_keystone_called(self):
        self.discovery.discover(self.manager, param='test-service-type')
        expected = [mock.call(service_type='test-service-type',
                              endpoint_type='test-endpoint-type',
                              region_name='test-region-name')]
        self.assertEqual(expected,
                         self.manager.keystone.service_catalog.get_urls
                         .call_args_list)

    def test_keystone_called_no_service_type(self):
        self.discovery.discover(self.manager)
        expected = [mock.call(service_type=None,
                              endpoint_type='test-endpoint-type',
                              region_name='test-region-name')]
        self.assertEqual(expected,
                         self.manager.keystone.service_catalog.get_urls
                         .call_args_list)
