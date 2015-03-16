# Copyright 2014 Intel Corporation.
# All Rights Reserved.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

"""Pollsters for IPMI and Intel Node Manager
"""

from oslo_config import cfg

OPTS = [
    cfg.IntOpt('polling_retry',
               default=3,
               help='Tolerance of IPMI/NM polling failures '
                    'before disable this pollster. '
                    'Negative indicates retrying forever.')
]

cfg.CONF.register_opts(OPTS, group='ipmi')
