# -*- encoding: utf-8 -*-
#
# Copyright © 2013 New Dream Network, LLC (DreamHost)
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

import datetime

from ceilometer.openstack.common import test
from ceilometer.storage import models


class FakeModel(models.Model):
    def __init__(self, arg1, arg2):
        models.Model.__init__(self, arg1=arg1, arg2=arg2)


class ModelTest(test.BaseTestCase):

    def test_create_attributes(self):
        m = FakeModel(1, 2)
        self.assertEqual(m.arg1, 1)
        self.assertEqual(m.arg2, 2)

    def test_as_dict(self):
        m = FakeModel(1, 2)
        d = m.as_dict()
        self.assertEqual(d, {'arg1': 1, 'arg2': 2})

    def test_as_dict_recursive(self):
        m = FakeModel(1, FakeModel('a', 'b'))
        d = m.as_dict()
        self.assertEqual(d, {'arg1': 1,
                             'arg2': {'arg1': 'a',
                                      'arg2': 'b'}})

    def test_as_dict_recursive_list(self):
        m = FakeModel(1, [FakeModel('a', 'b')])
        d = m.as_dict()
        self.assertEqual(d, {'arg1': 1,
                             'arg2': [{'arg1': 'a',
                                       'arg2': 'b'}]})

    def test_event_repr_no_traits(self):
        x = models.Event("1", "name", "now", None)
        self.assertEqual("<Event: 1, name, now, >", repr(x))


class TestTraitModel(test.BaseTestCase):

    def test_convert_value(self):
        v = models.Trait.convert_value(
            models.Trait.INT_TYPE, '10')
        self.assertEqual(v, 10)
        self.assertIsInstance(v, int)
        v = models.Trait.convert_value(
            models.Trait.FLOAT_TYPE, '10')
        self.assertEqual(v, 10.0)
        self.assertIsInstance(v, float)

        v = models.Trait.convert_value(
            models.Trait.DATETIME_TYPE, '2013-08-08 21:05:37.123456')
        self.assertEqual(v, datetime.datetime(2013, 8, 8, 21, 5, 37, 123456))
        self.assertIsInstance(v, datetime.datetime)

        v = models.Trait.convert_value(
            models.Trait.TEXT_TYPE, 10)
        self.assertEqual(v, "10")
        self.assertIsInstance(v, str)
