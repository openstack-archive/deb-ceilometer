#
# Copyright 2012 New Dream Network, LLC (DreamHost)
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
"""Tests for ceilometer/storage/
"""

from ceilometer.openstack.common import test
from ceilometer import storage
from ceilometer.storage import impl_log

import six


class EngineTest(test.BaseTestCase):

    def test_get_connection(self):
        engine = storage.get_connection('log://localhost')
        self.assertIsInstance(engine, impl_log.Connection)

    def test_get_connection_no_such_engine(self):
        try:
            storage.get_connection('no-such-engine://localhost')
        except RuntimeError as err:
            self.assertIn('no-such-engine', six.text_type(err))
