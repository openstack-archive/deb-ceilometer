#
# Copyright 2012 eNovance <licensing@enovance.com>
# Copyright 2012 Red Hat, Inc
# Copyright 2014 Cisco Systems, Inc
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
import abc
import collections

import six

import ceilometer
from ceilometer.compute import pollsters
from ceilometer.compute.pollsters import util
from ceilometer.compute.virt import inspector as virt_inspector
from ceilometer.i18n import _, _LW
from ceilometer.openstack.common import log
from ceilometer import sample

LOG = log.getLogger(__name__)


DiskIOData = collections.namedtuple(
    'DiskIOData',
    'r_bytes r_requests w_bytes w_requests per_disk_requests',
)

DiskRateData = collections.namedtuple('DiskRateData',
                                      ['read_bytes_rate',
                                       'read_requests_rate',
                                       'write_bytes_rate',
                                       'write_requests_rate',
                                       'per_disk_rate'])

DiskLatencyData = collections.namedtuple('DiskLatencyData',
                                         ['disk_latency',
                                          'per_disk_latency'])


@six.add_metaclass(abc.ABCMeta)
class _Base(pollsters.BaseComputePollster):

    DISKIO_USAGE_MESSAGE = ' '.join(["DISKIO USAGE:",
                                     "%s %s:",
                                     "read-requests=%d",
                                     "read-bytes=%d",
                                     "write-requests=%d",
                                     "write-bytes=%d",
                                     "errors=%d",
                                     ])

    CACHE_KEY_DISK = 'diskio'

    def _populate_cache(self, inspector, cache, instance):
        i_cache = cache.setdefault(self.CACHE_KEY_DISK, {})
        if instance.id not in i_cache:
            r_bytes = 0
            r_requests = 0
            w_bytes = 0
            w_requests = 0
            per_device_read_bytes = {}
            per_device_read_requests = {}
            per_device_write_bytes = {}
            per_device_write_requests = {}
            for disk, info in inspector.inspect_disks(instance):
                LOG.debug(self.DISKIO_USAGE_MESSAGE,
                          instance, disk.device, info.read_requests,
                          info.read_bytes, info.write_requests,
                          info.write_bytes, info.errors)
                r_bytes += info.read_bytes
                r_requests += info.read_requests
                w_bytes += info.write_bytes
                w_requests += info.write_requests
                # per disk data
                per_device_read_bytes[disk.device] = info.read_bytes
                per_device_read_requests[disk.device] = info.read_requests
                per_device_write_bytes[disk.device] = info.write_bytes
                per_device_write_requests[disk.device] = info.write_requests
            per_device_requests = {
                'read_bytes': per_device_read_bytes,
                'read_requests': per_device_read_requests,
                'write_bytes': per_device_write_bytes,
                'write_requests': per_device_write_requests,
            }
            i_cache[instance.id] = DiskIOData(
                r_bytes=r_bytes,
                r_requests=r_requests,
                w_bytes=w_bytes,
                w_requests=w_requests,
                per_disk_requests=per_device_requests,
            )
        return i_cache[instance.id]

    @abc.abstractmethod
    def _get_samples(instance, c_data):
        """Return one or more Sample."""

    def get_samples(self, manager, cache, resources):
        for instance in resources:
            instance_name = util.instance_name(instance)
            try:
                c_data = self._populate_cache(
                    self.inspector,
                    cache,
                    instance,
                )
                for s in self._get_samples(instance, c_data):
                    yield s
            except virt_inspector.InstanceNotFoundException as err:
                # Instance was deleted while getting samples. Ignore it.
                LOG.debug(_('Exception while getting samples %s'), err)
            except virt_inspector.InstanceShutOffException as e:
                LOG.warn(_LW('Instance %(instance_id)s was shut off while '
                             'getting samples of %(pollster)s: %(exc)s'),
                         {'instance_id': instance.id,
                          'pollster': self.__class__.__name__, 'exc': e})
            except ceilometer.NotImplementedError:
                # Selected inspector does not implement this pollster.
                LOG.debug(_('%(inspector)s does not provide data for '
                            ' %(pollster)s'),
                          {'inspector': self.inspector.__class__.__name__,
                           'pollster': self.__class__.__name__})
            except Exception as err:
                LOG.exception(_('Ignoring instance %(name)s: %(error)s'),
                              {'name': instance_name, 'error': err})


class ReadRequestsPollster(_Base):

    @staticmethod
    def _get_samples(instance, c_data):
        return [util.make_sample_from_instance(
            instance,
            name='disk.read.requests',
            type=sample.TYPE_CUMULATIVE,
            unit='request',
            volume=c_data.r_requests,
            additional_metadata={
                'device': c_data.per_disk_requests['read_requests'].keys()}
        )]


class PerDeviceReadRequestsPollster(_Base):

    @staticmethod
    def _get_samples(instance, c_data):
        samples = []
        for disk, value in six.iteritems(c_data.per_disk_requests[
                'read_requests']):
            samples.append(util.make_sample_from_instance(
                instance,
                name='disk.device.read.requests',
                type=sample.TYPE_CUMULATIVE,
                unit='request',
                volume=value,
                resource_id="%s-%s" % (instance.id, disk),
            ))
        return samples


class ReadBytesPollster(_Base):

    @staticmethod
    def _get_samples(instance, c_data):
        return [util.make_sample_from_instance(
            instance,
            name='disk.read.bytes',
            type=sample.TYPE_CUMULATIVE,
            unit='B',
            volume=c_data.r_bytes,
            additional_metadata={
                'device': c_data.per_disk_requests['read_bytes'].keys()},
        )]


class PerDeviceReadBytesPollster(_Base):

    @staticmethod
    def _get_samples(instance, c_data):
        samples = []
        for disk, value in six.iteritems(c_data.per_disk_requests[
                'read_bytes']):
            samples.append(util.make_sample_from_instance(
                instance,
                name='disk.device.read.bytes',
                type=sample.TYPE_CUMULATIVE,
                unit='B',
                volume=value,
                resource_id="%s-%s" % (instance.id, disk),
            ))
        return samples


class WriteRequestsPollster(_Base):

    @staticmethod
    def _get_samples(instance, c_data):
        return [util.make_sample_from_instance(
            instance,
            name='disk.write.requests',
            type=sample.TYPE_CUMULATIVE,
            unit='request',
            volume=c_data.w_requests,
            additional_metadata={
                'device': c_data.per_disk_requests['write_requests'].keys()},
        )]


class PerDeviceWriteRequestsPollster(_Base):

    @staticmethod
    def _get_samples(instance, c_data):
        samples = []
        for disk, value in six.iteritems(c_data.per_disk_requests[
                'write_requests']):
            samples.append(util.make_sample_from_instance(
                instance,
                name='disk.device.write.requests',
                type=sample.TYPE_CUMULATIVE,
                unit='request',
                volume=value,
                resource_id="%s-%s" % (instance.id, disk),
            ))
        return samples


class WriteBytesPollster(_Base):

    @staticmethod
    def _get_samples(instance, c_data):
        return [util.make_sample_from_instance(
            instance,
            name='disk.write.bytes',
            type=sample.TYPE_CUMULATIVE,
            unit='B',
            volume=c_data.w_bytes,
            additional_metadata={
                'device': c_data.per_disk_requests['write_bytes'].keys()},
        )]


class PerDeviceWriteBytesPollster(_Base):

    @staticmethod
    def _get_samples(instance, c_data):
        samples = []
        for disk, value in six.iteritems(c_data.per_disk_requests[
                'write_bytes']):
            samples.append(util.make_sample_from_instance(
                instance,
                name='disk.device.write.bytes',
                type=sample.TYPE_CUMULATIVE,
                unit='B',
                volume=value,
                resource_id="%s-%s" % (instance.id, disk),
            ))
        return samples


@six.add_metaclass(abc.ABCMeta)
class _DiskRatesPollsterBase(pollsters.BaseComputePollster):

    CACHE_KEY_DISK_RATE = 'diskio-rate'

    def _populate_cache(self, inspector, cache, instance):
        i_cache = cache.setdefault(self.CACHE_KEY_DISK_RATE, {})
        if instance.id not in i_cache:
            r_bytes_rate = 0
            r_requests_rate = 0
            w_bytes_rate = 0
            w_requests_rate = 0
            per_disk_r_bytes_rate = {}
            per_disk_r_requests_rate = {}
            per_disk_w_bytes_rate = {}
            per_disk_w_requests_rate = {}
            disk_rates = inspector.inspect_disk_rates(
                instance, self._inspection_duration)
            for disk, info in disk_rates:
                r_bytes_rate += info.read_bytes_rate
                r_requests_rate += info.read_requests_rate
                w_bytes_rate += info.write_bytes_rate
                w_requests_rate += info.write_requests_rate

                per_disk_r_bytes_rate[disk.device] = info.read_bytes_rate
                per_disk_r_requests_rate[disk.device] = info.read_requests_rate
                per_disk_w_bytes_rate[disk.device] = info.write_bytes_rate
                per_disk_w_requests_rate[disk.device] = (
                    info.write_requests_rate)
            per_disk_rate = {
                'read_bytes_rate': per_disk_r_bytes_rate,
                'read_requests_rate': per_disk_r_requests_rate,
                'write_bytes_rate': per_disk_w_bytes_rate,
                'write_requests_rate': per_disk_w_requests_rate,
            }
            i_cache[instance.id] = DiskRateData(
                r_bytes_rate,
                r_requests_rate,
                w_bytes_rate,
                w_requests_rate,
                per_disk_rate
            )
        return i_cache[instance.id]

    @abc.abstractmethod
    def _get_samples(self, instance, disk_rates_info):
        """Return one or more Sample."""

    def get_samples(self, manager, cache, resources):
        self._inspection_duration = self._record_poll_time()
        for instance in resources:
            try:
                disk_rates_info = self._populate_cache(
                    self.inspector,
                    cache,
                    instance,
                )
                for disk_rate in self._get_samples(instance, disk_rates_info):
                    yield disk_rate
            except virt_inspector.InstanceNotFoundException as err:
                # Instance was deleted while getting samples. Ignore it.
                LOG.debug(_('Exception while getting samples %s'), err)
            except ceilometer.NotImplementedError:
                # Selected inspector does not implement this pollster.
                LOG.debug(_('%(inspector)s does not provide data for '
                            ' %(pollster)s'),
                          {'inspector': self.inspector.__class__.__name__,
                           'pollster': self.__class__.__name__})
            except Exception as err:
                instance_name = util.instance_name(instance)
                LOG.exception(_('Ignoring instance %(name)s: %(error)s'),
                              {'name': instance_name, 'error': err})


class ReadBytesRatePollster(_DiskRatesPollsterBase):

    def _get_samples(self, instance, disk_rates_info):
        return [util.make_sample_from_instance(
            instance,
            name='disk.read.bytes.rate',
            type=sample.TYPE_GAUGE,
            unit='B/s',
            volume=disk_rates_info.read_bytes_rate,
            additional_metadata={
                'device': disk_rates_info.per_disk_rate[
                    'read_bytes_rate'].keys()},
        )]


class PerDeviceReadBytesRatePollster(_DiskRatesPollsterBase):

    def _get_samples(self, instance, disk_rates_info):
        samples = []
        for disk, value in six.iteritems(disk_rates_info.per_disk_rate[
                'read_bytes_rate']):
            samples.append(util.make_sample_from_instance(
                instance,
                name='disk.device.read.bytes.rate',
                type=sample.TYPE_GAUGE,
                unit='B/s',
                volume=value,
                resource_id="%s-%s" % (instance.id, disk),
            ))
        return samples


class ReadRequestsRatePollster(_DiskRatesPollsterBase):

    def _get_samples(self, instance, disk_rates_info):
        return [util.make_sample_from_instance(
            instance,
            name='disk.read.requests.rate',
            type=sample.TYPE_GAUGE,
            unit='requests/s',
            volume=disk_rates_info.read_requests_rate,
            additional_metadata={
                'device': disk_rates_info.per_disk_rate[
                    'read_requests_rate'].keys()},
        )]


class PerDeviceReadRequestsRatePollster(_DiskRatesPollsterBase):

    def _get_samples(self, instance, disk_rates_info):
        samples = []
        for disk, value in six.iteritems(disk_rates_info.per_disk_rate[
                'read_requests_rate']):
            samples.append(util.make_sample_from_instance(
                instance,
                name='disk.device.read.requests.rate',
                type=sample.TYPE_GAUGE,
                unit='requests/s',
                volume=value,
                resource_id="%s-%s" % (instance.id, disk),
            ))
        return samples


class WriteBytesRatePollster(_DiskRatesPollsterBase):

    def _get_samples(self, instance, disk_rates_info):
        return [util.make_sample_from_instance(
            instance,
            name='disk.write.bytes.rate',
            type=sample.TYPE_GAUGE,
            unit='B/s',
            volume=disk_rates_info.write_bytes_rate,
            additional_metadata={
                'device': disk_rates_info.per_disk_rate[
                    'write_bytes_rate'].keys()},
        )]


class PerDeviceWriteBytesRatePollster(_DiskRatesPollsterBase):

    def _get_samples(self, instance, disk_rates_info):
        samples = []
        for disk, value in six.iteritems(disk_rates_info.per_disk_rate[
                'write_bytes_rate']):
            samples.append(util.make_sample_from_instance(
                instance,
                name='disk.device.write.bytes.rate',
                type=sample.TYPE_GAUGE,
                unit='B/s',
                volume=value,
                resource_id="%s-%s" % (instance.id, disk),
            ))
        return samples


class WriteRequestsRatePollster(_DiskRatesPollsterBase):

    def _get_samples(self, instance, disk_rates_info):
        return [util.make_sample_from_instance(
            instance,
            name='disk.write.requests.rate',
            type=sample.TYPE_GAUGE,
            unit='requests/s',
            volume=disk_rates_info.write_requests_rate,
            additional_metadata={
                'device': disk_rates_info.per_disk_rate[
                    'write_requests_rate'].keys()},
        )]


class PerDeviceWriteRequestsRatePollster(_DiskRatesPollsterBase):

    def _get_samples(self, instance, disk_rates_info):
        samples = []
        for disk, value in six.iteritems(disk_rates_info.per_disk_rate[
                'write_requests_rate']):
            samples.append(util.make_sample_from_instance(
                instance,
                name='disk.device.write.requests.rate',
                type=sample.TYPE_GAUGE,
                unit='requests/s',
                volume=value,
                resource_id="%s-%s" % (instance.id, disk),
            ))
        return samples


@six.add_metaclass(abc.ABCMeta)
class _DiskLatencyPollsterBase(pollsters.BaseComputePollster):

    CACHE_KEY_DISK_LATENCY = 'disk-latency'

    def _populate_cache(self, inspector, cache, instance):
        i_cache = cache.setdefault(self.CACHE_KEY_DISK_LATENCY, {})
        if instance.id not in i_cache:
            latency = 0
            per_device_latency = {}
            disk_rates = inspector.inspect_disk_latency(instance)
            for disk, stats in disk_rates:
                latency += stats.disk_latency
                per_device_latency[disk.device] = (
                    stats.disk_latency)
            per_disk_latency = {
                'disk_latency': per_device_latency
            }
            i_cache[instance.id] = DiskLatencyData(
                latency,
                per_disk_latency
            )
        return i_cache[instance.id]

    @abc.abstractmethod
    def _get_samples(self, instance, disk_rates_info):
        """Return one or more Sample."""

    def get_samples(self, manager, cache, resources):
        for instance in resources:
            try:
                disk_latency_info = self._populate_cache(
                    self.inspector,
                    cache,
                    instance,
                )
                for disk_latency in self._get_samples(instance,
                                                      disk_latency_info):
                    yield disk_latency
            except virt_inspector.InstanceNotFoundException as err:
                # Instance was deleted while getting samples. Ignore it.
                LOG.debug(_('Exception while getting samples %s'), err)
            except ceilometer.NotImplementedError:
                # Selected inspector does not implement this pollster.
                LOG.debug(_('%(inspector)s does not provide data for '
                            ' %(pollster)s'),
                          {'inspector': self.inspector.__class__.__name__,
                           'pollster': self.__class__.__name__})
            except Exception as err:
                instance_name = util.instance_name(instance)
                LOG.exception(_('Ignoring instance %(name)s: %(error)s'),
                              {'name': instance_name, 'error': err})


class DiskLatencyPollster(_DiskLatencyPollsterBase):

    def _get_samples(self, instance, disk_latency_info):
        return [util.make_sample_from_instance(
            instance,
            name='disk.latency',
            type=sample.TYPE_GAUGE,
            unit='ms',
            volume=disk_latency_info.disk_latency / 1000
        )]


class PerDeviceDiskLatencyPollster(_DiskLatencyPollsterBase):

    def _get_samples(self, instance, disk_latency_info):
        samples = []
        for disk, value in six.iteritems(disk_latency_info.per_disk_latency[
                'disk_latency']):
            samples.append(util.make_sample_from_instance(
                instance,
                name='disk.device.latency',
                type=sample.TYPE_GAUGE,
                unit='ms',
                volume=value / 1000,
                resource_id="%s-%s" % (instance.id, disk)
            ))
        return samples
