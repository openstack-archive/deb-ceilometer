#!/usr/bin/env python
#
# Copyright 2012 eNovance <licensing@enovance.com>
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

import collections

from keystoneclient import exceptions
import mock
from oslotest import base
from oslotest import mockpatch
from swiftclient import client as swift_client
import testscenarios.testcase

from ceilometer.agent import manager
from ceilometer.objectstore import swift

HEAD_ACCOUNTS = [('tenant-000', {'x-account-object-count': 12,
                                 'x-account-bytes-used': 321321321,
                                 'x-account-container-count': 7,
                                 }),
                 ('tenant-001', {'x-account-object-count': 34,
                                 'x-account-bytes-used': 9898989898,
                                 'x-account-container-count': 17,
                                 }),
                 ('tenant-002-ignored', {'x-account-object-count': 34,
                                         'x-account-bytes-used': 9898989898,
                                         'x-account-container-count': 17,
                                         })]

GET_ACCOUNTS = [('tenant-000', ({'x-account-object-count': 10,
                                 'x-account-bytes-used': 123123,
                                 'x-account-container-count': 2,
                                 },
                                [{'count': 10,
                                  'bytes': 123123,
                                  'name': 'my_container'},
                                 {'count': 0,
                                  'bytes': 0,
                                  'name': 'new_container'
                                  }])),
                ('tenant-001', ({'x-account-object-count': 0,
                                 'x-account-bytes-used': 0,
                                 'x-account-container-count': 0,
                                 }, [])),
                ('tenant-002-ignored', ({'x-account-object-count': 0,
                                         'x-account-bytes-used': 0,
                                         'x-account-container-count': 0,
                                         }, []))]

Tenant = collections.namedtuple('Tenant', 'id')
ASSIGNED_TENANTS = [Tenant('tenant-000'), Tenant('tenant-001')]


class TestManager(manager.AgentManager):

    def __init__(self):
        super(TestManager, self).__init__()
        self.keystone = mock.MagicMock()


class TestSwiftPollster(testscenarios.testcase.WithScenarios,
                        base.BaseTestCase):

    # Define scenarios to run all of the tests against all of the
    # pollsters.
    scenarios = [
        ('storage.objects',
         {'factory': swift.ObjectsPollster}),
        ('storage.objects.size',
         {'factory': swift.ObjectsSizePollster}),
        ('storage.objects.containers',
         {'factory': swift.ObjectsContainersPollster}),
        ('storage.containers.objects',
         {'factory': swift.ContainersObjectsPollster}),
        ('storage.containers.objects.size',
         {'factory': swift.ContainersSizePollster}),
    ]

    @staticmethod
    def fake_ks_service_catalog_url_for(*args, **kwargs):
        raise exceptions.EndpointNotFound("Fake keystone exception")

    def fake_iter_accounts(self, ksclient, cache, tenants):
        tenant_ids = [t.id for t in tenants]
        for i in self.ACCOUNTS:
            if i[0] in tenant_ids:
                yield i

    @mock.patch('ceilometer.pipeline.setup_pipeline', mock.MagicMock())
    def setUp(self):
        super(TestSwiftPollster, self).setUp()
        self.pollster = self.factory()
        self.manager = TestManager()

        if self.pollster.CACHE_KEY_METHOD == 'swift.head_account':
            self.ACCOUNTS = HEAD_ACCOUNTS
        else:
            self.ACCOUNTS = GET_ACCOUNTS

    def tearDown(self):
        super(TestSwiftPollster, self).tearDown()
        swift._Base._ENDPOINT = None

    def test_iter_accounts_no_cache(self):
        cache = {}
        with mockpatch.PatchObject(self.factory, '_get_account_info',
                                   return_value=[]):
            data = list(self.pollster._iter_accounts(mock.Mock(), cache,
                                                     ASSIGNED_TENANTS))

        self.assertIn(self.pollster.CACHE_KEY_METHOD, cache)
        self.assertEqual([], data)

    def test_iter_accounts_cached(self):
        # Verify that if a method has already been called, _iter_accounts
        # uses the cached version and doesn't call swiftclient.
        mock_method = mock.Mock()
        mock_method.side_effect = AssertionError(
            'should not be called',
        )

        api_method = '%s_account' % self.pollster.METHOD
        with mockpatch.PatchObject(swift_client, api_method, new=mock_method):
            with mockpatch.PatchObject(self.factory, '_neaten_url'):
                cache = {self.pollster.CACHE_KEY_METHOD: [self.ACCOUNTS[0]]}
                data = list(self.pollster._iter_accounts(mock.Mock(), cache,
                                                         ASSIGNED_TENANTS))
        self.assertEqual([self.ACCOUNTS[0]], data)

    def test_neaten_url(self):
        test_endpoints = ['http://127.0.0.1:8080',
                          'http://127.0.0.1:8080/swift']
        test_tenant_id = 'a7fd1695fa154486a647e44aa99a1b9b'
        for test_endpoint in test_endpoints:
            standard_url = test_endpoint + '/v1/AUTH_' + test_tenant_id

            url = swift._Base._neaten_url(test_endpoint, test_tenant_id)
            self.assertEqual(standard_url, url)
            url = swift._Base._neaten_url(test_endpoint + '/', test_tenant_id)
            self.assertEqual(standard_url, url)
            url = swift._Base._neaten_url(test_endpoint + '/v1',
                                          test_tenant_id)
            self.assertEqual(standard_url, url)
            url = swift._Base._neaten_url(standard_url, test_tenant_id)
            self.assertEqual(standard_url, url)

    def test_metering(self):
        with mockpatch.PatchObject(self.factory, '_iter_accounts',
                                   side_effect=self.fake_iter_accounts):
            samples = list(self.pollster.get_samples(self.manager, {},
                                                     ASSIGNED_TENANTS))

        self.assertEqual(2, len(samples), self.pollster.__class__)

    def test_get_meter_names(self):
        with mockpatch.PatchObject(self.factory, '_iter_accounts',
                                   side_effect=self.fake_iter_accounts):
            samples = list(self.pollster.get_samples(self.manager, {},
                                                     ASSIGNED_TENANTS))

        self.assertEqual(set([samples[0].name]),
                         set([s.name for s in samples]))

    def test_only_poll_assigned(self):
        mock_method = mock.MagicMock()
        endpoint = 'end://point/'
        api_method = '%s_account' % self.pollster.METHOD
        with mockpatch.PatchObject(swift_client, api_method, new=mock_method):
            with mockpatch.PatchObject(
                    self.manager.keystone.service_catalog, 'url_for',
                    return_value=endpoint):
                list(self.pollster.get_samples(self.manager, {},
                                               ASSIGNED_TENANTS))
        expected = [mock.call(self.pollster._neaten_url(endpoint, t.id),
                              self.manager.keystone.auth_token)
                    for t in ASSIGNED_TENANTS]
        self.assertEqual(expected, mock_method.call_args_list)

    def test_get_endpoint_only_once(self):
        endpoint = 'end://point/'
        mock_url_for = mock.MagicMock(return_value=endpoint)
        api_method = '%s_account' % self.pollster.METHOD
        with mockpatch.PatchObject(swift_client, api_method,
                                   new=mock.MagicMock()):
            with mockpatch.PatchObject(
                    self.manager.keystone.service_catalog, 'url_for',
                    new=mock_url_for):
                list(self.pollster.get_samples(self.manager, {},
                                               ASSIGNED_TENANTS))
                list(self.pollster.get_samples(self.manager, {},
                                               ASSIGNED_TENANTS))
        self.assertEqual(1, mock_url_for.call_count)

    def test_endpoint_notfound(self):
        with mockpatch.PatchObject(
                self.manager.keystone.service_catalog, 'url_for',
                side_effect=self.fake_ks_service_catalog_url_for):
            samples = list(self.pollster.get_samples(self.manager, {},
                                                     ASSIGNED_TENANTS))

        self.assertEqual(0, len(samples))
