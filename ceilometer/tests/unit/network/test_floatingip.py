#!/usr/bin/env python
#
# Copyright 2012 eNovance <licensing@enovance.com>
#
# Copyright 2013 IBM Corp
# All Rights Reserved.
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

import mock
from oslo_context import context
from oslotest import base

from ceilometer.agent import manager
from ceilometer.network import floatingip


class TestFloatingIPPollster(base.BaseTestCase):

    @mock.patch('ceilometer.pipeline.setup_pipeline', mock.MagicMock())
    def setUp(self):
        super(TestFloatingIPPollster, self).setUp()
        self.addCleanup(mock.patch.stopall)
        self.context = context.get_admin_context()
        self.manager = manager.AgentManager()
        self.manager._keystone = mock.Mock()
        catalog = (self.manager._keystone.session.auth.
                   get_access.return_value.service_catalog)
        catalog.get_endpoints = mock.Mock(return_value={'network': mock.ANY})
        self.pollster = floatingip.FloatingIPPollster()
        fake_ips = self.fake_get_ips()
        patch_virt = mock.patch('ceilometer.nova_client.Client.'
                                'floating_ip_get_all',
                                return_value=fake_ips)
        patch_virt.start()

    @staticmethod
    def fake_get_ips():
        ips = []
        for i in range(1, 4):
            ip = mock.MagicMock()
            ip.id = i
            ip.ip = '1.1.1.%d' % i
            ip.pool = 'public'
            ips.append(ip)
        return ips

    def test_default_discovery(self):
        self.assertEqual('endpoint:compute', self.pollster.default_discovery)

    # FIXME(dhellmann): Is there a useful way to define this
    # test without a database?
    #
    # def test_get_samples_none_defined(self):
    #     try:
    #         list(self.pollster.get_samples(self.manager,
    #                                         self.context)
    #              )
    #     except exception.NoFloatingIpsDefined:
    #         pass
    #     else:
    #         assert False, 'Should have seen an error'

    def test_get_samples_not_empty(self):
        samples = list(self.pollster.get_samples(self.manager, {}, ['e']))
        self.assertEqual(3, len(samples))
        # It's necessary to verify all the attributes extracted by Nova
        # API /os-floating-ips to make sure they're available and correct.
        self.assertEqual(1, samples[0].resource_id)
        self.assertEqual("1.1.1.1", samples[0].resource_metadata["address"])
        self.assertEqual("public", samples[0].resource_metadata["pool"])

        self.assertEqual(2, samples[1].resource_id)
        self.assertEqual("1.1.1.2", samples[1].resource_metadata["address"])
        self.assertEqual("public", samples[1].resource_metadata["pool"])

        self.assertEqual(3, samples[2].resource_id)
        self.assertEqual("1.1.1.3", samples[2].resource_metadata["address"])
        self.assertEqual("public", samples[2].resource_metadata["pool"])

    def test_get_meter_names(self):
        samples = list(self.pollster.get_samples(self.manager, {}, ['e']))
        self.assertEqual(set(['ip.floating']), set([s.name for s in samples]))

    def test_get_samples_cached(self):
        cache = {'e-floating_ips': self.fake_get_ips()[:2]}
        samples = list(self.pollster.get_samples(self.manager, cache, ['e']))
        self.assertEqual(2, len(samples))
