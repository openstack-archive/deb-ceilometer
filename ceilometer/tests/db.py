# -*- encoding: utf-8 -*-
#
# Copyright © 2012 New Dream Network, LLC (DreamHost)
# Copyright © 2013 eNovance
#
# Author: Doug Hellmann <doug.hellmann@dreamhost.com>
#         Julien Danjou <julien@danjou.info>
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

"""Base classes for API tests."""
import os
import uuid
import warnings

from oslo.config import cfg

from ceilometer import storage
from ceilometer.tests import base as test_base


class TestBase(test_base.TestCase):
    def setUp(self):
        super(TestBase, self).setUp()
        cfg.CONF.set_override('connection', str(self.database_connection),
                              group='database')

        with warnings.catch_warnings():
            warnings.filterwarnings(
                action='ignore',
                message='.*you must provide a username and password.*')
            try:
                self.conn = storage.get_connection(cfg.CONF)
            except storage.StorageBadVersion as e:
                self.skipTest(str(e))
        self.conn.upgrade()

    def tearDown(self):
        self.conn.clear()
        self.conn = None
        super(TestBase, self).tearDown()


class MongoDBFakeConnectionUrl(object):

    def __init__(self):
        self.url = os.environ.get('CEILOMETER_TEST_MONGODB_URL')
        if not self.url:
            raise RuntimeError(
                "No MongoDB test URL set,"
                "export CEILOMETER_TEST_MONGODB_URL environment variable")

    def __str__(self):
        return '%(url)s_%(db)s' % dict(url=self.url, db=uuid.uuid4().hex)


class DB2FakeConnectionUrl(MongoDBFakeConnectionUrl):
    def __init__(self):
        self.url = (os.environ.get('CEILOMETER_TEST_DB2_URL') or
                    os.environ.get('CEILOMETER_TEST_MONGODB_URL'))
        if not self.url:
            raise RuntimeError(
                "No DB2 test URL set, "
                "export CEILOMETER_TEST_DB2_URL environment variable")
        else:
            # This is to make sure that the db2 driver is used when
            # CEILOMETER_TEST_DB2_URL was not set
            self.url = self.url.replace('mongodb:', 'db2:', 1)


class MixinTestsWithBackendScenarios(object):
    __metaclass__ = test_base.SkipNotImplementedMeta

    scenarios = [
        ('sqlalchemy', dict(database_connection='sqlite://')),
        ('mongodb', dict(database_connection=MongoDBFakeConnectionUrl())),
        ('hbase', dict(database_connection='hbase://__test__')),
        ('db2', dict(database_connection=DB2FakeConnectionUrl())),
    ]
