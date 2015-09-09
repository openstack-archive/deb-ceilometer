#
# Copyright 2013 ZHAW SoE
# Copyright 2014 Intel Corp.
#
# Authors: Lucas Graf <graflu0@students.zhaw.ch>
#          Toni Zehnder <zehndton@students.zhaw.ch>
#          Lianhao Lu <lianhao.lu@intel.com>
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

from ceilometer.hardware import plugin
from ceilometer.hardware.pollsters import util
from ceilometer import sample


class _Base(plugin.HardwarePollster):

    CACHE_KEY = 'memory'

    def generate_one_sample(self, host, c_data):
        value, metadata, extra = c_data
        return util.make_sample_from_host(host,
                                          name=self.IDENTIFIER,
                                          sample_type=sample.TYPE_GAUGE,
                                          unit='KB',
                                          volume=value,
                                          res_metadata=metadata,
                                          extra=extra)


class MemoryTotalPollster(_Base):
    IDENTIFIER = 'memory.total'


class MemoryUsedPollster(_Base):
    IDENTIFIER = 'memory.used'


class MemorySwapTotalPollster(_Base):
    IDENTIFIER = 'memory.swap.total'


class MemorySwapAvailPollster(_Base):
    IDENTIFIER = 'memory.swap.avail'


class MemoryBufferPollster(_Base):
    IDENTIFIER = 'memory.buffer'


class MemoryCachedPollster(_Base):
    IDENTIFIER = 'memory.cached'
