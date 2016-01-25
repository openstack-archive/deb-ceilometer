# Copyright (C) 2014 eNovance SAS <licensing@enovance.com>
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

import functools

from neutronclient.common import exceptions
from neutronclient.v2_0 import client as clientv20
from oslo_config import cfg
from oslo_log import log

from ceilometer import keystone_client

SERVICE_OPTS = [
    cfg.StrOpt('neutron',
               default='network',
               help='Neutron service type.'),
]

cfg.CONF.register_opts(SERVICE_OPTS, group='service_types')
cfg.CONF.import_group('service_credentials', 'ceilometer.keystone_client')

LOG = log.getLogger(__name__)


def logged(func):

    @functools.wraps(func)
    def with_logging(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except exceptions.NeutronClientException as e:
            if e.status_code == 404:
                LOG.warning("The resource could not be found.")
            else:
                LOG.warning(e)
            return []
        except Exception as e:
            LOG.exception(e)
            raise

    return with_logging


class Client(object):
    """A client which gets information via python-neutronclient."""

    def __init__(self):
        conf = cfg.CONF.service_credentials
        params = {
            'session': keystone_client.get_session(),
            'endpoint_type': conf.interface,
            'region_name': conf.region_name,
            'service_type': cfg.CONF.service_types.neutron,
        }
        self.client = clientv20.Client(**params)

    @logged
    def port_get_all(self):
        resp = self.client.list_ports()
        return resp.get('ports')

    @logged
    def vip_get_all(self):
        resp = self.client.list_vips()
        return resp.get('vips')

    @logged
    def pool_get_all(self):
        resp = self.client.list_pools()
        return resp.get('pools')

    @logged
    def member_get_all(self):
        resp = self.client.list_members()
        return resp.get('members')

    @logged
    def health_monitor_get_all(self):
        resp = self.client.list_health_monitors()
        return resp.get('health_monitors')

    @logged
    def pool_stats(self, pool):
        return self.client.retrieve_pool_stats(pool)

    @logged
    def vpn_get_all(self):
        resp = self.client.list_vpnservices()
        return resp.get('vpnservices')

    @logged
    def ipsec_site_connections_get_all(self):
        resp = self.client.list_ipsec_site_connections()
        return resp.get('ipsec_site_connections')

    @logged
    def firewall_get_all(self):
        resp = self.client.list_firewalls()
        return resp.get('firewalls')

    @logged
    def fw_policy_get_all(self):
        resp = self.client.list_firewall_policies()
        return resp.get('firewall_policies')
