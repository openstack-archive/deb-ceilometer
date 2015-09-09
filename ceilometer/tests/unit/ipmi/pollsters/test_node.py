# Copyright 2014 Intel Corp.
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

import mock
from oslo_config import cfg

from ceilometer.ipmi.pollsters import node
from ceilometer.tests.unit.ipmi.pollsters import base

CONF = cfg.CONF
CONF.import_opt('host', 'ceilometer.service')


class TestPowerPollster(base.TestPollsterBase):

    def fake_data(self):
        # data after parsing Intel Node Manager output
        return {"Current_value": ['13', '00']}

    def make_pollster(self):
        return node.PowerPollster()

    @mock.patch('ceilometer.pipeline.setup_pipeline', mock.MagicMock())
    def test_get_samples(self):
        self._test_get_samples()

        # only one sample, and value is 19(0x13 as current_value)
        self._verify_metering(1, 19, CONF.host)


class TestInletTemperaturePollster(base.TestPollsterBase):

    def fake_data(self):
        # data after parsing Intel Node Manager output
        return {"Current_value": ['23', '00']}

    def make_pollster(self):
        return node.InletTemperaturePollster()

    @mock.patch('ceilometer.pipeline.setup_pipeline', mock.MagicMock())
    def test_get_samples(self):
        self._test_get_samples()

        # only one sample, and value is 35(0x23 as current_value)
        self._verify_metering(1, 35, CONF.host)


class TestOutletTemperaturePollster(base.TestPollsterBase):

    def fake_data(self):
        # data after parsing Intel Node Manager output
        return {"Current_value": ['25', '00']}

    def make_pollster(self):
        return node.OutletTemperaturePollster()

    @mock.patch('ceilometer.pipeline.setup_pipeline', mock.MagicMock())
    def test_get_samples(self):
        self._test_get_samples()

        # only one sample, and value is 37(0x25 as current_value)
        self._verify_metering(1, 37, CONF.host)


class TestAirflowPollster(base.TestPollsterBase):

    def fake_data(self):
        # data after parsing Intel Node Manager output
        return {"Current_value": ['be', '00']}

    def make_pollster(self):
        return node.AirflowPollster()

    @mock.patch('ceilometer.pipeline.setup_pipeline', mock.MagicMock())
    def test_get_samples(self):
        self._test_get_samples()

        # only one sample, and value is 190(0xbe as current_value)
        self._verify_metering(1, 190, CONF.host)


class TestCUPSIndexPollster(base.TestPollsterBase):

    def fake_data(self):
        # data after parsing Intel Node Manager output
        return {"CUPS_Index": ['2e', '00']}

    def make_pollster(self):
        return node.CUPSIndexPollster()

    @mock.patch('ceilometer.pipeline.setup_pipeline', mock.MagicMock())
    def test_get_samples(self):
        self._test_get_samples()

        # only one sample, and value is 190(0xbe)
        self._verify_metering(1, 46, CONF.host)


class CPUUtilPollster(base.TestPollsterBase):

    def fake_data(self):
        # data after parsing Intel Node Manager output
        return {"CPU_Utilization":
                ['33', '00', '00', '00', '00', '00', '00', '00']}

    def make_pollster(self):
        return node.CPUUtilPollster()

    @mock.patch('ceilometer.pipeline.setup_pipeline', mock.MagicMock())
    def test_get_samples(self):
        self._test_get_samples()

        # only one sample, and value is 190(0xbe)
        self._verify_metering(1, 51, CONF.host)


class MemUtilPollster(base.TestPollsterBase):

    def fake_data(self):
        # data after parsing Intel Node Manager output
        return {"Mem_Utilization":
                ['05', '00', '00', '00', '00', '00', '00', '00']}

    def make_pollster(self):
        return node.MemUtilPollster()

    @mock.patch('ceilometer.pipeline.setup_pipeline', mock.MagicMock())
    def test_get_samples(self):
        self._test_get_samples()

        # only one sample, and value is 5(0x05)
        self._verify_metering(1, 5, CONF.host)


class IOUtilPollster(base.TestPollsterBase):

    def fake_data(self):
        # data after parsing Intel Node Manager output
        return {"IO_Utilization":
                ['00', '00', '00', '00', '00', '00', '00', '00']}

    def make_pollster(self):
        return node.IOUtilPollster()

    @mock.patch('ceilometer.pipeline.setup_pipeline', mock.MagicMock())
    def test_get_samples(self):
        self._test_get_samples()

        # only one sample, and value is 0(0x00)
        self._verify_metering(1, 0, CONF.host)
