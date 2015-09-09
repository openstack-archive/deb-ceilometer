#
# Copyright 2013 Intel Corp
#
# Authors: Lianhao Lu <lianhao.lu@intel.com>
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

from ceilometer.hardware.pollsters import disk
from ceilometer import sample
from ceilometer.tests.unit.hardware.pollsters import base


class TestDiskPollsters(base.TestPollsterBase):
    def test_disk_size_total(self):
        self._check_get_samples(disk.DiskTotalPollster,
                                'hardware.disk.size.total',
                                1000, sample.TYPE_GAUGE)

    def test_disk_size_used(self):
        self._check_get_samples(disk.DiskUsedPollster,
                                'hardware.disk.size.used',
                                90, sample.TYPE_GAUGE)
