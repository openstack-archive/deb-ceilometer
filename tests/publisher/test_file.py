# -*- encoding: utf-8 -*-
#
# Copyright © 2013 eNovance
#
# Author: Julien Danjou <julien@danjou.info>
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
"""Tests for ceilometer/publisher/udp.py
"""

import datetime
import os
import logging
import logging.handlers
from ceilometer import sample
from ceilometer.publisher import file
from ceilometer.tests import base
from ceilometer.openstack.common.network_utils import urlsplit


class TestFilePublisher(base.TestCase):

    test_data = [
        sample.Sample(
            name='test',
            type=sample.TYPE_CUMULATIVE,
            unit='',
            volume=1,
            user_id='test',
            project_id='test',
            resource_id='test_run_tasks',
            timestamp=datetime.datetime.utcnow().isoformat(),
            resource_metadata={'name': 'TestPublish'},
        ),
        sample.Sample(
            name='test2',
            type=sample.TYPE_CUMULATIVE,
            unit='',
            volume=1,
            user_id='test',
            project_id='test',
            resource_id='test_run_tasks',
            timestamp=datetime.datetime.utcnow().isoformat(),
            resource_metadata={'name': 'TestPublish'},
        ),
        sample.Sample(
            name='test2',
            type=sample.TYPE_CUMULATIVE,
            unit='',
            volume=1,
            user_id='test',
            project_id='test',
            resource_id='test_run_tasks',
            timestamp=datetime.datetime.utcnow().isoformat(),
            resource_metadata={'name': 'TestPublish'},
        ),
    ]

    def test_file_publisher_maxbytes(self):
        # Test valid configurations
        name = '%s/log_file' % self.tempdir.path
        parsed_url = urlsplit('file://%s?max_bytes=50&backup_count=3' % name)
        publisher = file.FilePublisher(parsed_url)
        publisher.publish_samples(None,
                                  self.test_data)

        handler = publisher.publisher_logger.handlers[0]
        self.assertTrue(isinstance(handler,
                                   logging.handlers.RotatingFileHandler))
        self.assertEqual([handler.maxBytes, handler.baseFilename,
                          handler.backupCount],
                         [50, name, 3])
        # The rotating file gets created since only allow 50 bytes.
        self.assertTrue(os.path.exists('%s.1' % name))

    def test_file_publisher(self):
        # Test missing max bytes, backup count configurations
        name = '%s/log_file_plain' % self.tempdir.path
        parsed_url = urlsplit('file://%s' % name)
        publisher = file.FilePublisher(parsed_url)
        publisher.publish_samples(None,
                                  self.test_data)

        handler = publisher.publisher_logger.handlers[0]
        self.assertTrue(isinstance(handler,
                                   logging.handlers.RotatingFileHandler))
        self.assertEqual([handler.maxBytes, handler.baseFilename,
                          handler.backupCount],
                         [0, name, 0])
        # Test the content is corrected saved in the file
        self.assertTrue(os.path.exists(name))
        with open(name, 'r') as f:
            content = f.read()
        for sample in self.test_data:
            self.assertTrue(sample.id in content)
            self.assertTrue(sample.timestamp in content)

    def test_file_publisher_invalid(self):
        # Test invalid max bytes, backup count configurations
        parsed_url = urlsplit(
            'file://%s/log_file_bad'
            '?max_bytes=yus&backup_count=5y' % self.tempdir.path)
        publisher = file.FilePublisher(parsed_url)
        publisher.publish_samples(None,
                                  self.test_data)

        self.assertIsNone(publisher.publisher_logger)
