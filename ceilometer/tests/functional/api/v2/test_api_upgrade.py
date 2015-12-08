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

from keystoneclient import exceptions
import mock
from oslotest import mockpatch

from ceilometer.tests.functional.api import v2


class TestAPIUpgradePath(v2.FunctionalTest):
    def _setup_osloconfig_options(self):
        self.CONF.set_override('gnocchi_is_enabled', True, group='api')
        self.CONF.set_override('aodh_is_enabled', True, group='api')
        self.CONF.set_override('aodh_url', 'http://alarm-endpoint:8008/',
                               group='api')

    def _setup_keystone_mock(self):
        self.CONF.set_override('gnocchi_is_enabled', None, group='api')
        self.CONF.set_override('aodh_is_enabled', None, group='api')
        self.CONF.set_override('aodh_url', None, group='api')
        self.CONF.set_override('meter_dispatchers', ['database'])
        self.ks = mock.Mock()
        self.ks.service_catalog.url_for.side_effect = self._url_for
        self.useFixture(mockpatch.Patch(
            'ceilometer.keystone_client.get_client', return_value=self.ks))

    @staticmethod
    def _url_for(service_type=None):
        if service_type == 'metric':
            return 'http://gnocchi/'
        elif service_type == 'alarming':
            return 'http://alarm-endpoint:8008/'
        raise exceptions.EndpointNotFound()

    def _do_test_gnocchi_enabled_without_database_backend(self):
        self.CONF.set_override('meter_dispatchers', 'gnocchi')
        for endpoint in ['meters', 'samples', 'resources']:
            response = self.app.get(self.PATH_PREFIX + '/' + endpoint,
                                    status=410)
            self.assertIn(b'Gnocchi API', response.body)

        headers_events = {"X-Roles": "admin",
                          "X-User-Id": "user1",
                          "X-Project-Id": "project1"}
        for endpoint in ['events', 'event_types']:
            self.app.get(self.PATH_PREFIX + '/' + endpoint,
                         headers=headers_events,
                         status=200)

        response = self.post_json('/query/samples',
                                  params={
                                      "filter": '{"=": {"type": "creation"}}',
                                      "orderby": '[{"timestamp": "DESC"}]',
                                      "limit": 3
                                  }, status=410)
        self.assertIn(b'Gnocchi API', response.body)
        sample_params = {
            "counter_type": "gauge",
            "counter_name": "fake_counter",
            "resource_id": "fake_resource_id",
            "counter_unit": "fake_unit",
            "counter_volume": "1"
        }
        self.post_json('/meters/fake_counter',
                       params=[sample_params],
                       status=201)
        response = self.post_json('/meters/fake_counter?direct=1',
                                  params=[sample_params],
                                  status=400)
        self.assertIn(b'direct option cannot be true when Gnocchi is enabled',
                      response.body)

    def _do_test_alarm_redirect(self):
        response = self.app.get(self.PATH_PREFIX + '/alarms',
                                expect_errors=True)

        self.assertEqual(307, response.status_code)
        self.assertEqual("http://alarm-endpoint:8008/v2/alarms",
                         response.headers['Location'])

        response = self.app.get(self.PATH_PREFIX + '/alarms/uuid',
                                expect_errors=True)

        self.assertEqual(307, response.status_code)
        self.assertEqual("http://alarm-endpoint:8008/v2/alarms/uuid",
                         response.headers['Location'])

        response = self.app.delete(self.PATH_PREFIX + '/alarms/uuid',
                                   expect_errors=True)

        self.assertEqual(307, response.status_code)
        self.assertEqual("http://alarm-endpoint:8008/v2/alarms/uuid",
                         response.headers['Location'])

        response = self.post_json('/query/alarms',
                                  params={
                                      "filter": '{"=": {"type": "creation"}}',
                                      "orderby": '[{"timestamp": "DESC"}]',
                                      "limit": 3
                                  }, status=307)
        self.assertEqual("http://alarm-endpoint:8008/v2/query/alarms",
                         response.headers['Location'])

    def test_gnocchi_enabled_without_database_backend_keystone(self):
        self._setup_keystone_mock()
        self._do_test_gnocchi_enabled_without_database_backend()
        self.ks.service_catalog.url_for.assert_has_calls([
            mock.call(service_type="alarming"),
            mock.call(service_type="metric")],
            any_order=True)

    def test_gnocchi_enabled_without_database_backend_configoptions(self):
        self._setup_osloconfig_options()
        self._do_test_gnocchi_enabled_without_database_backend()

    def test_alarm_redirect_keystone(self):
        self._setup_keystone_mock()
        self._do_test_alarm_redirect()
        self.assertEqual([mock.call(service_type="alarming")],
                         self.ks.service_catalog.url_for.mock_calls)

    def test_alarm_redirect_configoptions(self):
        self._setup_osloconfig_options()
        self._do_test_alarm_redirect()
