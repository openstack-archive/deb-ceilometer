# -*- encoding: utf-8 -*-
#
# Copyright © 2013 IBM Corp
#
# Author: Tong Li <litong01@us.ibm.com>
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
"""Tests for ceilometer/collector/dispatcher/file.py
"""

import os
import tempfile
import logging.handlers
from oslo.config import cfg

from ceilometer.collector.dispatcher import file
from ceilometer.publisher import rpc
from ceilometer.tests import base as tests_base


class TestDispatcherFile(tests_base.TestCase):

    def setUp(self):
        super(TestDispatcherFile, self).setUp()

    def test_file_dispatcher_with_all_config(self):
        # Create a temporaryFile to get a file name
        tf = tempfile.NamedTemporaryFile('r')
        filename = tf.name
        tf.close()

        cfg.CONF.dispatcher_file.file_path = filename
        cfg.CONF.dispatcher_file.max_bytes = 50
        cfg.CONF.dispatcher_file.backup_count = 5
        dispatcher = file.FileDispatcher(cfg.CONF)

        # The number of the handlers should be 1
        self.assertEqual(1, len(dispatcher.log.handlers))
        # The handler should be RotatingFileHandler
        handler = dispatcher.log.handlers[0]
        self.assertTrue(isinstance(handler,
                                   logging.handlers.RotatingFileHandler))

        msg = {'counter_name': 'test',
               'resource_id': self.id(),
               'counter_volume': 1,
               }
        msg['message_signature'] = rpc.compute_signature(
            msg,
            cfg.CONF.publisher_rpc.metering_secret,
        )

        # The record_metering_data method should exist and not produce errors.
        dispatcher.record_metering_data(None, msg)
        # After the method call above, the file should have been created.
        self.assertTrue(os.path.exists(handler.baseFilename))

    def test_file_dispatcher_with_path_only(self):
        # Create a temporaryFile to get a file name
        tf = tempfile.NamedTemporaryFile('r')
        filename = tf.name
        tf.close()

        cfg.CONF.dispatcher_file.file_path = filename
        cfg.CONF.dispatcher_file.max_bytes = None
        cfg.CONF.dispatcher_file.backup_count = None
        dispatcher = file.FileDispatcher(cfg.CONF)

        # The number of the handlers should be 1
        self.assertEqual(1, len(dispatcher.log.handlers))
        # The handler should be RotatingFileHandler
        handler = dispatcher.log.handlers[0]
        self.assertTrue(isinstance(handler,
                                   logging.FileHandler))

        msg = {'counter_name': 'test',
               'resource_id': self.id(),
               'counter_volume': 1,
               }
        msg['message_signature'] = rpc.compute_signature(
            msg,
            cfg.CONF.publisher_rpc.metering_secret,
        )

        # The record_metering_data method should exist and not produce errors.
        dispatcher.record_metering_data(None, msg)
        # After the method call above, the file should have been created.
        self.assertTrue(os.path.exists(handler.baseFilename))

    def test_file_dispatcher_with_no_path(self):
        cfg.CONF.dispatcher_file.file_path = None
        dispatcher = file.FileDispatcher(cfg.CONF)

        # The log should be None
        self.assertIsNone(dispatcher.log)
