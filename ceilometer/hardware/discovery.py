# -*- encoding: utf-8 -*-
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

from oslo_config import cfg
from oslo_log import log
from oslo_utils import timeutils

from ceilometer.agent import plugin_base
from ceilometer.i18n import _
from ceilometer import nova_client


LOG = log.getLogger(__name__)

OPTS = [
    cfg.StrOpt('url_scheme',
               default='snmp://',
               help='URL scheme to use for hardware nodes.'),
    cfg.StrOpt('readonly_user_name',
               default='ro_snmp_user',
               help='SNMPd user name of all nodes running in the cloud.'),
    cfg.StrOpt('readonly_user_password',
               default='password',
               help='SNMPd v3 authentication password of all the nodes '
                    'running in the cloud.',
               secret=True),
    cfg.StrOpt('readonly_user_auth_proto',
               choices=['md5', 'sha'],
               help='SNMPd v3 authentication algorithm of all the nodes '
                    'running in the cloud'),
    cfg.StrOpt('readonly_user_priv_proto',
               choices=['des', 'aes128', '3des', 'aes192', 'aes256'],
               help='SNMPd v3 encryption algorithm of all the nodes '
                    'running in the cloud'),
    cfg.StrOpt('readonly_user_priv_password',
               help='SNMPd v3 encryption password of all the nodes '
                    'running in the cloud.',
               secret=True),


]
CONF = cfg.CONF
CONF.register_opts(OPTS, group='hardware')


class NodesDiscoveryTripleO(plugin_base.DiscoveryBase):
    def __init__(self):
        super(NodesDiscoveryTripleO, self).__init__()
        self.nova_cli = nova_client.Client()
        self.last_run = None
        self.instances = {}

    @staticmethod
    def _address(instance, field):
        return instance.addresses['ctlplane'][0].get(field)

    @staticmethod
    def _make_resource_url(ip):
        params = [('readonly_user_auth_proto', 'auth_proto'),
                  ('readonly_user_priv_proto', 'priv_proto'),
                  ('readonly_user_priv_password', 'priv_password')]
        hwconf = CONF.hardware
        url = hwconf.url_scheme
        username = hwconf.readonly_user_name
        password = hwconf.readonly_user_password
        if username:
            url += username
        if password:
            url += ':' + password
        if username or password:
            url += '@'
        url += ip

        query = "&".join(
            param + "=" + hwconf.get(conf) for (conf, param) in params
            if hwconf.get(conf))
        if query:
            url += '?' + query

        return url

    def discover(self, manager, param=None):
        """Discover resources to monitor.

        instance_get_all will return all instances if last_run is None,
        and will return only the instances changed since the last_run time.
        """
        try:
            instances = self.nova_cli.instance_get_all(self.last_run)
        except Exception:
            # NOTE(zqfan): instance_get_all is wrapped and will log exception
            # when there is any error. It is no need to raise it again and
            # print one more time.
            return []

        for instance in instances:
            if getattr(instance, 'OS-EXT-STS:vm_state', None) in ['deleted',
                                                                  'error']:
                self.instances.pop(instance.id, None)
            else:
                self.instances[instance.id] = instance
        self.last_run = timeutils.utcnow(True).isoformat()

        resources = []
        for instance in self.instances.values():
            try:
                ip_address = self._address(instance, 'addr')
                final_address = self._make_resource_url(ip_address)

                resource = {
                    'resource_id': instance.id,
                    'resource_url': final_address,
                    'mac_addr': self._address(instance,
                                              'OS-EXT-IPS-MAC:mac_addr'),
                    'image_id': instance.image['id'],
                    'flavor_id': instance.flavor['id']
                }

                resources.append(resource)
            except KeyError:
                LOG.error(_("Couldn't obtain IP address of "
                            "instance %s") % instance.id)

        return resources
