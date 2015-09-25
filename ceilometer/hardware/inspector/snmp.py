#
# Copyright 2014 ZHAW SoE
# Copyright 2014 Intel Corp
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
"""Inspector for collecting data over SNMP"""

import copy
from pysnmp.entity.rfc3413.oneliner import cmdgen

import six

from ceilometer.hardware.inspector import base


class SNMPException(Exception):
    pass


def parse_snmp_return(ret, is_bulk=False):
    """Check the return value of snmp operations

    :param ret: a tuple of (errorIndication, errorStatus, errorIndex, data)
                returned by pysnmp
    :param is_bulk: True if the ret value is from GetBulkRequest
    :return: a tuple of (err, data)
             err: True if error found, or False if no error found
             data: a string of error description if error found, or the
                   actual return data of the snmp operation
    """
    err = True
    (errIndication, errStatus, errIdx, varBinds) = ret
    if errIndication:
        data = errIndication
    elif errStatus:
        if is_bulk:
            varBinds = varBinds[-1]
        data = "%s at %s" % (errStatus.prettyPrint(),
                             errIdx and varBinds[int(errIdx) - 1] or "?")
    else:
        err = False
        data = varBinds
    return err, data


EXACT = 'type_exact'
PREFIX = 'type_prefix'


class SNMPInspector(base.Inspector):
    # Default port
    _port = 161

    _CACHE_KEY_OID = "snmp_cached_oid"

    # NOTE: The following mapping has been moved to the yaml file identified
    # by the config options hardware.meter_definitions_file. However, we still
    # keep the description here for code reading purpose.

    """

     The following mapping define how to construct
     (value, metadata, extra) returned by inspect_generic
     MAPPING = {
         'identifier: {
             'matching_type': EXACT or PREFIX,
             'metric_oid': (oid, value_converter)
             'metadata': {
                 metadata_name1: (oid1, value_converter),
                 metadata_name2: (oid2, value_converter),
             },
             'post_op': special func to modify the return data,
         },
     }

     For matching_type of EXACT, each item in the above mapping will
     return exact one (value, metadata, extra) tuple. The value would be
     returned from SNMP request GetRequest for oid of 'metric_oid', the
     metadata dict would be constructed based on the returning from SNMP
     GetRequest for oids of 'metadata'.

     For matching_type of PREFIX, SNMP request GetBulkRequest
     would be send to get values for oids of 'metric_oid' and
     'metadata' of each item in the above mapping. And each item might
     return multiple (value, metadata, extra) tuple, e.g.
     Suppose we have the following mapping:
     MAPPING = {
      'disk.size.total': {
        'matching_type': PREFIX,
        'metric_oid': ("1.3.6.1.4.1.2021.9.1.6", int)
        'metadata': {
           'device': ("1.3.6.1.4.1.2021.9.1.3", str),
           'path': ("1.3.6.1.4.1.2021.9.1.2", str),
        },
        'post_op': None,
      },
     and the SNMP have the following oid/value(s):
     {
      '1.3.6.1.4.1.2021.9.1.6.1': 19222656,
      '1.3.6.1.4.1.2021.9.1.3.1': "/dev/sda2",
      '1.3.6.1.4.1.2021.9.1.2.1': "/"
      '1.3.6.1.4.1.2021.9.1.6.2': 808112,
      '1.3.6.1.4.1.2021.9.1.3.2': "tmpfs",
      '1.3.6.1.4.1.2021.9.1.2.2': "/run",
     }
     So here we'll return 2 instances of (value, metadata, extra):
     (19222656, {'device': "/dev/sda2", 'path': "/"}, None)
     (808112, {'device': "tmpfs", 'path': "/run"}, None)

     The post_op is assumed to be implemented by new metric developer. It
     could be used to add additional special metadata(e.g. ip address), or
     it could be used to add information into extra dict to be returned
     to construct the pollster how to build final sample, e.g.
         extra.update('project_id': xy, 'user_id': zw)
    """

    def __init__(self):
        super(SNMPInspector, self).__init__()
        self._cmdGen = cmdgen.CommandGenerator()

    def _query_oids(self, host, oids, cache, is_bulk):
        # send GetRequest or GetBulkRequest to get oid values and
        # populate the values into cache
        authData = self._get_auth_strategy(host)
        transport = cmdgen.UdpTransportTarget((host.hostname,
                                               host.port or self._port))
        oid_cache = cache.setdefault(self._CACHE_KEY_OID, {})

        if is_bulk:
            ret = self._cmdGen.bulkCmd(authData,
                                       transport,
                                       0, 100,
                                       *oids,
                                       lookupValues=True)
        else:
            ret = self._cmdGen.getCmd(authData,
                                      transport,
                                      *oids,
                                      lookupValues=True)
        (error, data) = parse_snmp_return(ret, is_bulk)
        if error:
            raise SNMPException("An error occurred, oids %(oid)s, "
                                "host %(host)s, %(err)s" %
                                dict(oid=oids,
                                     host=host.hostname,
                                     err=data))
        # save result into cache
        if is_bulk:
            for var_bind_table_row in data:
                for name, val in var_bind_table_row:
                    oid_cache[name.prettyPrint()] = val
        else:
            for name, val in data:
                oid_cache[name.prettyPrint()] = val

    @staticmethod
    def find_matching_oids(oid_cache, oid, match_type, find_one=True):
        matched = []
        if match_type == PREFIX:
            for key in oid_cache.keys():
                if key.startswith(oid):
                    matched.append(key)
                    if find_one:
                        break
        else:
            if oid in oid_cache:
                matched.append(oid)
        return matched

    @staticmethod
    def get_oid_value(oid_cache, oid_def, suffix=''):
        oid, converter = oid_def
        value = oid_cache[oid + suffix]
        if converter:
            value = converter(value)
        return value

    @classmethod
    def construct_metadata(cls, oid_cache, meta_defs, suffix=''):
        metadata = {}
        for key, oid_def in six.iteritems(meta_defs):
            metadata[key] = cls.get_oid_value(oid_cache, oid_def, suffix)
        return metadata

    @classmethod
    def _find_missing_oids(cls, meter_def, cache):
        # find oids have not been queried and cached
        new_oids = []
        oid_cache = cache.setdefault(cls._CACHE_KEY_OID, {})
        # check metric_oid
        if not cls.find_matching_oids(oid_cache,
                                      meter_def['metric_oid'][0],
                                      meter_def['matching_type']):
            new_oids.append(meter_def['metric_oid'][0])
        for metadata in meter_def['metadata'].values():
            if not cls.find_matching_oids(oid_cache,
                                          metadata[0],
                                          meter_def['matching_type']):
                new_oids.append(metadata[0])
        return new_oids

    def inspect_generic(self, host, cache, extra_metadata, param):
        # the snmp definition for the corresponding meter
        meter_def = param
        # collect oids that needs to be queried
        oids_to_query = self._find_missing_oids(meter_def, cache)
        # query oids and populate into caches
        if oids_to_query:
            self._query_oids(host, oids_to_query, cache,
                             meter_def['matching_type'] == PREFIX)
        # construct (value, metadata, extra)
        oid_cache = cache[self._CACHE_KEY_OID]
        # find all oids which needed to construct final sample values
        # for matching type of EXACT, only 1 sample would be generated
        # for matching type of PREFIX, multiple samples could be generated
        oids_for_sample_values = self.find_matching_oids(
            oid_cache,
            meter_def['metric_oid'][0],
            meter_def['matching_type'],
            False)
        input_extra_metadata = extra_metadata

        for oid in oids_for_sample_values:
            suffix = oid[len(meter_def['metric_oid'][0]):]
            value = self.get_oid_value(oid_cache,
                                       meter_def['metric_oid'],
                                       suffix)
            # get the metadata for this sample value
            metadata = self.construct_metadata(oid_cache,
                                               meter_def['metadata'],
                                               suffix)
            extra_metadata = copy.deepcopy(input_extra_metadata) or {}
            # call post_op for special cases
            if meter_def['post_op']:
                func = getattr(self, meter_def['post_op'], None)
                if func:
                    value = func(host, cache, meter_def,
                                 value, metadata, extra_metadata,
                                 suffix)
            yield (value, metadata, extra_metadata)

    def _post_op_memory_avail_to_used(self, host, cache, meter_def,
                                      value, metadata, extra, suffix):
        _memory_total_oid = "1.3.6.1.4.1.2021.4.5.0"
        if _memory_total_oid not in cache[self._CACHE_KEY_OID]:
            self._query_oids(host, [_memory_total_oid], cache, False)
        value = int(cache[self._CACHE_KEY_OID][_memory_total_oid]) - value
        return value

    def _post_op_net(self, host, cache, meter_def,
                     value, metadata, extra, suffix):
        # add ip address into metadata
        _interface_ip_oid = "1.3.6.1.2.1.4.20.1.2"
        oid_cache = cache.setdefault(self._CACHE_KEY_OID, {})
        if not self.find_matching_oids(oid_cache,
                                       _interface_ip_oid,
                                       PREFIX):
            # populate the oid into cache
            self._query_oids(host, [_interface_ip_oid], cache, True)
        ip_addr = ''
        for k, v in six.iteritems(oid_cache):
            if k.startswith(_interface_ip_oid) and v == int(suffix[1:]):
                ip_addr = k.replace(_interface_ip_oid + ".", "")
        metadata.update(ip=ip_addr)
        # update resource_id for each nic interface
        self._suffix_resource_id(host, metadata, 'name', extra)
        return value

    def _post_op_disk(self, host, cache, meter_def,
                      value, metadata, extra, suffix):
        self._suffix_resource_id(host, metadata, 'device', extra)
        return value

    @staticmethod
    def _suffix_resource_id(host, metadata, key, extra):
        prefix = metadata.get(key)
        if prefix:
            res_id = extra.get('resource_id') or host.hostname
            res_id = res_id + ".%s" % metadata.get(key)
            extra.update(resource_id=res_id)

    @staticmethod
    def _get_auth_strategy(host):
        if host.password:
            auth_strategy = cmdgen.UsmUserData(host.username,
                                               authKey=host.password)
        else:
            auth_strategy = cmdgen.CommunityData(host.username or 'public')
        return auth_strategy

    def prepare_params(self, param):
        processed = {}
        processed['matching_type'] = param['matching_type']
        processed['metric_oid'] = (param['oid'], eval(param['type']))
        processed['post_op'] = param.get('post_op', None)
        processed['metadata'] = {}
        for k, v in six.iteritems(param.get('metadata', {})):
            processed['metadata'][k] = (v['oid'], eval(v['type']))
        return processed
