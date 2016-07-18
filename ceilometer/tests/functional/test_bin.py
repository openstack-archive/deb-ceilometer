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

import os
import subprocess

from oslo_utils import fileutils
import six

from ceilometer.tests import base


class BinTestCase(base.BaseTestCase):
    def setUp(self):
        super(BinTestCase, self).setUp()
        content = ("[database]\n"
                   "connection=log://localhost\n")
        if six.PY3:
            content = content.encode('utf-8')
        self.tempfile = fileutils.write_to_tempfile(content=content,
                                                    prefix='ceilometer',
                                                    suffix='.conf')

    def tearDown(self):
        super(BinTestCase, self).tearDown()
        os.remove(self.tempfile)

    def test_dbsync_run(self):
        subp = subprocess.Popen(['ceilometer-dbsync',
                                 "--config-file=%s" % self.tempfile])
        self.assertEqual(0, subp.wait())

    def test_run_expirer_ttl_disabled(self):
        subp = subprocess.Popen(['ceilometer-expirer',
                                 '-d',
                                 "--config-file=%s" % self.tempfile],
                                stderr=subprocess.PIPE)
        __, err = subp.communicate()
        self.assertEqual(0, subp.poll())
        self.assertIn(b"Nothing to clean, database metering "
                      b"time to live is disabled", err)
        self.assertIn(b"Nothing to clean, database event "
                      b"time to live is disabled", err)

    def _test_run_expirer_ttl_enabled(self, ttl_name, data_name):
        content = ("[database]\n"
                   "%s=1\n"
                   "connection=log://localhost\n" % ttl_name)
        if six.PY3:
            content = content.encode('utf-8')
        self.tempfile = fileutils.write_to_tempfile(content=content,
                                                    prefix='ceilometer',
                                                    suffix='.conf')
        subp = subprocess.Popen(['ceilometer-expirer',
                                 '-d',
                                 "--config-file=%s" % self.tempfile],
                                stderr=subprocess.PIPE)
        __, err = subp.communicate()
        self.assertEqual(0, subp.poll())
        msg = "Dropping %s data with TTL 1" % data_name
        if six.PY3:
            msg = msg.encode('utf-8')
        self.assertIn(msg, err)

    def test_run_expirer_ttl_enabled(self):
        self._test_run_expirer_ttl_enabled('metering_time_to_live',
                                           'metering')
        self._test_run_expirer_ttl_enabled('time_to_live', 'metering')
        self._test_run_expirer_ttl_enabled('event_time_to_live', 'event')


class BinSendSampleTestCase(base.BaseTestCase):
    def setUp(self):
        super(BinSendSampleTestCase, self).setUp()
        pipeline_cfg_file = self.path_get('etc/ceilometer/pipeline.yaml')
        content = ("[DEFAULT]\n"
                   "pipeline_cfg_file={0}\n".format(pipeline_cfg_file))
        if six.PY3:
            content = content.encode('utf-8')

        self.tempfile = fileutils.write_to_tempfile(content=content,
                                                    prefix='ceilometer',
                                                    suffix='.conf')

    def tearDown(self):
        super(BinSendSampleTestCase, self).tearDown()
        os.remove(self.tempfile)

    def test_send_counter_run(self):
        subp = subprocess.Popen(['ceilometer-send-sample',
                                 "--config-file=%s" % self.tempfile,
                                 "--sample-resource=someuuid",
                                 "--sample-name=mycounter"])
        self.assertEqual(0, subp.wait())


class BinCeilometerPollingServiceTestCase(base.BaseTestCase):
    def setUp(self):
        super(BinCeilometerPollingServiceTestCase, self).setUp()
        self.tempfile = None
        self.subp = None

    def tearDown(self):
        if self.subp:
            try:
                self.subp.kill()
            except OSError:
                pass
        os.remove(self.tempfile)
        super(BinCeilometerPollingServiceTestCase, self).tearDown()

    def test_starting_with_duplication_namespaces(self):
        content = ("[database]\n"
                   "connection=log://localhost\n")
        if six.PY3:
            content = content.encode('utf-8')
        self.tempfile = fileutils.write_to_tempfile(content=content,
                                                    prefix='ceilometer',
                                                    suffix='.conf')
        self.subp = subprocess.Popen(['ceilometer-polling',
                                      "--config-file=%s" % self.tempfile,
                                      "--polling-namespaces",
                                      "compute",
                                      "compute"],
                                     stderr=subprocess.PIPE)
        out = self.subp.stderr.read(1024)
        self.assertIn(b'Duplicated values: [\'compute\', \'compute\'] '
                      b'found in CLI options, auto de-duplicated', out)

    def test_polling_namespaces_invalid_value_in_config(self):
        content = ("[DEFAULT]\n"
                   "polling_namespaces = ['central']\n"
                   "[database]\n"
                   "connection=log://localhost\n")
        if six.PY3:
            content = content.encode('utf-8')
        self.tempfile = fileutils.write_to_tempfile(content=content,
                                                    prefix='ceilometer',
                                                    suffix='.conf')
        self.subp = subprocess.Popen(
            ["ceilometer-polling", "--config-file=%s" % self.tempfile],
            stderr=subprocess.PIPE)
        __, err = self.subp.communicate()
        expected = ("Exception: Valid values are ['compute', 'central', "
                    "'ipmi'], but found [\"['central']\"]")
        self.assertIn(expected, err)
