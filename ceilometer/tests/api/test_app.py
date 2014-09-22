# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright 2014 IBM Corp.
# All Rights Reserved.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

import socket

import mock
from oslo.config import cfg
from oslo.config import fixture as fixture_config

from ceilometer.api import app
from ceilometer.tests import base


class TestApp(base.BaseTestCase):

    def setUp(self):
        super(TestApp, self).setUp()
        self.CONF = self.useFixture(fixture_config.Config()).conf

    def test_WSGI_address_family(self):
        self.CONF.set_override('host', '::', group='api')
        server_cls = app.get_server_cls(cfg.CONF.api.host)
        self.assertEqual(server_cls.address_family, socket.AF_INET6)

        self.CONF.set_override('host', '127.0.0.1', group='api')
        server_cls = app.get_server_cls(cfg.CONF.api.host)
        self.assertEqual(server_cls.address_family, socket.AF_INET)

        self.CONF.set_override('host', 'ddddd', group='api')
        server_cls = app.get_server_cls(cfg.CONF.api.host)
        self.assertEqual(server_cls.address_family, socket.AF_INET)

    def test_api_paste_file_not_exist(self):
        self.CONF.set_override('api_paste_config', 'non-existent-file')
        with mock.patch.object(self.CONF, 'find_file') as ff:
            ff.return_value = None
            self.assertRaises(cfg.ConfigFilesNotFoundError, app.load_app)
