#!/usr/bin/env python
# -*- encoding: utf-8 -*-
#
# Copyright © 2012 New Dream Network (DreamHost)
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
"""Test base classes.
"""
import fixtures
import functools
from oslo.config import cfg
import os.path
import testtools
from testtools import testcase

from ceilometer.openstack.common import timeutils
from ceilometer.openstack.common.fixture import config
from ceilometer.openstack.common.fixture import moxstubout


cfg.CONF.import_opt('pipeline_cfg_file', 'ceilometer.pipeline')


class TestCase(testtools.TestCase):
    def setUp(self):
        super(TestCase, self).setUp()
        self.tempdir = self.useFixture(fixtures.TempDir())
        self.useFixture(fixtures.FakeLogger())
        self.useFixture(config.Config())
        moxfixture = self.useFixture(moxstubout.MoxStubout())
        self.mox = moxfixture.mox
        self.stubs = moxfixture.stubs

        cfg.CONF([], project='ceilometer')

        # Set a default location for the pipeline config file so the
        # tests work even if ceilometer is not installed globally on
        # the system.
        cfg.CONF.set_override(
            'pipeline_cfg_file',
            self.path_get('etc/ceilometer/pipeline.yaml')
        )

    def path_get(self, project_file=None):
        root = os.path.abspath(os.path.join(os.path.dirname(__file__),
                                            '..',
                                            '..',
                                            )
                               )
        if project_file:
            return os.path.join(root, project_file)
        else:
            return root

    def temp_config_file_path(self, name='ceilometer.conf'):
        return os.path.join(self.tempdir.path, name)

    def assertTimestampEqual(self, first, second, msg=None):
        """Checks that two timestamps are equals.

        This relies on assertAlmostEqual to avoid rounding problem, and only
        checks up the first microsecond values.

        """
        return self.assertAlmostEqual(
            timeutils.delta_seconds(first, second),
            0.0,
            places=5)


def _skip_decorator(func):
    @functools.wraps(func)
    def skip_if_not_implemented(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except NotImplementedError as e:
            raise testcase.TestSkipped(str(e))
        except Exception as e:
            if 'not implemented' in str(e):
                raise testcase.TestSkipped(str(e))
            raise
    return skip_if_not_implemented


class SkipNotImplementedMeta(type):
    def __new__(cls, name, bases, local):
        for attr in local:
            value = local[attr]
            if callable(value) and (
                    attr.startswith('test_') or attr == 'setUp'):
                local[attr] = _skip_decorator(value)
        return type.__new__(cls, name, bases, local)
